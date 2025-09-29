"""
End-to-end tests for the PlatformEventsClient in the SFQ library.

These tests verify listing, publishing, and subscribing to Platform Events
using a live Salesforce org. Requires environment variables for authentication
and an org with 'sfq__e' custom Platform Event configured.
"""

import os
import time
from datetime import datetime

import logging
from queue import Queue
from threading import Thread

import pytest
from sfq import SFAuth as Client
from sfq.utils import get_logger

logger = get_logger(__name__)


@pytest.fixture(scope="module")
def sf_client():
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    client = Client(
        instance_url=os.getenv("SF_INSTANCE_URL") or "",
        client_id=os.getenv("SF_CLIENT_ID") or "",
        client_secret=(os.getenv("SF_CLIENT_SECRET") or "").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN") or "",
    )

    client._refresh_token_if_needed()

    # Test auth
    if not client.access_token:
        pytest.fail("Failed to authenticate with Salesforce")

    return client


def test_list_events(sf_client):
    """Test listing available Platform Events includes sfq__e"""
    events = sf_client.list_events()
    assert events is not None
    assert isinstance(events, list)
    assert 'sfq__e' in events, f"Expected 'sfq__e' in {events}"


def test_publish_single(sf_client):
    """Test publishing a single Platform Event"""
    event_data = {"text__c": f"Single test at {datetime.now().isoformat()}"}
    result = sf_client.publish("sfq__e", event_data)
    
    assert result is not None
    assert isinstance(result, dict)
    assert result.get('success') is True
    assert 'id' in result
    assert len(result['id']) == 18  # Salesforce ID length


def test_publish_batch(sf_client):
    """Test publishing a batch of Platform Events"""
    events = [
        {"text__c": f"Batch 1 at {datetime.now().isoformat()}"},
        {"text__c": f"Batch 2 at {datetime.now().isoformat()}"},
    ]
    result = sf_client.publish_batch(events, "sfq__e")
    
    assert result is not None
    assert isinstance(result, dict)
    assert 'results' in result
    assert len(result['results']) == 2
    for r in result['results']:
        assert r.get('success') is True
        assert 'id' in r


def test_subscribe_captures_published_event(sf_client):
    """Test subscribing captures a recently published event (E2E with timing)"""
    # Create a second client for publishing
    second_client = Client(
        instance_url=os.getenv("SF_INSTANCE_URL") or "",
        client_id=os.getenv("SF_CLIENT_ID") or "",
        client_secret=(os.getenv("SF_CLIENT_SECRET") or "").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN") or "",
    )
    second_client._refresh_token_if_needed()

    if not second_client.access_token:
        pytest.fail("Second client failed to authenticate")

    events_received = []

    def collect_events():
        try:
            print("Starting subscription...")
            gen = sf_client._subscribe("sfq__e", queue_timeout=3, max_runtime=20)
            count = 0
            for event in gen:
                print(f"Received event {count + 1}: {event}")
                events_received.append(event)
                count += 1
                if count >= 1:
                    print("Got 1 event, breaking")
                    break
        except Exception as e:
            print(f"Subscription error: {e}")
            logger.error(f"Subscription error: {e}")

    # Start subscription in thread
    subscription_thread = Thread(target=collect_events)
    subscription_thread.daemon = True
    subscription_thread.start()

    print("Subscription thread started")
    time.sleep(3)  # Wait for handshake

    # Publish from second client
    event_data = {"text__c": f"Subscribe test at {datetime.now().isoformat()}"}
    print("Publishing event...")
    publish_result = second_client.publish("sfq__e", event_data)
    print(f"Publish result: {publish_result}")

    # Wait for potential event
    time.sleep(8)

    # Stop subscription
    print("Stopping subscription...")
    subscription_thread.join(timeout=5)

    print(f"Total events received: {len(events_received)}")
    for e in events_received:
        print(e)

    assert len(events_received) >= 1, f"No events received. Got {len(events_received)} events"
    assert 'data' in events_received[0]
    assert 'channel' in events_received[0]
    assert events_received[0]['channel'].endswith('/sfq__e')
