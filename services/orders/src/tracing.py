import json
import os
import threading
import time
import uuid
from urllib.request import Request, urlopen

ZIPKIN_URL = os.getenv("ZIPKIN_URL", "")


def trace_id(headers):
    return headers.get("X-Trace-ID") or uuid.uuid4().hex


def emit_span(trace, name, started):
    if not ZIPKIN_URL:
        return
    payload = [{"traceId": trace, "id": uuid.uuid4().hex[:16], "name": name, "timestamp": int(started * 1_000_000), "duration": max(1, int((time.time() - started) * 1_000_000)), "localEndpoint": {"serviceName": "orders"}}]

    def send():
        try:
            request = Request(f"{ZIPKIN_URL}/api/v2/spans", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
            urlopen(request, timeout=0.5).close()
        except Exception:
            pass

    threading.Thread(target=send, daemon=True).start()
