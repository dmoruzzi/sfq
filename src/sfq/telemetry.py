"""
Telemetry module for SFQ.

Provides opt-in HTTP event telemetry with explicit levels:
- 0 / unset: disabled
- 1: Standard (anonymous, no PII)
- 2: Debug (diagnostics; explicit opt-in)

Env vars used:
- `SFQ_TELEMETRY` : 0|1|2
- `SFQ_TELEMETRY_ENDPOINT` : URL to POST telemetry
- `SFQ_TELEMETRY_SAMPLING` : float 0.0-1.0 sampling fraction
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
import uuid
import random
import platform
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import http.client
import atexit
import logging

# Derive SDK version from package metadata or env; fall back to hardcoded value
try:
    try:
        # Python 3.8+
        from importlib.metadata import version, PackageNotFoundError  # type: ignore
    except Exception:
        # Backport for older Pythons
        from importlib_metadata import version, PackageNotFoundError  # type: ignore
except Exception:
    version = None  # type: ignore
    PackageNotFoundError = Exception  # type: ignore

try:
    _SDK_VERSION = os.getenv("SFQ_SDK_VERSION")
    if not _SDK_VERSION and version is not None:
        try:
            _SDK_VERSION = version("sfq")
        except PackageNotFoundError:
            _SDK_VERSION = None
    if not _SDK_VERSION:
        _SDK_VERSION = "0.0.47"
except Exception:
    _SDK_VERSION = "0.0.47"

DEFAULT_ENDPOINT = os.getenv(
    "SFQ_TELEMETRY_ENDPOINT", "https://sfq-telemetry.moruzzi.org/api/v0/events"
)

class TelemetryConfig:
    def __init__(self) -> None:
        raw = os.getenv("SFQ_TELEMETRY")
        try:
            self.level = int(raw) if raw is not None else 0
        except Exception:
            self.level = 0

        try:
            self.sampling = float(os.getenv("SFQ_TELEMETRY_SAMPLING", "1.0"))
        except Exception:
            self.sampling = 1.0

        self.endpoint = os.getenv("SFQ_TELEMETRY_ENDPOINT", DEFAULT_ENDPOINT)
        self.api_key = os.getenv("SFQ_TELEMETRY_KEY", "PUBLIC")

    def enabled(self) -> bool:
        return bool(self.level and self.level in (1, 2))


# Module-level config and client id
_config = TelemetryConfig()
_client_id = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
_logger = logging.getLogger("sfq.telemetry")
_debug = os.getenv("SFQ_TELEMETRY_DEBUG") in ("1", "true", "True")
_log_handler: Optional[logging.Handler] = None


def get_config() -> TelemetryConfig:
    return _config


def _build_payload(event_type: str, ctx: Dict[str, Any], level: int) -> Dict[str, Any]:
    base = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sdk": "sfq",
        "sdk_version": _SDK_VERSION,
        "event_type": event_type,
        "client_id": _client_id,
        "telemetry_level": level,
    }

    # Standard payload: safe, minimal, no PII
    if level == 1:
        # Only include the minimal fields requested by Standard telemetry consumers.
        allowed = {
            "method": ctx.get("method"),
        }
        # Add only basic non-identifying environment info
        try:
            allowed["environment"] = {
                "os": platform.system(),
                "os_release": platform.release(),
                "python_version": platform.python_version(),
            }
        except Exception:
            # never fail telemetry building for environment inspection
            pass

        base["payload"] = allowed
        return base

    # Debug payload: include more diagnostic info (only when explicitly enabled)
    payload = ctx.copy()
    # Add non-identifying environment info (include sforce_client for Full too)
    try:
        ua = None
        if isinstance(ctx.get("request_headers"), dict):
            ua = ctx.get("request_headers").get("User-Agent")

        sforce_client = None
        if isinstance(ctx.get("request_headers"), dict):
            sforce_client = _extract_sforce_client(
                ctx.get("request_headers").get("Sforce-Call-Options")
            )

        payload_env = {
            "os": platform.system(),
            "os_release": platform.release(),
            "python_version": platform.python_version(),
            "user_agent": ua,
            "sforce_client": sforce_client,
        }
        payload["environment"] = payload_env
    except Exception:
        pass
    # For Debug telemetry, replace raw path/endpoint with a hashed representation
    # to allow useful grouping without sending the actual path/ids.
    try:
        raw_path = None
        if isinstance(payload.get("path"), str):
            raw_path = payload.pop("path")
        elif isinstance(payload.get("endpoint"), str):
            raw_path = payload.pop("endpoint")
        elif isinstance(payload.get("url"), str):
            raw_path = payload.pop("url")

        if raw_path:
            sanitized = _sanitize_path(raw_path)
            if sanitized:
                payload["path_hash"] = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
    except Exception:
        # never fail telemetry building for hashing
        pass
    # Redact obvious secrets from headers
    if "request_headers" in payload:
        payload["request_headers"] = _redact_headers(payload["request_headers"])
    if "response_headers" in payload:
        payload["response_headers"] = _redact_headers(payload["response_headers"])

    base["payload"] = payload
    return base


def _sanitize_path(endpoint: Optional[str]) -> Optional[str]:
    if not endpoint:
        return None
    # Remove query params
    return endpoint.split("?")[0]


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    if not headers:
        return headers
    redacted = {}
    secret_keys = {"authorization", "cookie", "set-cookie", "x-refresh-token"}
    for k, v in headers.items():
        if k.lower() in secret_keys:
            redacted[k] = "REDACTED"
        else:
            redacted[k] = v
    return redacted


def _extract_sforce_client(call_options: Optional[str]) -> Optional[str]:
    """Extract `client` value from Sforce-Call-Options header like 'client=foo' or 'client=foo,other=bar'."""
    if not call_options:
        return None
    try:
        # split on commas and semicolons, look for client=...
        parts = re.split(r"[,;]", call_options)
        for p in parts:
            p = p.strip()
            if p.lower().startswith("client="):
                return p.split("=", 1)[1]
        return None
    except Exception:
        return None


def _sanitize_log_message(msg: Optional[str]) -> Optional[str]:
    if not msg:
        return msg
    try:
        # redact bearer tokens
        msg = re.sub(r"Bearer\s+\S+", "Bearer <REDACTED>", msg, flags=re.IGNORECASE)
        # redact long hex or token-like strings (20+ chars)
        msg = re.sub(r"[A-Fa-f0-9_-]{20,}", "<REDACTED>", msg)
        # redact emails
        msg = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<redacted-email>", msg)
        # remove urls
        msg = re.sub(r"https?://\S+", "<url>", msg)
        # truncate
        if len(msg) > 2000:
            msg = msg[:2000]
        return msg
    except Exception:
        return "<unavailable>"


class TelemetryLogHandler(logging.Handler):
    """Logging handler that forwards sanitized log records to telemetry when allowed.

    Only forwards when telemetry level==2 (Debug). Ignores
    records originating from the telemetry module to avoid recursion.
    """
    def emit(self, record: logging.LogRecord) -> None:
        try:
            # avoid forwarding telemetry module logs (prevents recursion)
            if record.name.startswith("sfq.telemetry"):
                return

            cfg = get_config()
            if not cfg.enabled() or int(cfg.level) != 2:
                return

            # build a compact sanitized message
            msg = self.format(record) if self.formatter else record.getMessage()
            sanitized = _sanitize_log_message(msg)

            payload_ctx = {
                "logger": record.name,
                "level": record.levelname,
                "message": sanitized,
                "module": record.module,
                "filename": record.filename,
                "lineno": record.lineno,
                "created": record.created,
            }

            # include exception text if present (sanitized)
            if record.exc_info:
                import traceback

                exc_text = "\n".join(traceback.format_exception(*record.exc_info))
                payload_ctx["exception"] = _sanitize_log_message(exc_text)

            # Emit as telemetry event (telemetry.emit will check sampling/level)
            try:
                emit("log.record", payload_ctx)
            except Exception:
                # never let logging failures break the app
                pass
        except Exception:
            # swallow all errors inside handler
            pass


def _maybe_register_log_handler() -> None:
    """Register the telemetry log handler when debug telemetry is enabled."""
    global _log_handler
    try:
        cfg = get_config()
        if not cfg.enabled() or int(cfg.level) != 2:
            return

        if _log_handler is not None:
            return

        handler = TelemetryLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        _log_handler = handler
        if _debug:
            _logger.debug("Telemetry log handler registered")
    except Exception:
        pass


class _Sender(threading.Thread):
    def __init__(self, endpoint: str, api_key: Optional[str]) -> None:
        super().__init__(daemon=True)
        self.endpoint = endpoint
        self.api_key = api_key
        self._q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=500)
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._post(item)
            except Exception:
                # Never let telemetry errors propagate
                pass
            finally:
                self._q.task_done()

    def stop(self) -> None:
        self._stop.set()

    def enqueue(self, event: Dict[str, Any]) -> None:
        try:
            self._q.put_nowait(event)
        except queue.Full:
            # drop telemetry if queue is full
            pass

    def _post(self, event: Dict[str, Any]) -> None:
        parsed = urlparse(self.endpoint)
        conn = None
        body = json.dumps(event).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = f"{self.api_key}"
        else:
            headers["X-API-Key"] = _SDK_VERSION

        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=5)
        else:
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)

        path = parsed.path or "/"
        if parsed.query:
            path = path + "?" + parsed.query

        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        # read and ignore response
        try:
            resp.read()
        finally:
            try:
                conn.close()
            except Exception:
                pass


# Module-level sender
_sender: Optional[_Sender] = None


def _ensure_sender() -> _Sender:
    global _sender
    if _sender is None:
        _sender = _Sender(_config.endpoint, _config.api_key)
        _sender.start()
    # register log handler if requested (best-effort)
    try:
        _maybe_register_log_handler()
    except Exception:
        pass
    return _sender


def emit(event_type: str, ctx: Dict[str, Any]) -> None:
    """Emit a telemetry event asynchronously respecting opt-in and sampling."""
    cfg = _config
    if not cfg.enabled():
        return

    if random.random() > cfg.sampling:
        return

    # safety: ensure integer level
    level = int(cfg.level)
    payload = _build_payload(event_type, ctx, level)

    sender = _ensure_sender()
    sender.enqueue(payload)


def shutdown(timeout: float = 2.0) -> None:
    """Attempt to stop the background sender (best-effort)."""
    global _sender
    if _sender is None:
        return
    try:
        if _debug:
            _logger.debug("Shutting down telemetry sender, waiting up to %s seconds", timeout)
        _sender.stop()
        _sender.join(timeout)
    except Exception:
        pass


# Ensure we attempt to flush telemetry on process exit
atexit.register(shutdown)
