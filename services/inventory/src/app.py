import json
import os
import queue
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from metrics import record_request, render
from tracing import emit_span, trace_id
from auth import is_admin

DB_PATH = os.getenv("DB_PATH", "inventory.db")


def connection():
    return sqlite3.connect(DB_PATH, timeout=10)


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as database:
        database.execute("CREATE TABLE IF NOT EXISTS stock (sku TEXT PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity >= 0))")
        if database.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 0:
            database.executemany("INSERT INTO stock VALUES (?, ?)", [("keyboard", 10), ("mouse", 25), ("monitor", 5)])


init_db()
SUBSCRIBERS = set()


def broadcast_stock():
    with connection() as database:
        payload = dict(database.execute("SELECT sku, quantity FROM stock").fetchall())
    for subscriber in list(SUBSCRIBERS):
        subscriber.put(payload)


class InventoryHandler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        record_request()
        started = __import__("time").time()
        request_trace = trace_id(self.headers)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Trace-ID", request_trace)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        emit_span(request_trace, f"inventory.{self.command}", started)

    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            subscriber = queue.Queue()
            SUBSCRIBERS.add(subscriber)
            try:
                while True:
                    try:
                        payload = subscriber.get(timeout=15)
                        self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                SUBSCRIBERS.discard(subscriber)
        elif self.path == "/metrics":
            with connection() as database:
                units = database.execute("SELECT COALESCE(SUM(quantity), 0) FROM stock").fetchone()[0]
                items = database.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
            body = render([("microshop_inventory_stock_units", units, "gauge"), ("microshop_inventory_stock_items", items, "gauge")]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self._send(200, {"service": "inventory", "status": "ok"})
        elif self.path == "/stock":
            with connection() as database:
                rows = database.execute("SELECT sku, quantity FROM stock").fetchall()
            self._send(200, dict(rows))
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/reserve", "/stock/enable"):
            self._send(404, {"error": "not found"})
            return
        if self.path == "/stock/enable" and not is_admin(self.headers.get("Authorization")):
            self._send(401, {"error": "admin authentication required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            sku = request["sku"]
            quantity = int(request["quantity"])
            if quantity < 1:
                raise ValueError("quantity must be positive")
            with connection() as database:
                if self.path == "/stock/enable":
                    database.execute("INSERT INTO stock(sku, quantity) VALUES (?, ?) ON CONFLICT(sku) DO UPDATE SET quantity = excluded.quantity", (sku, quantity))
                    self._send(200, {"enabled": True, "sku": sku, "quantity": quantity})
                    broadcast_stock()
                    return
                updated = database.execute("UPDATE stock SET quantity = quantity - ? WHERE sku = ? AND quantity >= ?", (quantity, sku, quantity)).rowcount
                if updated == 0:
                    self._send(409, {"reserved": False, "error": "insufficient stock"})
                    return
                remaining = database.execute("SELECT quantity FROM stock WHERE sku = ?", (sku,)).fetchone()[0]
                self._send(200, {"reserved": True, "sku": sku, "quantity": quantity, "remaining": remaining})
                broadcast_stock()
        except (KeyError, ValueError, json.JSONDecodeError):
            self._send(400, {"error": "expected sku and positive quantity"})

    def log_message(self, format, *args):
        print(f"inventory: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8001"))
    print(f"inventory listening on {port}")
    ThreadingHTTPServer(("0.0.0.0", port), InventoryHandler).serve_forever()
