from __future__ import annotations

import json
import logging

from skeinrank_governance_api.observability.logging import (
    JsonLogFormatter,
    structured_log_extra,
)


def test_structured_log_extra_adds_event_and_sanitizes_reserved_fields():
    extra = structured_log_extra(
        event="ops.test",
        outcome="succeeded",
        msg="reserved message",
        _private="hidden",
        nested={"value": object()},
    )

    assert extra["event"] == "ops.test"
    assert extra["outcome"] == "succeeded"
    assert extra["field_msg"] == "reserved message"
    assert extra["field_private"] == "hidden"
    assert isinstance(extra["nested"]["value"], str)


def test_json_formatter_renders_structured_event_fields():
    formatter = JsonLogFormatter(
        service_name="skeinrank-governance-api", service_version="test"
    )
    record = logging.LogRecord(
        name="skeinrank.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="structured event",
        args=(),
        exc_info=None,
    )
    for key, value in structured_log_extra(
        event="ops.report.generated",
        outcome="succeeded",
        request_id="req-structured",
        report_status="ok",
    ).items():
        setattr(record, key, value)

    payload = json.loads(formatter.format(record))

    assert payload["event"] == "ops.report.generated"
    assert payload["outcome"] == "succeeded"
    assert payload["request_id"] == "req-structured"
    assert payload["report_status"] == "ok"
