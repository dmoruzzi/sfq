"""
Platform Events client module for the SFQ library.

This module provides operations for Salesforce Platform Events including
listing available events, publishing events, and subscribing to events
using the Streaming API.
"""

import json
import http.client
import time
import warnings
from queue import Empty, Queue
from urllib.parse import urlparse

from typing import Any, Dict, Generator, List, Optional

from .http_client import HTTPClient
from .query import QueryClient
from .utils import get_logger

logger = get_logger(__name__)


class PlatformEventsClient:
    """
    Manages Platform Events operations for Salesforce API communication.

    This class encapsulates listing available Platform Events, publishing
    event records, and subscribing to real-time events via CometD streaming.
    Platform Events must end with the `__e` suffix for custom events.
    """

    def __init__(
        self,
        http_client: HTTPClient,
        api_version: str,
    ) -> None:
        """
        Initialize the PlatformEventsClient with HTTP client and API version.

        :param http_client: HTTPClient instance for making requests
        :param api_version: Salesforce API version to use
        """
        self.http_client = http_client
        self.api_version = api_version
        self.query_client = QueryClient(self.http_client, api_version=self.api_version)

    def list_events(self) -> Optional[List[str]]:
        """
        List all available Platform Events in the Salesforce org.

        Uses the REST API to get all sObjects and filter those ending with '__e'.

        :return: List of event names or None on failure
        """
        endpoint = f"/services/data/{self.api_version}/sobjects/"

        status_code, data = self.http_client.send_authenticated_request(
            method="GET",
            endpoint=endpoint,
        )

        if status_code != 200 or not data:
            logger.error("Failed to query for sObjects: HTTP %s - %s", status_code, data)
            return None

        try:
            response = json.loads(data)
            sobjects = response.get("sobjects", [])
            events = [sobj["name"] for sobj in sobjects if sobj["name"].endswith("__e")]

            logger.debug("Retrieved %d Platform Events: %r", len(events), events)
            return events
        except json.JSONDecodeError as e:
            logger.error("Failed to parse sObjects response: %s", e)
            return None

    def publish(
        self,
        event_name: str,
        event_data: Dict[str, Any],
        batch_size: int = 200,
    ) -> Optional[Dict[str, Any]]:
        """
        Publish a single or batch of Platform Events via REST API.

        Posts event data to /sobjects/{EventName}__e. Supports batching
        for multiple events by passing a list in event_data under 'records'.

        :param event_name: The Platform Event API name (e.g., 'MyEvent__e')
        :param event_data: Dict of field-value pairs or {'records': [list of dicts]}
        :param batch_size: Batch size for composite API (default 200)
        :return: Response dict or None on failure
        """
        if not event_name.endswith("__e"):
            logger.error("Event name must end with '__e': %s", event_name)
            return None

        sobject = event_name
        records = event_data.get("records", [event_data]) if isinstance(event_data, dict) else [event_data]

        endpoint = f"/services/data/{self.api_version}/sobjects/{sobject}"

        # For single event, direct POST
        if len(records) == 1:
            status_code, data = self.http_client.send_authenticated_request(
                method="POST",
                endpoint=endpoint,
                body=json.dumps(records[0]),
            )
            if status_code == 201 and data:
                result = json.loads(data)
                logger.debug("Published event '%s': %r", event_name, result)
                return result
            else:
                logger.error("Publish failed for '%s': HTTP %s - %s", event_name, status_code, data)
                return None

        # For batch, use composite/tree or loop with threading (simple loop for now)
        results = []
        for record in records:
            status_code, data = self.http_client.send_authenticated_request(
                method="POST",
                endpoint=endpoint,
                body=json.dumps(record),
            )
            if status_code == 201 and data:
                results.append(json.loads(data))
            else:
                logger.warning("Failed to publish record in batch: HTTP %s - %s", status_code, data)
                results.append({"error": data or f"HTTP {status_code}"})

        logger.debug("Published batch of %d events for '%s'", len(results), event_name)
        return {"results": results}

    def publish_batch(
        self,
        events: List[Dict[str, Any]],
        event_name: str,
        batch_size: int = 200,
        max_workers: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Publish multiple Platform Events in batches with optional threading.

        :param events: List of event data dicts
        :param event_name: The Platform Event API name
        :param batch_size: Records per batch
        :param max_workers: Max threads for concurrent publishes
        :return: Dict of results or None on failure
        """
        if not event_name.endswith("__e"):
            logger.error("Event name must end with '__e': %s", event_name)
            return None

        # Reuse publish logic but force batch mode
        batch_data = {"records": events}
        return self.publish(event_name, batch_data, batch_size)

    def subscribe(
        self,
        event_name: str,
        queue_timeout: int = 90,
        max_runtime: Optional[int] = 10,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Subscribe to a Platform Event topic and yield incoming events.

        Uses the CometD long-polling Streaming API. Topic format:
        '/event/{EventName}'.

        :param event_name: The Platform Event API name (e.g., 'MyEvent__e')
        :param queue_timeout: Seconds to wait for messages before heartbeat log
        :param max_runtime: Max seconds to listen (None for unlimited)
        :yields: Event dicts with channel and data
        """
        if not event_name.endswith("__e"):
            logger.error("Event name must end with '__e': %s", event_name)
            return

        topic = f"/event/{event_name}"

        # Refresh token
        self.http_client.refresh_token_and_update_auth()

        if not self.http_client.auth_manager.access_token:
            logger.error("No access token available for event stream.")
            return

        start_time = time.time()
        message_queue = Queue()
        msg_count = 0

        instance_url = self.http_client.auth_manager.instance_url
        api_version = self.api_version
        user_agent = self.http_client.user_agent
        sforce_client = self.http_client.sforce_client

        headers = {
            "Authorization": f"Bearer {self.http_client.auth_manager.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": user_agent,
            "Sforce-Call-Options": f"client={sforce_client}",
        }

        parsed_url = urlparse(instance_url)
        conn = http.client.HTTPSConnection(parsed_url.netloc)
        _API_VERSION = api_version.removeprefix("v")
        client_id = ""

        try:
            logger.debug("Starting handshake with Salesforce CometD server.")
            handshake_payload = json.dumps(
                {
                    "id": str(msg_count + 1),
                    "version": "1.0",
                    "minimumVersion": "1.0",
                    "channel": "/meta/handshake",
                    "supportedConnectionTypes": ["long-polling"],
                    "advice": {"timeout": 60000, "interval": 0},
                }
            )
            conn.request(
                "POST",
                f"/cometd/{_API_VERSION}/meta/handshake",
                body=handshake_payload,
                headers=headers,
            )
            response = conn.getresponse()
            if response.status != 200:
                logger.error("Handshake failed: HTTP %d", response.status)
                return
            hand_data = json.loads(response.read().decode("utf-8"))
            if not hand_data or not hand_data[0].get("successful"):
                logger.error("Handshake failed: %s", hand_data)
                return

            client_id = hand_data[0]["clientId"]
            # Extract cookie from handshake response
            for name, value in response.getheaders():
                if name.lower() == "set-cookie" and "BAYEUX_BROWSER=" in value:
                    _bayeux_browser_cookie = value.split("BAYEUX_BROWSER=")[1].split(";")[0]
                    headers["Cookie"] = f"BAYEUX_BROWSER={_bayeux_browser_cookie}"
                    break

            logger.debug(f"Handshake successful, client ID: {client_id}")

            logger.debug(f"Subscribing to topic: {topic}")
            subscribe_message = {
                "channel": "/meta/subscribe",
                "clientId": client_id,
                "subscription": topic,
                "id": str(msg_count + 1),
            }
            conn.request(
                "POST",
                f"/cometd/{_API_VERSION}/subscribe",
                body=json.dumps(subscribe_message),
                headers=headers,
            )
            response = conn.getresponse()
            if response.status != 200:
                logger.error("Subscription failed: HTTP %d", response.status)
                return
            sub_response = json.loads(response.read().decode("utf-8"))
            if not sub_response or not sub_response[0].get("successful"):
                logger.error("Subscription failed: %s", sub_response)
                return

            # Check for cookie in subscribe response headers
            for name, value in response.getheaders():
                if name.lower() == "set-cookie" and "BAYEUX_BROWSER=" in value:
                    bayeux = value.split("BAYEUX_BROWSER=")[1].split(";")[0]
                    headers["Cookie"] = f"BAYEUX_BROWSER={bayeux}"
                    break

            logger.info(f"Successfully subscribed to topic: {topic}")

            while True:
                if max_runtime and (time.time() - start_time > max_runtime):
                    logger.info(f"Disconnecting after max_runtime={max_runtime} seconds")
                    break

                logger.debug("Sending connection message.")
                connect_payload = json.dumps(
                    [
                        {
                            "channel": "/meta/connect",
                            "clientId": client_id,
                            "connectionType": "long-polling",
                            "id": str(msg_count + 1),
                        }
                    ]
                )

                max_retries = 5
                attempt = 0
                while attempt < max_retries:
                    try:
                        conn.request(
                            "POST",
                            f"/cometd/{_API_VERSION}/meta/connect",
                            body=connect_payload,
                            headers=headers,
                        )
                        response = conn.getresponse()
                        if response.status != 200:
                            logger.warning(f"Connect failed: HTTP {response.status}")
                            attempt += 1
                            continue
                        msg_count += 1

                        events = json.loads(response.read().decode("utf-8"))
                        for event in events:
                            if event.get("channel") == topic and "data" in event:
                                logger.debug(f"Event received for topic {topic}")
                                message_queue.put(event)
                        break
                    except Exception as e:
                        logger.warning(f"Connection error (attempt {attempt + 1}): {e}")
                        if conn:
                            conn.close()
                        conn = http.client.HTTPSConnection(parsed_url.netloc)
                        wait_time = min(2 ** attempt, 60)
                        time.sleep(wait_time)
                        attempt += 1
                else:
                    logger.error("Max retries reached. Exiting event stream.")
                    break

                while True:
                    try:
                        msg = message_queue.get(timeout=queue_timeout)
                        yield msg
                    except Empty:
                        logger.debug(f"Heartbeat: no message in last {queue_timeout} seconds")
                        break
        except Exception as err:
            logger.exception("Subscription error for topic '%s': %s", topic, err)
        finally:
            if client_id:
                try:
                    logger.debug(f"Disconnecting from server with client ID: {client_id}")
                    disconnect_payload = json.dumps(
                        [
                            {
                                "channel": "/meta/disconnect",
                                "clientId": client_id,
                                "id": str(msg_count + 1),
                            }
                        ]
                    )
                    conn.request(
                        "POST",
                        f"/cometd/{_API_VERSION}/meta/disconnect",
                        body=disconnect_payload,
                        headers=headers,
                    )
                    response = conn.getresponse()
                    _ = response.read().decode("utf-8")
                except Exception as e:
                    logger.warning(f"Exception during disconnect: {e}")
            if conn:
                conn.close()


def get_platform_events_client(
    http_client: HTTPClient,
    api_version: str,
) -> PlatformEventsClient:
    """
    Factory function to create a PlatformEventsClient instance.

    :param http_client: HTTPClient instance
    :param api_version: API version
    :return: New PlatformEventsClient
    """
    return PlatformEventsClient(http_client, api_version)
