import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load_tracing(service):
    path = ROOT / "services" / service / "src" / "tracing.py"
    spec = importlib.util.spec_from_file_location(f"{service}_tracing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TracingTests(unittest.TestCase):
    def test_trace_id_is_forwarded_or_created(self):
        tracing = load_tracing("orders")
        self.assertEqual(tracing.trace_id({"X-Trace-ID": "abc123"}), "abc123")
        self.assertEqual(len(tracing.trace_id({})), 32)

    def test_zipkin_is_optional(self):
        tracing = load_tracing("inventory")
        tracing.emit_span("a" * 32, "inventory.reserve", 1.0)


if __name__ == "__main__":
    unittest.main()
