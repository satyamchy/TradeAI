import json
import logging

from app.shared.logging import StructuredFormatter, bind_log_context, reset_log_context


def test_structured_logs_carry_request_id_and_redact_credentials():
    tokens = bind_log_context(request_id="req-test", module="ai_analysis")
    try:
        record = logging.LogRecord(
            "trade.test", logging.INFO, __file__, 1,
            "access_token=very-secret", (), None,
        )
        payload = json.loads(StructuredFormatter().format(record))
    finally:
        reset_log_context(tokens)

    assert payload["request_id"] == "req-test"
    assert payload["module"] == "ai_analysis"
    assert "very-secret" not in payload["message"]
