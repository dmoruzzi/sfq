"""
Utility functions and logging configuration for the SFQ library.

This module contains shared utilities, logging configuration, and helper functions
used throughout the SFQ library, including the custom TRACE logging level and
sensitive data redaction functionality.
"""

import base64
import hashlib
import json
import logging
import re
from html import escape
from typing import Any, Dict, List, Tuple, Union

# Custom TRACE logging level
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def _redact_sensitive(data: Any) -> Any:
    """
    Redacts sensitive keys from a dictionary, query string, or sessionId.

    This function recursively processes data structures to remove or mask
    sensitive information like tokens, passwords, and session IDs.

    :param data: The data to redact (dict, list, tuple, or string)
    :return: The data with sensitive information redacted
    """
    REDACT_VALUE = "*" * 8
    REDACT_KEYS = [
        "access_token",
        "authorization",
        "set-cookie",
        "cookie",
        "refresh_token",
        "client_secret",
        "sessionid",
    ]

    if isinstance(data, dict):
        return {
            k: (REDACT_VALUE if k.lower() in REDACT_KEYS else v)
            for k, v in data.items()
        }
    elif isinstance(data, (list, tuple)):
        return type(data)(
            (
                (item[0], REDACT_VALUE)
                if isinstance(item, tuple) and item[0].lower() in REDACT_KEYS
                else item
                for item in data
            )
        )
    elif isinstance(data, str):
        data = re.sub(
            r"(<[a-zA-Z0-9_]*:?sessionId>)(.*?)(</[a-zA-Z0-9_]*:?sessionId>)",
            r"\1{}\3".format(REDACT_VALUE),
            data,
        )
        data = re.sub(
            r"(<[a-zA-Z0-9_]*:?sessionId>)(.*?)(</[a-zA-Z0-9_]*:?sessionId>)",
            r"\1{}\3".format(REDACT_VALUE),
            data,
        )
        # Redact query string parameters
        parts = data.split("&")
        for i, part in enumerate(parts):
            if "=" in part:
                key, value = part.split("=", 1)
                if key.lower() in REDACT_KEYS:
                    parts[i] = f"{key}={REDACT_VALUE}"
        return "&".join(parts)

    return data


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """
    Custom TRACE level logging function with redaction.

    This function adds a custom TRACE logging level that automatically
    redacts sensitive information from log messages.

    :param self: The logger instance
    :param message: The log message
    :param args: Additional arguments for the log message
    :param kwargs: Additional keyword arguments for logging
    """
    redacted_args = args
    if args:
        first = args[0]
        if isinstance(first, str):
            try:
                loaded = json.loads(first)
                first = loaded
            except (json.JSONDecodeError, TypeError):
                pass
        redacted_first = _redact_sensitive(first)
        redacted_args = (redacted_first,) + args[1:]

    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, redacted_args, **kwargs)


# Add the trace method to the Logger class
logging.Logger.trace = trace


def get_logger(name: str = "sfq") -> logging.Logger:
    """
    Get a logger instance with the custom TRACE level configured.

    :param name: The logger name (defaults to "sfq")
    :return: Configured logger instance
    """
    return logging.getLogger(name)


def format_headers_for_logging(
    headers: Union[Dict[str, str], List[Tuple[str, str]]],
) -> List[Tuple[str, str]]:
    """
    Format headers for logging, filtering out sensitive browser information.

    :param headers: Headers as dict or list of tuples
    :return: Filtered list of header tuples suitable for logging
    """
    if isinstance(headers, dict):
        headers_list = list(headers.items())
    else:
        headers_list = list(headers)

    # Filter out BrowserId cookies and other sensitive headers
    return [(k, v) for k, v in headers_list if not v.startswith("BrowserId=")]


def parse_api_usage_from_header(sforce_limit_info: str) -> Tuple[int, int, float]:
    """
    Parse API usage information from Sforce-Limit-Info header.

    :param sforce_limit_info: The Sforce-Limit-Info header value
    :return: Tuple of (current_calls, max_calls, usage_percentage)
    """
    try:
        # Expected format: "api-usage=123/15000"
        usage_part = sforce_limit_info.split("=")[1]
        current_api_calls = int(usage_part.split("/")[0])
        maximum_api_calls = int(usage_part.split("/")[1])
        usage_percentage = round(current_api_calls / maximum_api_calls * 100, 2)
        return current_api_calls, maximum_api_calls, usage_percentage
    except (IndexError, ValueError, ZeroDivisionError) as e:
        logger = get_logger()
        logger.warning("Failed to parse API usage from header: %s", e)
        return 0, 0, 0.0


