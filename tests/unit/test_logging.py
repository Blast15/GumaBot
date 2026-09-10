import json
import logging

from gumabot.logging_config import JsonFormatter


def test_json_log_preserves_exception_and_unicode():
    try:
        raise ValueError("broken")
    except ValueError:
        import sys

        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "Lỗi", (), sys.exc_info())
    record.event = "worker_failure"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "worker_failure"
    assert payload["message"] == "Lỗi"
    assert "ValueError: broken" in payload["traceback"]
