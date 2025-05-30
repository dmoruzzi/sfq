import http.client
import json
import logging
import time
from typing import Any, Optional
import warnings
from queue import Empty, Queue

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

class ExperimentalWarning(Warning):
    pass


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Custom TRACE level logging function with redaction."""

    def _redact_sensitive(data: Any) -> Any:
        """Redacts sensitive keys from a dictionary or query string."""
        REDACT_VALUE = "*" * 8
        REDACT_KEYS = [
            "access_token",
            "authorization",
            "set-cookie",
            "cookie",
            "refresh_token",
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
            parts = data.split("&")
            for i, part in enumerate(parts):
                if "=" in part:
                    key, value = part.split("=", 1)
                    if key.lower() in REDACT_KEYS:
                        parts[i] = f"{key}={REDACT_VALUE}"
            return "&".join(parts)
        return data

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


logging.Logger.trace = trace
logger = logging.getLogger("sfq")

def _reconnect_with_backoff(self, attempt: int) -> None:
    wait_time = min(2**attempt, 60)
    logger.warning(
        f"Reconnecting after failure, backoff {wait_time}s (attempt {attempt})"
    )
    time.sleep(wait_time)

def _subscribe_topic(
    self,
    topic: str,
    queue_timeout: int = 90,
    max_runtime: Optional[int] = None,
):
    """
    Yields events from a subscribed Salesforce CometD topic.

    :param topic: Topic to subscribe to, e.g. '/event/MyEvent__e'
    :param queue_timeout: Seconds to wait for a message before logging heartbeat
    :param max_runtime: Max total time to listen in seconds (None = unlimited)
    """
    warnings.warn(
        "The _subscribe_topic method is experimental and subject to change in future versions.",
        ExperimentalWarning,
        stacklevel=2,
    )

    self._refresh_token_if_needed()
    self._msg_count: int = 0

    if not self.access_token:
        logger.error("No access token available for event stream.")
        return

    start_time = time.time()
    message_queue = Queue()
    headers = {
        "Authorization": f"Bearer {self.access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": self.user_agent,
        "Sforce-Call-Options": f"client={self.sforce_client}",
    }

    parsed_url = urlparse(self.instance_url)
    conn = self._create_connection(parsed_url.netloc)
    _API_VERSION = str(self.api_version).removeprefix("v")
    client_id = str()

    try:
        logger.trace("Starting handshake with Salesforce CometD server.")
        handshake_payload = json.dumps(
            {
                "id": str(self._msg_count + 1),
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
            headers=headers,
            body=handshake_payload,
        )
        response = conn.getresponse()
        self._http_resp_header_logic(response)

        logger.trace("Received handshake response.")
        for name, value in response.getheaders():
            if name.lower() == "set-cookie" and "BAYEUX_BROWSER=" in value:
                _bayeux_browser_cookie = value.split("BAYEUX_BROWSER=")[1].split(
                    ";"
                )[0]
                headers["Cookie"] = f"BAYEUX_BROWSER={_bayeux_browser_cookie}"
                break

        data = json.loads(response.read().decode("utf-8"))
        if not data or not data[0].get("successful"):
            logger.error("Handshake failed: %s", data)
            return

        client_id = data[0]["clientId"]
        logger.trace(f"Handshake successful, client ID: {client_id}")

        logger.trace(f"Subscribing to topic: {topic}")
        subscribe_message = {
            "channel": "/meta/subscribe",
            "clientId": client_id,
            "subscription": topic,
            "id": str(self._msg_count + 1),
        }
        conn.request(
            "POST",
            f"/cometd/{_API_VERSION}/meta/subscribe",
            headers=headers,
            body=json.dumps(subscribe_message),
        )
        response = conn.getresponse()
        self._http_resp_header_logic(response)

        sub_response = json.loads(response.read().decode("utf-8"))
        if not sub_response or not sub_response[0].get("successful"):
            logger.error("Subscription failed: %s", sub_response)
            return

        logger.info(f"Successfully subscribed to topic: {topic}")
        logger.trace("Entering event polling loop.")

        try:
            while True:
                if max_runtime and (time.time() - start_time > max_runtime):
                    logger.info(
                        f"Disconnecting after max_runtime={max_runtime} seconds"
                    )
                    break

                logger.trace("Sending connection message.")
                connect_payload = json.dumps(
                    [
                        {
                            "channel": "/meta/connect",
                            "clientId": client_id,
                            "connectionType": "long-polling",
                            "id": str(self._msg_count + 1),
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
                            headers=headers,
                            body=connect_payload,
                        )
                        response = conn.getresponse()
                        self._http_resp_header_logic(response)
                        self._msg_count += 1

                        events = json.loads(response.read().decode("utf-8"))
                        for event in events:
                            if event.get("channel") == topic and "data" in event:
                                logger.trace(
                                    f"Event received for topic {topic}, data: {event['data']}"
                                )
                                message_queue.put(event)
                        break
                    except (
                        http.client.RemoteDisconnected,
                        ConnectionResetError,
                        TimeoutError,
                        http.client.BadStatusLine,
                        http.client.CannotSendRequest,
                        ConnectionAbortedError,
                        ConnectionRefusedError,
                        ConnectionError,
                    ) as e:
                        logger.warning(
                            f"Connection error (attempt {attempt + 1}): {e}"
                        )
                        conn.close()
                        conn = self._create_connection(parsed_url.netloc)
                        self._reconnect_with_backoff(attempt)
                        attempt += 1
                    except Exception as e:
                        logger.exception(
                            f"Connection error (attempt {attempt + 1}): {e}"
                        )
                        break
                else:
                    logger.error("Max retries reached. Exiting event stream.")
                    break

                while True:
                    try:
                        msg = message_queue.get(timeout=queue_timeout, block=True)
                        yield msg
                    except Empty:
                        logger.debug(
                            f"Heartbeat: no message in last {queue_timeout} seconds"
                        )
                        break
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, disconnecting...")

        except Exception as e:
            logger.exception(f"Polling error: {e}")

    finally:
        if client_id:
            try:
                logger.trace(
                    f"Disconnecting from server with client ID: {client_id}"
                )
                disconnect_payload = json.dumps(
                    [
                        {
                            "channel": "/meta/disconnect",
                            "clientId": client_id,
                            "id": str(self._msg_count + 1),
                        }
                    ]
                )
                conn.request(
                    "POST",
                    f"/cometd/{_API_VERSION}/meta/disconnect",
                    headers=headers,
                    body=disconnect_payload,
                )
                response = conn.getresponse()
                self._http_resp_header_logic(response)
                _ = response.read()
                logger.trace("Disconnected successfully.")
            except Exception as e:
                logger.warning(f"Exception during disconnect: {e}")
        if conn:
            logger.trace("Closing connection.")
            conn.close()

        logger.trace("Leaving event polling loop.")