def log_api_usage(sforce_limit_info: str, high_usage_threshold: int = 80) -> None:
    """
    Log API usage information with appropriate warning levels.

    :param sforce_limit_info: The Sforce-Limit-Info header value
    :param high_usage_threshold: Threshold percentage for high usage warning
    """
    logger = get_logger()
    current_calls, max_calls, usage_percentage = parse_api_usage_from_header(
        sforce_limit_info
    )

    if usage_percentage > high_usage_threshold:
        logger.warning(
            "High API usage: %s/%s (%s%%)",
            current_calls,
            max_calls,
            usage_percentage,
        )
    else:
        logger.debug(
            "API usage: %s/%s (%s%%)",
            current_calls,
            max_calls,
            usage_percentage,
        )


def extract_org_and_user_ids(token_id_url: str) -> Tuple[str, str]:
    """
    Extract organization and user IDs from the token response ID URL.

    :param token_id_url: The ID URL from the token response
    :return: Tuple of (org_id, user_id)
    :raises ValueError: If the URL format is invalid
    """
    try:
        parts = token_id_url.split("/")
        org_id = parts[4]
        user_id = parts[5]
        return org_id, user_id
    except (IndexError, AttributeError):
        raise ValueError(f"Invalid token ID URL format: {token_id_url}")


def dicts_to_html_table(items: List[Dict[str, Any]], styled: bool = False) -> str:
    """
    Convert a list of dictionaries to a compact HTML table.

    :param items: List of dictionaries to convert
    :param styled: If True, apply minimal inline CSS for compact styling
    :return: HTML string for a table with one column per key.
    :raises ValueError: If input is not a list of dictionaries, or if keys are invalid types.
    """
    if not isinstance(items, list):
        raise ValueError("Input must be a list of dictionaries.")

    def render_value(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, (int, float, str, bool)):
            return str(val)
        if isinstance(val, list):
            return (
                "<ul>"
                + "".join(f"<li>{render_value(item)}</li>" for item in val)
                + "</ul>"
            )
        if isinstance(val, dict):
            return dicts_to_html_table([val], styled=styled)
        try:
            dumped = json.dumps(val, default=str)
            if dumped.startswith('"') and dumped.endswith('"'):
                dumped = dumped[1:-1]
            return escape(dumped)
        except Exception:
            return escape(str(val))

    # Preserve key order by first appearance
    columns: List[str] = []
    seen = set()
    for i, d in enumerate(items):
        if not isinstance(d, dict):
            raise ValueError(f"Element at index {i} is not a dictionary.")
        for k in d.keys():
            k_str = (
                k
                if isinstance(k, str)
                else str(k)
                if isinstance(k, (int, float, bool))
                else None
            )
            if k_str is None:
                raise ValueError(f"Dictionary at index {i} has a non-string key: {k!r}")
            if k_str not in seen:
                columns.append(k_str)
                seen.add(k_str)

    # Build table
    def get_value_by_str_key(d: Dict[Any, Any], col: str) -> Any:
        for k in d.keys():
            k_str = (
                k
                if isinstance(k, str)
                else str(k)
                if isinstance(k, (int, float, bool))
                else None
            )
            if k_str == col:
                return d[k]
        return ""

    if styled:
        table_style = (
            "border-collapse:collapse;font-size:12px;line-height:1.2;"
            "margin:0;padding:0;width:auto;"
        )
        td_style = "border:1px solid #ccc;padding:2px 6px;vertical-align:top;"
        th_style = (
            "border:1px solid #ccc;padding:2px 6px;background:#f8f8f8;font-weight:bold;"
        )
        if columns:
            html = [f'<table style="{table_style}"><thead><tr>']
            html.extend(f'<th style="{th_style}">{col}</th>' for col in columns)
            html.append("</tr></thead><tbody>")
            for d in items:
                html.append("<tr>")
                html.extend(
                    f'<td style="{td_style}">{render_value(get_value_by_str_key(d, col))}</td>'
                    for col in columns
                )
                html.append("</tr>")
            html.append("</tbody></table>")
        else:
            html = [
                f'<table style="{table_style}"><thead></thead><tbody></tbody></table>'
            ]
    else:
        if columns:
            html = ["<table><thead><tr>"]
            html.extend(f"<th>{col}</th>" for col in columns)
            html.append("</tr></thead><tbody>")
            for d in items:
                html.append("<tr>")
                html.extend(
                    f"<td>{render_value(get_value_by_str_key(d, col))}</td>"
                    for col in columns
                )
                html.append("</tr>")
            html.append("</tbody></table>")
        else:
            html = ["<table><thead></thead><tbody></tbody></table>"]

    return "".join(html)


