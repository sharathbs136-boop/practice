import threading

_REQUESTS = 0
_LOCK = threading.Lock()


def record_request():
    global _REQUESTS
    with _LOCK:
        _REQUESTS += 1


def render(extra):
    with _LOCK:
        requests = _REQUESTS
    lines = ["# HELP microshop_http_requests_total Total HTTP requests.", "# TYPE microshop_http_requests_total counter", f"microshop_http_requests_total{{service=\"cart\"}} {requests}"]
    for name, value, kind in extra:
        lines.extend([f"# TYPE {name} {kind}", f"{name}{{service=\"cart\"}} {value}"])
    return "\n".join(lines) + "\n"
