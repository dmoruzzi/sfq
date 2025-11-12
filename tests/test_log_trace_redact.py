import logging
import os
from io import StringIO

import pytest

from sfq import SFAuth


@pytest.fixture(scope="module")
def sf_instance():
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    sf = SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )
    return sf


@pytest.fixture
def capture_logs():
    """
    Fixture to capture logs emitted to 'sfq' logger at TRACE level.
    """
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(5)

    logger = logging.getLogger("sfq")
    original_level = logger.level
    original_handlers = logger.handlers[:]

    logger.setLevel(5)
    for h in original_handlers:
        logger.removeHandler(h)
    logger.addHandler(handler)

    yield logger, log_stream

    # Teardown - restore original handlers and level
    logger.removeHandler(handler)
    for h in original_handlers:
        logger.addHandler(h)
    logger.setLevel(original_level)


def test_access_token_redacted_in_logs(sf_instance, capture_logs):
    """
    Ensure access tokens are redacted in log output to prevent leakage.
    """
    logger, log_stream = capture_logs

    # Trigger token refresh to get access token and logging
    sf_instance._refresh_token_if_needed()

    logger.handlers[0].flush()
    log_contents = log_stream.getvalue()

    # The test should verify that access tokens are being logged AND redacted
    assert "access_token" in log_contents, (
        "Expected access_token key in logs for redaction testing"
    )
    assert "'access_token': '********'," in log_contents, (
        "Access token was not properly redacted in logs"
    )


def test_soap_sessionid_redacted_in_logs(sf_instance, capture_logs):
    """
    Ensure SOAP sessionId is redacted in log output to prevent leakage.
    """
    logger, log_stream = capture_logs

    # Generate SOAP header using the public method
    soap_header = sf_instance._gen_soap_header()
    logger.trace("SOAP header payload: %s", soap_header)

    logger.handlers[0].flush()
    log_contents = log_stream.getvalue()

    assert "<sessionId>" in log_contents, "Expected <sessionId> tag in logs"
    assert f"<sessionId>{'*' * 8}</sessionId>" in log_contents, (
        "SOAP sessionId was not properly redacted in logs"
    )


def test_soap_create_redaction(sf_instance, capture_logs):
    """
    Ensure SOAP create operation does not leak sensitive information in logs.
    """
    logger, log_stream = capture_logs

    # Use the private _create method which delegates to the CRUD client
    create_response = sf_instance._create("Account", [{"Name": "Test Account"}])
    logger.trace("Creating Account: %s", create_response)

    # If create_response is None, it means authentication failed or no credentials
    if create_response is None:
        pytest.skip(
            "Skipping SOAP create redaction test - no valid credentials or authentication failed"
        )

    created_ids = [
        item["id"]
        for item in create_response
        if item.get("success") is True and "id" in item
    ]

    if created_ids:
        del_response = sf_instance.cdelete(created_ids)
        logger.trace("Deleting created Account: %s", del_response)

    logger.handlers[0].flush()
    log_contents = log_stream.getvalue()

    for acc_id in created_ids:
        assert acc_id in log_contents, f"Expected account ID {acc_id} in logs"

    assert "<sessionId>" in log_contents, (
        "SOAP sessionId should be logged, but redacted"
    )
    assert f"<sessionId>{'*' * 8}</sessionId>" in log_contents, (
        "SOAP sessionId should be logged in redacted form, but was not"
    )

    assert "access_token" not in log_contents, "Access token should not be logged"


def test_metadata_retrieve_redaction(sf_instance, capture_logs):
    """
    Ensure Metadata API retrieve operation does not leak sensitive information in logs.
    """
    logger, log_stream = capture_logs

    retrieve_response = sf_instance.mdapi_retrieve(["ApexComponent"])
    logger.trace("Metadata retrieve response: %s", retrieve_response)

    logger.handlers[0].flush()
    log_contents = log_stream.getvalue()

    assert "<met:sessionId>" in log_contents, (
        "SOAP sessionId should be present in logs for metadata retrieve"
    )
    assert f"<met:sessionId>{'*' * 8}</met:sessionId>" in log_contents, (
        "SOAP sessionId should be redacted as 8 asterisks in metadata retrieve logs"
    )

    # Access tokens must never be exposed
    assert "access_token" not in log_contents, (
        "Access token should not be logged in metadata retrieve traces"
    )