def flatten_dict(d, parent_key="", sep="."):
    """Recursively flatten a dictionary with dot notation."""
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def remove_attributes(obj):
    """Recursively remove 'attributes' key from dicts/lists."""
    if isinstance(obj, dict):
        return {k: remove_attributes(v) for k, v in obj.items() if k != "attributes"}
    elif isinstance(obj, list):
        return [remove_attributes(item) for item in obj]
    else:
        return obj


def records_to_html_table(
    records: List[Dict[str, Any]], headers: Dict[str, str] = None, styled: bool = False
) -> str:
    if not isinstance(records, list):
        raise ValueError("records must be a list of dictionaries")

    cleaned = remove_attributes(records)

    flat_rows = []
    for record in cleaned:
        if not isinstance(record, dict):
            raise ValueError(f"Record is not a dictionary: {record!r}")
        flat_rows.append(flatten_dict(record))

    # Preserve column order across all rows
    seen = set()
    ordered_columns = []
    for row in flat_rows:
        for key in row.keys():
            if key not in seen:
                ordered_columns.append(key)
                seen.add(key)

    # headers optionally remaps flattened field names to user-friendly display names
    if headers is None:
        headers = {}
        for col in ordered_columns:
            headers[col] = col
    else:
        for col in ordered_columns:
            headers[col] = headers.get(col, col)

    # Normalize rows so all have the same keys, using remapped column names
    normalized_data = []
    for row in flat_rows:
        normalized_row = {
            headers.get(col, col): (
                "" if row.get(col, None) is None else row.get(col, "")
            )
            for col in ordered_columns
        }
        normalized_data.append(normalized_row)

    return dicts_to_html_table(normalized_data, styled=styled)


def fuzz(text: str, key: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """Lightweight XOR-based obfuscation with variable hash prefix/suffix (no separators).
    
    Args:
        text: The text to obfuscate
        key: The key for XOR operation
        prefix_len: Length of the MD5 hash prefix (default: 4)
        suffix_len: Length of the SHA1 hash suffix (default: 4)
        
    Returns:
        Base64 encoded obfuscated string
    """

    prefix = hashlib.md5(text.encode()).hexdigest()[:prefix_len]
    suffix = hashlib.sha1(text.encode()).hexdigest()[-suffix_len:] if suffix_len > 0 else ""

    if not key:
        combined = prefix + text + suffix
    else:
        fuzzed_chars = [
            chr(ord(char) ^ ord(key[i % len(key)])) for i, char in enumerate(text)
        ]
        combined = prefix + ''.join(fuzzed_chars) + suffix

    encoded = base64.b64encode(combined.encode("utf-8")).decode("utf-8")
    return encoded


def defuzz(encoded_text: str, key: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """Reverse the fuzz transformation (no separators).
    
    Args:
        encoded_text: The base64 encoded obfuscated text
        key: The key used for original XOR operation
        prefix_len: Length of the MD5 hash prefix (must match encoding)
        suffix_len: Length of the SHA1 hash suffix (must match encoding)
        
    Returns:
        The original decoded text
        
    Raises:
        ValueError: If encoded text format is invalid or corrupted
    """

    decoded = base64.b64decode(encoded_text.encode("utf-8")).decode("utf-8")

    if len(decoded) < prefix_len + suffix_len:
        raise ValueError("Invalid encoded text format or corrupted data.")

    prefix = decoded[:prefix_len]
    suffix = decoded[-suffix_len:] if suffix_len > 0 else ""
    body = decoded[prefix_len:-suffix_len] if suffix_len > 0 else decoded[prefix_len:]

    if len(prefix) != prefix_len or len(suffix) != suffix_len:
        raise ValueError("Prefix/suffix length mismatch or corrupted data.")

    if not key:
        return body

    defuzzed_chars = [
        chr(ord(char) ^ ord(key[i % len(key)])) for i, char in enumerate(body)
    ]

    return ''.join(defuzzed_chars)
