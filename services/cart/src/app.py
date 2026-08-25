import json
import os
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from metrics import record_request, render

DB_PATH = os.getenv("DB_PATH", "carts.db")


def connection():
    database = sqlite3.connect(DB_PATH, timeout=10)
    database.row_factory = sqlite3.Row
    return database


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS carts (
                cart_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        database.execute("""
            CREATE TABLE IF NOT EXISTS cart_items (
                id TEXT PRIMARY KEY,
                cart_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY(cart_id) REFERENCES carts(cart_id)
            )
        """)


init_db()


class CartHandler(BaseHTTPRequestHandler):
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
            self._send(200, {"service": "cart", "status": "ok"})
        elif self.path == "/metrics":
            with connection() as database:
                total_carts = database.execute("SELECT COUNT(*) FROM carts").fetchone()[0]
                total_items = database.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0]
            body = render([
                ("microshop_carts_total", total_carts, "gauge"),
                ("microshop_cart_items_total", total_items, "gauge")
            ]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/cart/get":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                username = payload["username"]
                
                with connection() as database:
                    cart = database.execute("SELECT * FROM carts WHERE username = ?", (username,)).fetchone()
                    if not cart:
                        cart_id = f"cart-{uuid.uuid4().hex[:10]}"
                        database.execute("INSERT INTO carts (cart_id, username) VALUES (?, ?)", (cart_id, username))
                        cart = {"cart_id": cart_id, "username": username}
                    else:
                        cart = dict(cart)
                    
                    items = database.execute("SELECT sku, name, price, quantity FROM cart_items WHERE cart_id = ?", (cart["cart_id"],)).fetchall()
                
                self._send(200, {"cart_id": cart["cart_id"], "items": [dict(row) for row in items]})
            except (KeyError, json.JSONDecodeError):
                self._send(400, {"error": "username is required"})
        
        elif self.path == "/cart/add":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                cart_id = payload["cart_id"]
                sku = payload["sku"]
                name = payload["name"]
                price = float(payload["price"])
                quantity = int(payload["quantity"])
                
                with connection() as database:
                    item_id = f"item-{uuid.uuid4().hex[:10]}"
                    database.execute(
                        "INSERT INTO cart_items (id, cart_id, sku, name, price, quantity) VALUES (?, ?, ?, ?, ?, ?)",
                        (item_id, cart_id, sku, name, price, quantity)
                    )
                
                self._send(201, {"item_id": item_id, "sku": sku})
            except (KeyError, ValueError, json.JSONDecodeError):
                self._send(400, {"error": "cart_id, sku, name, price, and quantity are required"})
        
        elif self.path == "/cart/clear":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                cart_id = payload["cart_id"]
                
                with connection() as database:
                    database.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
                
                self._send(200, {"cart_id": cart_id, "cleared": True})
            except (KeyError, json.JSONDecodeError):
                self._send(400, {"error": "cart_id is required"})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, format, *args):
        print(f"cart: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8007"))
    print(f"cart listening on {port}")
    ThreadingHTTPServer(("0.0.0.0", port), CartHandler).serve_forever()
