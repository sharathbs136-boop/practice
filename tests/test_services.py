import importlib.util
import json
import base64
import hashlib
import hmac
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load_service(name, path):
    service_path = ROOT / path
    if path == "services/orders/src/app.py":
        sys.modules.pop("auth", None)
    sys.path.insert(0, str(service_path.parent))
    spec = importlib.util.spec_from_file_location(name, service_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


products = load_service("products_app", "services/products/src/app.py")
inventory = load_service("inventory_app", "services/inventory/src/app.py")
orders = load_service("orders_app", "services/orders/src/app.py")


class ServiceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = []
        for module in (inventory, products):
            server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.InventoryHandler if module is inventory else module.ProductsHandler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.servers.append(server)
        inventory_port = cls.servers[0].server_address[1]
        orders.INVENTORY_URL = f"http://127.0.0.1:{inventory_port}"
        server = orders.ThreadingHTTPServer(("127.0.0.1", 0), orders.OrdersHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.servers.append(server)

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:
            server.shutdown()

    def setUp(self):
        with products.connection() as database:
            database.execute("DELETE FROM products")
            database.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?)", ("keyboard", "Mechanical Keyboard", 89.0, "Desk", "active"))
        with inventory.connection() as database:
            database.execute("DELETE FROM stock")
        with orders.connection() as database:
            database.execute("DELETE FROM orders")
        body = base64.urlsafe_b64encode(json.dumps({"username": "admin", "role": "admin"}).encode()).decode().rstrip("=")
        signature = hmac.new(b"microshop-practice-secret", body.encode(), hashlib.sha256).hexdigest()
        self.admin_headers = {"Authorization": f"Bearer {body}.{signature}"}

    def request(self, server, method, path, payload=None, headers=None):
        connection = HTTPConnection("127.0.0.1", server.server_address[1])
        body = json.dumps(payload).encode() if payload is not None else None
        request_headers = {"Content-Type": "application/json"} if body else {}
        request_headers.update(headers or {})
        connection.request(method, path, body, request_headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        connection.close()
        return response.status, data

    def test_product_activation_and_order_deducts_stock(self):
        inventory_server, products_server, orders_server = self.servers
        status, product = self.request(products_server, "POST", "/products", {"name": "USB Hub", "category": "Desk", "price": 29.99}, self.admin_headers)
        self.assertEqual(status, 201)
        self.assertEqual(product["status"], "pending")

        status, _ = self.request(products_server, "PUT", f"/admin/products/{product['id']}/enable", headers=self.admin_headers)
        self.assertEqual(status, 200)
        status, stock = self.request(inventory_server, "POST", "/stock/enable", {"sku": product["id"], "quantity": 3}, self.admin_headers)
        self.assertEqual(status, 200)
        self.assertEqual(stock["quantity"], 3)

        status, order = self.request(orders_server, "POST", "/orders", {"sku": product["id"], "quantity": 1}, self.admin_headers)
        self.assertEqual(status, 201)
        self.assertEqual(order["status"], "confirmed")
        self.assertEqual(order["product_id"], product["id"])
        self.assertEqual(order["reservation"]["remaining"], 2)

        status, remaining = self.request(inventory_server, "GET", "/stock")
        self.assertEqual(status, 200)
        self.assertEqual(remaining[product["id"]], 2)

    def test_order_fails_when_stock_is_insufficient(self):
        inventory_server, _, orders_server = self.servers
        self.request(inventory_server, "POST", "/stock/enable", {"sku": "keyboard", "quantity": 1}, self.admin_headers)
        status, response = self.request(orders_server, "POST", "/orders", {"sku": "keyboard", "quantity": 2}, self.admin_headers)
        self.assertEqual(status, 409)
        self.assertFalse(response["reserved"])


if __name__ == "__main__":
    unittest.main()
