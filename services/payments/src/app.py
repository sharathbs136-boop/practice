import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class PaymentsHandler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"service": "payments", "status": "ok", "mode": "sandbox"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/payments/authorize":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            payment_token = request["payment_token"]
            amount = float(request["amount"])
            if not payment_token or amount <= 0:
                raise ValueError("invalid payment")
            if payment_token == "declined":
                self._send(402, {"approved": False, "error": "payment declined"})
                return
            self._send(201, {"approved": True, "payment_id": f"pay-{uuid.uuid4().hex[:10]}", "amount": round(amount, 2)})
        except (KeyError, ValueError, json.JSONDecodeError):
            self._send(400, {"error": "payment_token and positive amount are required"})

    def log_message(self, format, *args):
        print(f"payments: {format % args}")


if __name__ == "__main__":
    port = 8004
    print(f"payments listening on {port} (sandbox)")
    ThreadingHTTPServer(("0.0.0.0", port), PaymentsHandler).serve_forever()
