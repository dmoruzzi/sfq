"""
Utility functions and logging configuration for the SFQ library.

This module contains shared utilities, logging configuration, and helper functions
used throughout the SFQ library, including the custom TRACE logging level and
sensitive data redaction functionality.
"""

import json
import logging
import re
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
        # Redact sessionId in XML
        if "<sessionId>" in data and "</sessionId>" in data:
            data = re.sub(
                r"(<sessionId>)(.*?)(</sessionId>)",
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
