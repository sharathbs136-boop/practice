import json
import os
import sqlite3
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from metrics import record_request, render

DB_PATH = os.getenv("DB_PATH", "users.db")


def connection():
    database = sqlite3.connect(DB_PATH, timeout=10)
    database.row_factory = sqlite3.Row
    return database


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                address TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Insert default admin user
        try:
            database.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                ("admin", "admin@microshop.local", "admin123", "admin")
            )
        except sqlite3.IntegrityError:
            pass


init_db()


class UsersHandler(BaseHTTPRequestHandler):
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
            self._send(200, {"service": "users", "status": "ok"})
        elif self.path == "/metrics":
            with connection() as database:
                total = database.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            body = render([("microshop_users_total", total, "gauge")]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/users/register":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                username = payload["username"].strip()
                email = payload.get("email", f"{username}@microshop.local")
                password = payload["password"]
                
                if len(username) < 3 or len(password) < 6:
                    self._send(400, {"error": "username must be 3+ characters, password 6+ characters"})
                    return
                
                with connection() as database:
                    database.execute(
                        "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                        (username, email, password, "user")
                    )
                self._send(201, {"username": username, "email": email, "role": "user"})
            except sqlite3.IntegrityError:
                self._send(409, {"error": "username or email already exists"})
            except (KeyError, ValueError, json.JSONDecodeError):
                self._send(400, {"error": "username, email, and password are required"})
        elif self.path == "/users/verify":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                username = payload["username"]
                password = payload["password"]
                
                with connection() as database:
                    user = database.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                
                if user and user["password_hash"] == password:
                    self._send(200, {"username": user["username"], "email": user["email"], "role": user["role"]})
                else:
                    self._send(401, {"error": "invalid username or password"})
            except (KeyError, json.JSONDecodeError):
                self._send(400, {"error": "username and password are required"})
        elif self.path == "/users/profile":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                username = payload["username"]
                
                with connection() as database:
                    user = database.execute(
                        "SELECT username, email, role, address, phone FROM users WHERE username = ?",
                        (username,)
                    ).fetchone()
                
                if user:
                    self._send(200, dict(user))
                else:
                    self._send(404, {"error": "user not found"})
            except (KeyError, json.JSONDecodeError):
                self._send(400, {"error": "username is required"})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, format, *args):
        print(f"users: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8006"))
    print(f"users listening on {port}")
    ThreadingHTTPServer(("0.0.0.0", port), UsersHandler).serve_forever()
