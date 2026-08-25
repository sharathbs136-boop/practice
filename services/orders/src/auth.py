import base64
import hashlib
import hmac
import json
import os

SECRET = os.getenv("AUTH_SECRET", "microshop-practice-secret")


def is_authenticated(header):
    try:
        token = (header or "").removeprefix("Bearer ")
        body, signature = token.split(".")
        expected = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return hmac.compare_digest(signature, expected) and payload.get("username")
    except (ValueError, json.JSONDecodeError):
        return False
