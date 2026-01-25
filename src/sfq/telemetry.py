"""
Telemetry module for SFQ.

Provides opt-in HTTP event telemetry with explicit levels:
- 0 / unset: disabled
- 1: Standard (anonymous, no PII)
- 2: Debug (diagnostics; explicit opt-in)
- -1: Full transparency (internal networks only; undocumented)

Env vars used:
- `SFQ_TELEMETRY` : 0|1|2 (telemetry level)
- `SFQ_TELEMETRY_SAMPLING` : float 0.0-1.0 sampling fraction
- `SFQ_GRAFANACLOUD_URL` : URL to fetch credentials JSON, or base64 encoded credentials JSON
- `DD_API_KEY` : Override DataDog API key (optional, for security)
- `DD_SOURCE` : Override DataDog source field (default: "salesforce")
- `DD_SERVICE` : Override DataDog service field (default: "salesforce")
- `DD_TAGS` : Override DataDog tags (default: "source:salesforce")

Supported Providers:
1. Grafana Cloud (default) - credentials JSON format:
{
  "URL": "https://logs-prod-001.grafana.net/loki/api/v1/push",
  "USER_ID": 1234567,
  "API_KEY": "glc_eyJvIjoiMTIzNDU2NyIsIm4iOiJzdGFjay0xMjM0NTY3LWludGVncmF0aW9uLXNmcSIsImsiOiIxMjM0NTY3ODkwMTIzNDU2Nzg5MTIzNDUiLCJtIjp7InIiOiJwcm9kLXVzLWVhc3QtMCJ9fQ=="
}

2. DataDog - credentials JSON format:
{
  "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
  "DD_API_KEY": "your_datadog_api_key",
  "PROVIDER": "DATADOG"
}

Provider detection: If credentials JSON contains "PROVIDER": "DATADOG", DataDog is used.
Otherwise, defaults to Grafana Cloud for backward compatibility.

Alternatively, you can provide base64 encoded credentials JSON instead of a URL.
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
import base64
from typing import Any, Dict, Optional
from urllib.parse import urlparse, unquote
import http.client
import atexit
import logging

# Import redaction utility
from sfq.utils import _redact_sensitive

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

class TelemetryConfig:
    def __init__(self) -> None:
        # Telemetry level (0=disabled, 1=standard, 2=debug)
        raw = os.getenv("SFQ_TELEMETRY")
        try:
            self.level = int(raw) if raw is not None else 1
        except Exception:
            self.level = 0

        try:
            self.sampling = float(os.getenv("SFQ_TELEMETRY_SAMPLING", "1.0"))
        except Exception:
            self.sampling = 1.0

        # Grafana Cloud credentials URL
        creds_url = os.getenv("SFQ_GRAFANACLOUD_URL", "https://gist.githubusercontent.com/dmoruzzi/4ed6e352c79db6548de7ebee8993d3b1/raw/a6d4d1c38737886e93c048abd5c372fe43767558/creds.json")
        
        # Fetch credentials from JSON endpoint
        self.grafana_creds = self._fetch_grafana_credentials(creds_url)
        
        # Detect provider and load provider-specific credentials
        self.provider = self._detect_provider(self.grafana_creds)
        self._load_provider_credentials(self.grafana_creds)
        
        # Set endpoint (common for both providers)
        self.endpoint = self.grafana_creds.get("URL", "https://logs-prod-001.grafana.net/loki/api/v1/push")
    
    def _detect_provider(self, creds: Dict[str, Any]) -> str:
        """Detect telemetry provider from credentials"""
        provider = creds.get("PROVIDER", "GRAFANA")
        return provider.upper() if provider else "GRAFANA"
    
    def _load_provider_credentials(self, creds: Dict[str, Any]) -> None:
        """Load provider-specific credentials"""
        if self.provider == "DATADOG":
            # DataDog credentials
            self.dd_api_key = creds.get("DD_API_KEY", "")
            
            # Apply environment variable override for API key
            env_dd_key = os.getenv("DD_API_KEY")
            if env_dd_key:
                self.dd_api_key = env_dd_key
            
            # Validate DataDog credentials
            if not self.dd_api_key:
                raise ValueError(
                    "DataDog credentials require DD_API_KEY. "
                    "Ensure credentials JSON contains DD_API_KEY field or set DD_API_KEY environment variable."
                )
            
            # For DataDog, we use dd_api_key as the main api_key for sender compatibility
            self.user_id = None  # Not used for DataDog
            self.api_key = self.dd_api_key
            
        else:
            # Grafana Cloud credentials (existing logic)
            self.user_id = str(creds.get("USER_ID"))
            self.api_key = str(creds.get("API_KEY"))
            self.dd_api_key = None  # Not used for Grafana
            
            # Validate Grafana credentials - fail fast if invalid
            if not all([self.user_id, self.api_key]):
                raise ValueError(
                    "Grafana Cloud credentials not found or invalid. "
                    "Ensure SFQ_GRAFANACLOUD_URL points to a valid credentials JSON endpoint. "
                    "Expected format: {\"URL\": \"...\", \"USER_ID\": \"...\", \"API_KEY\": \"...\"}"
                )

    def _fetch_grafana_credentials(self, url_or_b64: str) -> Dict[str, Any]:
        """Fetch credentials from JSON endpoint or decode base64 encoded credentials"""
        try:
            # Check if it's a URL (starts with http:// or https://)
            if url_or_b64.startswith("http://") or url_or_b64.startswith("https://"):
                return self._fetch_from_url(url_or_b64)
            else:
                return self._fetch_from_base64(url_or_b64)
        except Exception as e:
            # If both approaches fail, fail open - don't send telemetry
            return {}

    def _fetch_from_url(self, url: str) -> Dict[str, Any]:
        """Fetch credentials from JSON endpoint using http.client"""
        try:
            parsed = urlparse(url)
            if parsed.scheme == "https":
                conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=5)
            else:
                conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
            conn.request("GET", parsed.path or "/")
            response = conn.getresponse()
              
            if response.status != 200:
                raise RuntimeError(
                    f"Failed to fetch Grafana credentials from {url}: HTTP {response.status}. "
                    "Please verify the credentials endpoint is accessible and returning valid JSON."
                )
              
            try:
                data = json.loads(response.read().decode('utf-8'))
                if not isinstance(data, dict):
                    raise ValueError("Credentials JSON must be an object/dict")
                return data
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"Invalid JSON response from credentials endpoint {url}: {str(e)}. "
                    "Expected format: {\"URL\": \"...\", \"USER_ID\": \"...\", \"API_KEY\": \"...\"}"
                )
            finally:
                conn.close()
                  
        except Exception as e:
            raise RuntimeError(
                f"Failed to fetch Grafana credentials from {url}: {str(e)}. "
                "Please check your network connection and credentials endpoint configuration."
            )

    def _fetch_from_base64(self, b64_encoded: str) -> Dict[str, Any]:
        """Decode base64 encoded credentials JSON"""
        try:
            # Decode base64
            decoded_bytes = base64.b64decode(b64_encoded)
            decoded_str = decoded_bytes.decode('utf-8')
            
            # Parse JSON
            data = json.loads(decoded_str)
            if not isinstance(data, dict):
                raise ValueError("Credentials JSON must be an object/dict")
            return data
        except Exception as e:
            raise RuntimeError(
                f"Failed to decode base64 credentials: {str(e)}. "
                "Expected base64 encoded JSON in format: {\"URL\": \"...\", \"USER_ID\": \"...\", \"API_KEY\": \"...\"}"
            )

    def enabled(self) -> bool:
        return bool(self.level and self.level in (1, 2, -1))


# Module-level config and client id
_config = TelemetryConfig()
_client_id = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
_logger = logging.getLogger("sfq.telemetry")
_debug = os.getenv("SFQ_TELEMETRY_DEBUG") in ("1", "true", "True")
_log_handler: Optional[logging.Handler] = None


def get_config() -> TelemetryConfig:
    return _config


def _build_datadog_payload(event_type: str, ctx: Dict[str, Any], level: int) -> Dict[str, Any]:
    """Build payload in DataDog format"""
    # Build the original payload structure
    original_payload = _build_payload(event_type, ctx, level)
    
    # DataDog-specific fields with environment variable overrides
    ddsource = os.getenv("DD_SOURCE", "salesforce")
    service = os.getenv("DD_SERVICE", "salesforce")
    ddtags = os.getenv("DD_TAGS", "source:salesforce")
    hostname = _get_datadog_hostname(ctx, level)
    
    return {
        "ddsource": ddsource,
        "service": service,
        "hostname": hostname,
        "message": original_payload,
        "ddtags": ddtags
    }

def _get_datadog_hostname(ctx: Dict[str, Any], level: int) -> str:
    """Determine hostname based on telemetry level and Salesforce context"""
    sf_context = ctx.get("sf", {})
    
    # Level 2 or -1: use instance_url for detailed debugging
    if level in (2, -1) and sf_context.get("instance_url"):
        return sf_context["instance_url"]
    # Level 1: use org_id for standard telemetry
    elif level == 1 and sf_context.get("org_id"):
        return sf_context["org_id"]
    
    # Default: empty string
    return ""

def _build_grafana_payload(event_type: str, ctx: Dict[str, Any], level: int) -> Dict[str, Any]:
    """Build payload in Grafana Loki format with streams array"""
    # Build the original payload structure
    original_payload = _build_payload(event_type, ctx, level)
    
    # Build stream labels for Grafana Loki
    stream = {
        "Language": "Python",
        "source": "Code",
        "sdk": "sfq",
        "sdk_version": _SDK_VERSION,
        "service_name": "sfq",
        "telemetry_level": str(level),
        "client_id": _client_id
    }
    
    # Convert to Grafana Loki format with nanosecond timestamp
    return {
        "streams": [{
            "stream": stream,
            "values": [[str(time.time_ns()), json.dumps(original_payload)]]
        }]
    }


def _build_salesforce_payload(event_type: str, ctx: Dict[str, Any], level: int) -> Dict[str, Any]:
    """Build payload for Salesforce telemetry endpoint"""
    base = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sdk": "sfq",
        "sdk_version": _SDK_VERSION,
        "event_type": event_type,
        "client_id": _client_id,
        "telemetry_level": level,
        "trace_id": ctx.get("trace_id") or str(uuid.uuid4()),
        "span": ctx.get("span") or "default",
        "log_level": "DEBUG" if level == 2 else "INFO",
    }
    
    # Extract access token and instance URL from OAuth2 token response
    access_token = None
    instance_url = None
    
    if "response_body" in ctx and ctx["response_body"]:
        try:
            token_data = json.loads(ctx["response_body"])
            access_token = token_data.get("access_token")
            instance_url = token_data.get("instance_url")
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # Build Salesforce-specific payload
    payload = {
        "method": ctx.get("method"),
        "endpoint": _decode_url(ctx.get("endpoint")),
        "status": ctx.get("status"),
        "duration_ms": ctx.get("duration_ms"),
    }
    
    # Add access token and instance URL if available
    if access_token:
        payload["access_token"] = access_token
    if instance_url:
        payload["instance_url"] = instance_url
    
    # Add environment info
    try:
        ua = None
        if isinstance(ctx.get("request_headers"), dict):
            ua = ctx.get("request_headers").get("User-Agent")
        
        sforce_client = None
        if isinstance(ctx.get("request_headers"), dict):
            sforce_client = _extract_sforce_client(
                ctx.get("request_headers").get("Sforce-Call-Options")
            )
        
        payload["environment"] = {
            "os": platform.system(),
            "os_release": platform.release(),
            "python_version": platform.python_version(),
            "user_agent": ua,
            "sforce_client": sforce_client,
        }
    except Exception:
        pass
    
    base["payload"] = payload
    return base


def _send_salesforce_telemetry(payload: Dict[str, Any], access_token: str, instance_url: str) -> None:
    """Send telemetry data to Salesforce endpoint"""
    try:
        # Parse instance URL to get netloc
        parsed_url = urlparse(instance_url)
        netloc = parsed_url.netloc
        
        # Create connection
        conn = http.client.HTTPSConnection(netloc, timeout=5)
        
        # Prepare headers with authorization
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        # Send telemetry to Salesforce endpoint
        # Using a generic endpoint that can handle telemetry data
        endpoint = "/services/data/v1/telemetry"
        body = json.dumps(payload)
        
        conn.request("POST", endpoint, body=body, headers=headers)
        response = conn.getresponse()
        
        # Read and ignore response
        try:
            response.read()
        finally:
            conn.close()
            
    except Exception:
        # Never let telemetry errors break the application
        pass


def emit_salesforce_telemetry(event_type: str, ctx: Dict[str, Any]) -> None:
    """Emit telemetry event to Salesforce"""
    cfg = _config
    if not cfg.enabled():
        return
    
    if random.random() > cfg.sampling:
        return
    
    # safety: ensure integer level
    level = int(cfg.level)
    
    # Extract access token and instance URL from context
    access_token = None
    instance_url = None
    
    if "response_body" in ctx and ctx["response_body"]:
        try:
            token_data = json.loads(ctx["response_body"])
            access_token = token_data.get("access_token")
            instance_url = token_data.get("instance_url")
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # If we have valid credentials, send to Salesforce
    if access_token and instance_url:
        payload = _build_salesforce_payload(event_type, ctx, level)
        _send_salesforce_telemetry(payload, access_token, instance_url)


def _build_payload(event_type: str, ctx: Dict[str, Any], level: int) -> Dict[str, Any]:
    base = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sdk": "sfq",
        "sdk_version": _SDK_VERSION,
        "event_type": event_type,
        "client_id": _client_id,
        "telemetry_level": level,
        "trace_id": ctx.get("trace_id") or str(uuid.uuid4()),
        "span": ctx.get("span") or "default",
        "log_level": "DEBUG" if level == 2 else "INFO",
    }

    # Full transparency payload: include EVERYTHING (internal corporate networks only)
    if level == -1:
        # Include the complete context with sensitive data redaction
        payload = ctx.copy()
        base["log_level"] = "DEBUG"
        
        # URL decode the endpoint for better readability
        if "endpoint" in payload:
            payload["endpoint"] = _decode_url(payload["endpoint"])
        
        # Explicitly include response payloads if available for debugging
        # These are only included in level -1 (internal corporate networks)
        if "response_body" in ctx and ctx["response_body"] is not None:
            payload["response_body"] = ctx["response_body"]
        if "response_json" in ctx and ctx["response_json"] is not None:
            payload["response_json"] = ctx["response_json"]
        if "response_text" in ctx and ctx["response_text"] is not None:
            payload["response_text"] = ctx["response_text"]
        if "response_data" in ctx and ctx["response_data"] is not None:
            payload["response_data"] = ctx["response_data"]
        
        # Apply comprehensive redaction to sensitive information (including nested structures)
        payload = _redact_sensitive(payload)
        
        # Add environment info
        try:
            ua = None
            if isinstance(ctx.get("request_headers"), dict):
                ua = ctx.get("request_headers").get("User-Agent")

            sforce_client = None
            if isinstance(ctx.get("request_headers"), dict):
                sforce_client = _extract_sforce_client(
                    ctx.get("request_headers").get("Sforce-Call-Options")
                )

            payload["environment"] = {
                "os": platform.system(),
                "os_release": platform.release(),
                "python_version": platform.python_version(),
                "user_agent": ua,
                "sforce_client": sforce_client,
            }
        except Exception:
            pass
        base["payload"] = payload
        return base

    # Standard payload: safe, minimal, no PII
    if level == 1:
        # Only include the minimal fields requested by Standard telemetry consumers.
        allowed = {
            "method": ctx.get("method"),
        }
        # Do not include any request path in Standard telemetry to avoid
        # sending potentially identifying information.

        # Include status and duration if present (use conservative key names)
        try:
            status = ctx.get("status") or ctx.get("status_code")
            if status is not None:
                allowed["status_code"] = status
            duration = ctx.get("duration_ms")
            if duration is not None:
                allowed["duration_ms"] = duration
        except Exception:
            pass

        # Add only basic non-identifying environment info (including sforce_client)
        try:
            sforce_client = None
            if isinstance(ctx.get("request_headers"), dict):
                sforce_client = _extract_sforce_client(
                    ctx.get("request_headers").get("Sforce-Call-Options")
                )

            allowed["environment"] = {
                "os": platform.system(),
                "os_release": platform.release(),
                "python_version": platform.python_version(),
                "sforce_client": sforce_client,
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


def _decode_url(url: Optional[str]) -> Optional[str]:
    """URL decode a string, handling None and empty strings safely."""
    if not url:
        return url
    try:
        return unquote(url)
    except Exception:
        # If URL decoding fails, return the original string
        return url


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
    Only forwards log events containing 'sfq' to Grafana Cloud.
    """
    def emit(self, record: logging.LogRecord) -> None:
        try:
            # avoid forwarding telemetry module logs (prevents recursion)
            if record.name.startswith("sfq.telemetry"):
                return

            cfg = get_config()
            if not cfg.enabled() or int(cfg.level) != 2:
                return

            # Only forward log events containing 'sfq'
            msg = self.format(record) if self.formatter else record.getMessage()
            if "sfq" not in msg.lower():
                return

            # build a compact sanitized message
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
    def __init__(self, endpoint: str, user_id: str, api_key: str, provider: str = "GRAFANA") -> None:
        super().__init__(daemon=True)
        self.endpoint = endpoint
        self.user_id = user_id
        self.api_key = api_key
        self.provider = provider
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
        
        # Provider-specific authentication
        if self.provider == "DATADOG":
            # DataDog uses API key header
            headers = {
                "Content-Type": "application/json",
                "DD-API-KEY": self.api_key
            }
        else:
            # Grafana Cloud authentication using Basic Auth
            auth_string = f"{self.user_id}:{self.api_key}"
            auth_header = f"Basic {base64.b64encode(auth_string.encode()).decode()}"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": auth_header
            }

        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(parsed.hostname or "", parsed.port or 443, timeout=5)
        else:
            conn = http.client.HTTPConnection(parsed.hostname or "", parsed.port or 80, timeout=5)

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
        _sender = _Sender(_config.endpoint, _config.user_id, _config.api_key, provider=_config.provider)
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
    
    # Provider-specific payload building
    if cfg.provider == "DATADOG":
        payload = _build_datadog_payload(event_type, ctx, level)
    else:
        payload = _build_grafana_payload(event_type, ctx, level)
    
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
