import json
import os
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from metrics import record_request, render
from tracing import emit_span, trace_id
from auth import is_admin

DB_PATH = os.getenv("DB_PATH", "products.db")


def connection():
    database = sqlite3.connect(DB_PATH, timeout=10)
    database.row_factory = sqlite3.Row
    return database


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as database:
        database.execute("CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL, category TEXT NOT NULL, status TEXT NOT NULL)")
        if database.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            database.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", [
                ("keyboard", "Mechanical Keyboard", 89.0, "Desk", "active"),
                ("mouse", "Precision Mouse", 49.0, "Desk", "active"),
                ("monitor", "4K Monitor", 399.0, "Display", "active"),
            ])


def rows_to_products(rows):
    return [dict(row) for row in rows]


init_db()


class ProductsHandler(BaseHTTPRequestHandler):
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
        emit_span(request_trace, f"products.{self.command}", started)

    def do_GET(self):
        if self.path == "/metrics":
            with connection() as database:
                total = database.execute("SELECT COUNT(*) FROM products").fetchone()[0]
                active = database.execute("SELECT COUNT(*) FROM products WHERE status = 'active'").fetchone()[0]
            body = render([("microshop_products_total", total, "gauge"), ("microshop_products_active", active, "gauge")]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self._send(200, {"service": "products", "status": "ok"})
        elif self.path == "/products":
            with connection() as database:
                self._send(200, rows_to_products(database.execute("SELECT * FROM products WHERE status = 'active'").fetchall()))
        elif self.path == "/admin/products":
            if not is_admin(self.headers.get("Authorization")):
                self._send(401, {"error": "admin authentication required"})
                return
            with connection() as database:
                self._send(200, rows_to_products(database.execute("SELECT * FROM products").fetchall()))
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/products":
            self._send(404, {"error": "not found"})
            return
        if not is_admin(self.headers.get("Authorization")):
            self._send(401, {"error": "admin authentication required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            name = request["name"].strip()
            category = request["category"].strip()
            price = float(request["price"])
            if not name or not category or price <= 0:
                raise ValueError("invalid product")
            product = {"id": uuid.uuid4().hex[:8], "name": name, "price": price, "category": category, "status": "pending"}
            with connection() as database:
                database.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?)", tuple(product.values()))
            self._send(201, product)
        except (KeyError, ValueError, json.JSONDecodeError):
            self._send(400, {"error": "expected name, category, and positive price"})

    def do_PUT(self):
        prefix = "/admin/products/"
        if not self.path.startswith(prefix) or not self.path.endswith("/enable"):
            self._send(404, {"error": "not found"})
            return
        if not is_admin(self.headers.get("Authorization")):
            self._send(401, {"error": "admin authentication required"})
            return
        product_id = self.path[len(prefix):-len("/enable")]
        with connection() as database:
            database.execute("UPDATE products SET status = 'active' WHERE id = ?", (product_id,))
            product = database.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            self._send(404, {"error": "product not found"})
            return
        self._send(200, dict(product))

    def log_message(self, format, *args):
        print(f"products: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))
    print(f"products listening on {port}")
    ThreadingHTTPServer(("0.0.0.0", port), ProductsHandler).serve_forever()
