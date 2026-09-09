"""Regression tests for a Milestone 10 review finding: structured-log
redaction only masked top-level `extra` keys by name, so a secret nested
inside a list/dict value (e.g. pydantic's ValidationError.errors(), which
separates the field name in `loc` from the raw value in a sibling `input`
key) was not redacted even though it matched the code's own documented
intent ("masks any extra field whose key looks like a secret")."""

import json
import logging

from app.core.errors import _safe_validation_errors
from app.core.logging import RedactingJSONFormatter, _redact_recursive


def test_redact_recursive_masks_nested_dict_values():
    payload = {"user": {"name": "alice", "password": "hunter2"}}
    redacted = _redact_recursive(payload)
    assert redacted == {"user": {"name": "alice", "password": "***REDACTED***"}}


def test_redact_recursive_masks_inside_lists():
    payload = [{"api_key": "sk_live_abc"}, {"note": "fine"}]
    redacted = _redact_recursive(payload)
    assert redacted == [{"api_key": "***REDACTED***"}, {"note": "fine"}]


def test_formatter_redacts_nested_dict_by_key_name():
    # The formatter's own defense: any dict key matching the sensitive
    # pattern is masked no matter how deeply nested. (The loc/input
    # mismatch in pydantic's error shape -- where the secret VALUE sits
    # under a non-sensitive-looking "input" key -- is a different problem,
    # fixed separately at the call site by _safe_validation_errors below.)
    record = logging.LogRecord(
        name="safeops",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="something happened",
        args=(),
        exc_info=None,
    )
    record.context = {"nested": {"api_key": "should-not-appear"}}
    formatted = RedactingJSONFormatter().format(record)
    assert "should-not-appear" not in formatted
    payload = json.loads(formatted)
    assert payload["context"]["nested"]["api_key"] == "***REDACTED***"


def test_formatter_redacts_already_sanitized_validation_errors_end_to_end():
    # The real call path: errors.py sanitizes via _safe_validation_errors
    # before ever calling logger.warning -- confirm the final formatted
    # log line does not contain the raw secret when that path is followed.
    record = logging.LogRecord(
        name="safeops",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="request_validation_error",
        args=(),
        exc_info=None,
    )
    raw_errors = [{"loc": ("body", "token"), "msg": "field required", "input": "should-not-appear"}]
    record.errors = _safe_validation_errors(raw_errors)
    formatted = RedactingJSONFormatter().format(record)
    assert "should-not-appear" not in formatted
    payload = json.loads(formatted)
    assert payload["errors"][0]["input"] == "***REDACTED***"


def test_safe_validation_errors_redacts_input_by_loc_field_name():
    errors = [
        {"loc": ("body", "api_key"), "msg": "field required", "input": "sk_live_abc123"},
        {"loc": ("body", "objective"), "msg": "field required", "input": "not-secret-value"},
    ]
    safe = _safe_validation_errors(errors)
    assert safe[0]["input"] == "***REDACTED***"
    assert safe[1]["input"] == "not-secret-value"


def test_safe_validation_errors_leaves_non_sensitive_fields_untouched():
    errors = [{"loc": ("body", "agent_id"), "msg": "invalid uuid", "input": "not-a-uuid"}]
    safe = _safe_validation_errors(errors)
    assert safe[0]["input"] == "not-a-uuid"


def test_safe_validation_errors_redacts_external_source_content():
    # Milestone 11 review finding: "content"/"sources" are not
    # secret-sounding field names, so _is_sensitive_key alone never caught
    # this shape -- confirmed by hand with a real >20,000-char malicious
    # payload that failed length validation and appeared verbatim in
    # server logs before this fix. SourceInput.content is externally
    # supplied, untrusted-by-design content (see app/schemas/
    # external_action.py), not a secret, but must not be logged raw either.
    malicious = "MALICIOUS-SECRET-MARKER-" + ("A" * 21_000)
    errors = [
        {
            "loc": ("body", "sources", 0, "content"),
            "msg": "String should have at most 20000 characters",
            "input": malicious,
        }
    ]
    safe = _safe_validation_errors(errors)
    assert safe[0]["input"] == "***REDACTED***"

    record = logging.LogRecord(
        name="safeops",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="request_validation_error",
        args=(),
        exc_info=None,
    )
    record.errors = safe
    formatted = RedactingJSONFormatter().format(record)
    assert malicious not in formatted
    assert "MALICIOUS-SECRET-MARKER" not in formatted
