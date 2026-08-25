import json
import os
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from metrics import record_request, render
from tracing import emit_span, trace_id
from auth import is_authenticated

INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8001")
DB_PATH = os.getenv("DB_PATH", "orders.db")


def connection():
    return sqlite3.connect(DB_PATH, timeout=10)


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as database:
        database.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, sku TEXT NOT NULL, quantity INTEGER NOT NULL, status TEXT NOT NULL, reservation TEXT NOT NULL)")


init_db()


def reserve_stock(sku, quantity, request_trace):
    body = json.dumps({"sku": sku, "quantity": quantity}).encode("utf-8")
    request = Request(
        f"{INVENTORY_URL}/reserve",
        data=body,
        headers={"Content-Type": "application/json", "X-Trace-ID": request_trace},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())
    except URLError:
        return 503, {"error": "inventory unavailable"}


class OrdersHandler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        record_request()
        started = __import__("time").time()
        response_trace = trace_id(self.headers)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Trace-ID", response_trace)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        emit_span(response_trace, f"orders.{self.command}", started)

    def do_GET(self):
        if self.path == "/metrics":
            with connection() as database:
                created = database.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            body = render([("microshop_orders_created_total", created, "counter")]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self._send(200, {"service": "orders", "status": "ok"})
        elif self.path == "/orders":
            with connection() as database:
                rows = database.execute("SELECT order_id, sku, quantity, status FROM orders ORDER BY rowid DESC").fetchall()
            self._send(200, [dict(row) for row in rows])
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/orders":
            self._send(404, {"error": "not found"})
            return
        if not is_authenticated(self.headers.get("Authorization")):
            self._send(401, {"error": "sign in required to place an order"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            sku = request["sku"]
            quantity = int(request["quantity"])
            status, reservation = reserve_stock(sku, quantity, trace_id(self.headers))
            if status != 200:
                self._send(status, reservation)
                return
            order = {"order_id": f"order-{uuid.uuid4().hex[:10]}", "product_id": sku, "status": "confirmed", "reservation": reservation}
            with connection() as database:
                database.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", (order["order_id"], sku, quantity, order["status"], json.dumps(reservation)))
            self._send(201, order)
        except (KeyError, ValueError, json.JSONDecodeError):
            self._send(400, {"error": "expected sku and positive quantity"})

    def log_message(self, format, *args):
        print(f"orders: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"orders listening on {port}; inventory={INVENTORY_URL}")
    ThreadingHTTPServer(("0.0.0.0", port), OrdersHandler).serve_forever()
