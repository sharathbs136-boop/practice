import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from metrics import record_request, render

DB_PATH = os.getenv("DB_PATH", "notifications.db")


def connection():
    database = sqlite3.connect(DB_PATH, timeout=10)
    database.row_factory = sqlite3.Row
    return database


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                event_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read INTEGER DEFAULT 0
            )
        """)


init_db()


class NotificationsHandler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        record_request()
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"service": "notifications", "status": "ok"})
        elif self.path == "/metrics":
            with connection() as database:
                total = database.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
                unread = database.execute("SELECT COUNT(*) FROM notifications WHERE read=0").fetchone()[0]
            body = render([
                ("microshop_notifications_total", total, "counter"),
                ("microshop_notifications_unread", unread, "gauge")
            ]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/notifications/send":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            username = payload["username"]
            event_type = payload["event_type"]
            subject = payload["subject"]
            message = payload["message"]
            notification_id = f"notif-{payload.get('id', 'unknown')}"
            
            with connection() as database:
                database.execute(
                    "INSERT INTO notifications (id, username, event_type, subject, message) VALUES (?, ?, ?, ?, ?)",
                    (notification_id, username, event_type, subject, message)
                )
            self._send(201, {"id": notification_id, "username": username, "event_type": event_type})
        except (KeyError, ValueError, json.JSONDecodeError):
            self._send(400, {"error": "username, event_type, subject, and message are required"})

    def log_message(self, format, *args):
        print(f"notifications: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8005"))
    print(f"notifications listening on {port}")
    ThreadingHTTPServer(("0.0.0.0", port), NotificationsHandler).serve_forever()
