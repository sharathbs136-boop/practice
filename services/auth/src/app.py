import base64
import hashlib
import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.getenv("AUTH_SECRET", "microshop-practice-secret")
USERS = {"admin": {"password": "admin123", "role": "admin"}, "user": {"password": "user123", "role": "user"}}


def encode(payload):
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify(token):
    try:
        body, signature = token.split(".")
        expected = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None


class AuthHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"service": "auth", "status": "ok"})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/login", "/register"):
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            if self.path == "/register":
                username = request["username"].strip()
                password = request["password"]
                if len(username) < 3 or len(password) < 6:
                    self.send_json(400, {"error": "username must be 3+ characters and password 6+ characters"})
                    return
                if username in USERS:
                    self.send_json(409, {"error": "username already exists"})
                    return
                USERS[username] = {"password": password, "role": "user"}
                self.send_json(201, {"username": username, "role": "user"})
                return
            user = USERS.get(request["username"])
            if user is None or not secrets.compare_digest(user["password"], request["password"]):
                self.send_json(401, {"error": "invalid username or password"})
                return
            self.send_json(200, {"token": encode({"username": request["username"], "role": user["role"]}), "username": request["username"], "role": user["role"]})
        except (KeyError, json.JSONDecodeError):
            self.send_json(400, {"error": "username and password are required"})

    def log_message(self, format, *args):
        print(f"auth: {format % args}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8003"))
    print(f"auth listening on {port}")
    ThreadingHTTPServer(("0.0.0.0", port), AuthHandler).serve_forever()
