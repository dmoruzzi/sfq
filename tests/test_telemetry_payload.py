import importlib
import os


def _reload_telemetry():
    import sfq.telemetry as telemetry
    importlib.reload(telemetry)
    return telemetry


def test_standard_payload_contains_no_pii():
    old = os.environ.get("SFQ_TELEMETRY")
    try:
        os.environ["SFQ_TELEMETRY"] = "1"
        t = _reload_telemetry()

        ctx = {
            "method": "GET",
            "endpoint": "/services/data/v50.0/sobjects/Account?id=001",
            "status": 200,
            "duration_ms": 123,
            "request_headers": {
                "Authorization": "Bearer SECRET",
                "Accept": "application/json",
                "Sforce-Call-Options": "client=sfq/0.0.47",
            },
        }

        payload = t._build_payload("http.request", ctx, 1)

        assert "payload" in payload
        p = payload["payload"]
        # Standard payload only contains method, status_code, duration_ms
        assert p.get("method") == "GET"
        # Standard telemetry must not include the request path
        assert "path" not in p
        assert p.get("status_code") == 200
        assert p.get("duration_ms") == 123
        # Headers must not appear in Standard payload
        assert "request_headers" not in p
        # sforce_client should be extracted into environment
        assert "environment" in p
        assert p["environment"]["sforce_client"] == "sfq/0.0.47"

    finally:
        if old is None:
            os.environ.pop("SFQ_TELEMETRY", None)
        else:
            os.environ["SFQ_TELEMETRY"] = old


def test_full_payload_includes_redacted_headers():
    old = os.environ.get("SFQ_TELEMETRY")
    try:
        os.environ["SFQ_TELEMETRY"] = "2"
        t = _reload_telemetry()

        ctx = {
            "method": "POST",
            "endpoint": "/services/data/v50.0/sobjects/Account",
            "status": 500,
            "duration_ms": 999,
            "request_headers": {
                "Authorization": "Bearer SECRET",
                "X-Custom": "value",
                "Sforce-Call-Options": "client=sfq/0.0.47",
            },
            "response_headers": {"Set-Cookie": "s=sess"},
        }

        payload = t._build_payload("http.request", ctx, 2)
        assert "payload" in payload
        p = payload["payload"]
        # Headers should be present but redacted
        assert "request_headers" in p
        assert p["request_headers"]["Authorization"] == "REDACTED"
        assert p["request_headers"]["X-Custom"] == "value"
        # sforce_client should be present in environment as well
        assert "environment" in p
        assert p["environment"]["sforce_client"] == "sfq/0.0.47"

    finally:
        if old is None:
            os.environ.pop("SFQ_TELEMETRY", None)
        else:
            os.environ["SFQ_TELEMETRY"] = old
