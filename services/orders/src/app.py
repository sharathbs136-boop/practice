import json
import os
import queue
import sqlite3
import uuid
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from metrics import record_request, render
from tracing import emit_span, trace_id
from auth import identity
from auth import is_authenticated
from auth import is_admin

INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8004")
DB_PATH = os.getenv("DB_PATH", "orders.db")
ORDER_STATUSES = ("confirmed", "processing", "shipped", "delivered", "cancelled")


def connection():
    database = sqlite3.connect(DB_PATH, timeout=10)
    database.row_factory = sqlite3.Row
    return database


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as database:
        database.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, sku TEXT NOT NULL, quantity INTEGER NOT NULL, status TEXT NOT NULL, reservation TEXT NOT NULL, username TEXT NOT NULL DEFAULT '')")
        columns = {row[1] for row in database.execute("PRAGMA table_info(orders)").fetchall()}
        if "username" not in columns:
            database.execute("ALTER TABLE orders ADD COLUMN username TEXT NOT NULL DEFAULT ''")


init_db()
SUBSCRIBERS = set()


def orders_snapshot(username=None):
    with connection() as database:
        if username is None:
            rows = database.execute("SELECT order_id, sku, quantity, status FROM orders ORDER BY rowid DESC").fetchall()
        else:
            rows = database.execute("SELECT order_id, sku, quantity, status FROM orders WHERE username = ? ORDER BY rowid DESC", (username,)).fetchall()
    return [dict(row) for row in rows]


def broadcast_orders():
    for subscriber in list(SUBSCRIBERS):
        subscriber.put(orders_snapshot(subscriber.username))


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


def authorize_payment(amount, payment_token, request_trace):
    body = json.dumps({"amount": amount, "payment_token": payment_token}).encode("utf-8")
    request = Request(
        f"{PAYMENT_URL}/payments/authorize",
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
        return 503, {"error": "payment service unavailable"}


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
        request_path = urlparse(self.path).path
        if request_path == "/events":
            token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            payload = identity(self.headers.get("Authorization") or f"Bearer {token}")
            if payload is None:
                self._send(401, {"error": "sign in required for live orders"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            subscriber = queue.Queue()
            subscriber.username = None if payload.get("role") == "admin" else payload["username"]
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
        elif request_path == "/metrics":
            with connection() as database:
                created = database.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            body = render([("microshop_orders_created_total", created, "counter")]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif request_path == "/health":
            self._send(200, {"service": "orders", "status": "ok"})
        elif request_path in ("/orders", "/admin/orders"):
            payload = identity(self.headers.get("Authorization"))
            if payload is None:
                self._send(401, {"error": "sign in required to view orders"})
                return
            if request_path == "/admin/orders" and payload.get("role") != "admin":
                self._send(401, {"error": "admin authentication required"})
                return
            self._send(200, orders_snapshot(None if payload.get("role") == "admin" else payload["username"]))
        else:
            self._send(404, {"error": "not found"})

    def do_PUT(self):
        prefix = "/admin/orders/"
        suffix = "/status"
        if not self.path.startswith(prefix) or not self.path.endswith(suffix):
            self._send(404, {"error": "not found"})
            return
        if not is_admin(self.headers.get("Authorization")):
            self._send(401, {"error": "admin authentication required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            status = request["status"]
            if status not in ORDER_STATUSES:
                raise ValueError("invalid status")
            order_id = self.path[len(prefix):-len(suffix)]
            with connection() as database:
                updated = database.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id)).rowcount
                order = database.execute("SELECT order_id, sku, quantity, status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if updated == 0:
                self._send(404, {"error": "order not found"})
                return
            self._send(200, dict(order))
            broadcast_orders()
        except (KeyError, ValueError, json.JSONDecodeError):
            self._send(400, {"error": "status must be a valid order status"})

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
            payment_token = request.get("payment_token", "test-card")
            amount = float(request.get("amount", quantity))
            payment_status, payment = authorize_payment(amount, payment_token, trace_id(self.headers))
            if payment_status != 201:
                self._send(payment_status, payment)
                return
            status, reservation = reserve_stock(sku, quantity, trace_id(self.headers))
            if status != 200:
                self._send(status, reservation)
                return
            payload = identity(self.headers.get("Authorization"))
            order = {"order_id": f"order-{uuid.uuid4().hex[:10]}", "product_id": sku, "status": "confirmed", "reservation": reservation, "username": payload["username"]}
            with connection() as database:
                database.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", (order["order_id"], sku, quantity, order["status"], json.dumps(reservation), order["username"]))
            self._send(201, order)
            broadcast_orders()
        except (KeyError, ValueError, json.JSONDecodeError):
            self._send(400, {"error": "expected sku and positive quantity"})

    def log_message(self, format, *args):
        print(f"orders: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"orders listening on {port}; inventory={INVENTORY_URL}")
    ThreadingHTTPServer(("0.0.0.0", port), OrdersHandler).serve_forever()
