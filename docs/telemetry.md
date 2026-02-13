# Telemetry Guide

sfq collects anonymous usage telemetry to help improve the library. This guide explains how telemetry works and how to configure it.

## Overview

Telemetry is **enabled by default** with Standard level (non-PII, anonymized data). You can disable it or adjust the level at any time.

## Quick Configuration

```bash
# Disable telemetry entirely
export SFQ_TELEMETRY=0

# Enable Standard telemetry (default)
export SFQ_TELEMETRY=1

# Enable Debug telemetry (internal use only)
export SFQ_TELEMETRY=2
```

## Telemetry Levels

| Level    | Value | Description                                 | Use Case                           |
|----------|-------|---------------------------------------------|------------------------------------|
| Disabled | `0`   | No events sent                              | Complete privacy                   |
| Standard | `1`   | Anonymized, non-PII events                  | Default, safe for all environments |
| Debug    | `2`   | Diagnostic info, may include sensitive data | Internal troubleshooting only      |
| Full     | `-1`  | Complete request/response data              | Internal corporate networks only   |

### Standard Telemetry (Level 1)

Default level. Sends anonymized events containing:
- Method names (e.g., `query`, `cquery`)
- HTTP status codes
- Execution duration
- Environment info (OS, Python version)

**Does NOT include:**
- Request/response bodies
- Tokens or credentials
- Record IDs or user identifiers
- Query contents

Example event:
```json
{
    "timestamp": "2026-01-19T09:21:05Z",
    "sdk": "sfq",
    "sdk_version": "0.0.56",
    "event_type": "http.request",
    "telemetry_level": 1,
    "payload": {
        "method": "GET",
        "status_code": 200,
        "duration_ms": 174,
        "environment": {
            "os": "Windows",
            "python_version": "3.11.0"
        }
    }
}
```

### Debug Telemetry (Level 2)

Includes additional diagnostic information. **Use with internal endpoints only** as it may contain:
- Request headers (with sensitive values redacted)
- Path hashes
- Stack traces on errors

Enable for troubleshooting:
```bash
export SFQ_TELEMETRY=2
export SFQ_TELEMETRY_ENDPOINT=https://your-internal-endpoint.com/telemetry
```

## Configuration Options

| Variable                 | Description                              | Default       |
|--------------------------|------------------------------------------|---------------|
| `SFQ_TELEMETRY`          | Telemetry level (`0`, `1`, `2`, `-1`)    | `1`           |
| `SFQ_TELEMETRY_ENDPOINT` | Custom endpoint URL                      | Grafana Cloud |
| `SFQ_TELEMETRY_SAMPLING` | Fraction of events to send (`0.0`-`1.0`) | `1.0`         |
| `SFQ_TELEMETRY_KEY`      | Bearer token for endpoint                | None          |

## Destinations

### Grafana Cloud (Default)

Standard telemetry sends to Grafana Cloud Loki. No configuration required.

### DataDog

Configure DataDog as the destination:

```bash
export SFQ_GRAFANACLOUD_URL=https://your-datadog-endpoint.com/creds.json
```

Or provide credentials directly (base64 encoded):
```bash
export SFQ_GRAFANACLOUD_URL="$(echo '{"URL": "https://http-intake.logs.datadoghq.com/api/v2/logs", "DD_API_KEY": "your-key", "PROVIDER": "DATADOG"}' | base64)"
```

DataDog-specific overrides:
```bash
export DD_API_KEY="your-api-key"
export DD_SOURCE="salesforce"
export DD_SERVICE="my-app"
export DD_TAGS="env:prod,team:backend"
```

### Custom Endpoint

Route telemetry to your own endpoint:
```bash
export SFQ_TELEMETRY_ENDPOINT=https://your-telemetry.com/ingest
export SFQ_TELEMETRY_KEY="your-auth-token"
```

## Sampling

Reduce telemetry volume by sampling a fraction of events:

```bash
# Send only 10% of events
export SFQ_TELEMETRY_SAMPLING=0.1
```

## Privacy

- **Opt-out**: Set `SFQ_TELEMETRY=0` to disable completely
- **No PII in Standard mode**: User data, tokens, and identifiers are never included
- **Client ID**: A random SHA-256 hash generated at runtime, not traceable to users or orgs
- **Transparent**: Full source code available for review

## Field Reference

| Field                 | Description                           |
|-----------------------|---------------------------------------|
| `timestamp`           | ISO 8601 UTC timestamp                |
| `sdk`                 | Always `sfq`                          |
| `sdk_version`         | Library version                       |
| `event_type`          | Event category (e.g., `http.request`) |
| `client_id`           | Anonymous runtime identifier          |
| `telemetry_level`     | Current level setting                 |
| `trace_id`            | Correlation ID for related events     |
| `payload.method`      | HTTP method                           |
| `payload.status_code` | HTTP response code                    |
| `payload.duration_ms` | Operation duration                    |
