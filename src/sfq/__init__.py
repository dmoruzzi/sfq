import http.client
import logging
import time
import os
import json
from urllib.parse import urlparse, quote

logging.basicConfig(level=logging.INFO)

class SFAuth:
    def __init__(
        self,
        instance_url,
        client_id,
        refresh_token,
        api_version="v62.0",
        token_endpoint="/services/oauth2/token",
        access_token=None,
        token_expiration_time=None,
        token_lifetime=15 * 60,
        proxy="auto",
    ):
        """
        Initializes the SFAuth with necessary parameters.

        :param instance_url: The Salesforce instance URL.
        :param client_id: The client ID for OAuth.
        :param refresh_token: The refresh token for OAuth.
        :param api_version: The Salesforce API version (default is "v62.0").
        :param token_endpoint: The token endpoint (default is "/services/oauth2/token").
        :param access_token: The access token for the current session (default is None).
        :param token_expiration_time: The expiration time of the access token (default is None).
        :param token_lifetime: The lifetime of the access token (default is 15 minutes).
        :param proxy: The proxy configuration (default is "auto").
        """
        self.instance_url = instance_url
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.api_version = api_version
        self.token_endpoint = token_endpoint
        self.access_token = access_token
        self.token_expiration_time = token_expiration_time
        self.token_lifetime = token_lifetime
        self._auto_configure_proxy(proxy)

    def _auto_configure_proxy(self, proxy):
        """
        Automatically configure the proxy based on the environment.
        """
        if proxy == "auto":
            if "https_proxy" in os.environ:
                self.proxy = os.environ["https_proxy"]
            else:
                self.proxy = None
        else:
            self.proxy = proxy

    def _prepare_payload(self):
        """Prepare the payload for the token request."""
        return {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
        }

    def _create_connection(self, netloc):
        """
        Create a connection using HTTP or HTTPS, depending on the proxy configuration.
        """
        if self.proxy:
            proxy_url = urlparse(self.proxy)
            if proxy_url.scheme == "http://":
                conn = http.client.HTTPConnection(proxy_url.hostname, proxy_url.port)
            else:
                conn = http.client.HTTPSConnection(proxy_url.hostname, proxy_url.port)
            conn.set_tunnel(netloc)
        else:
            conn = http.client.HTTPSConnection(netloc)
        return conn

    def _send_post_request(self, payload):
        """Send a POST request to the Salesforce token endpoint using http.client."""
        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = "&".join([f"{key}={quote(str(value))}" for key, value in payload.items()])

        try:
            conn.request("POST", self.token_endpoint, body, headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            if response.status == 200:
                return json.loads(data)
            else:
                logging.error(
                    f"HTTP error occurred: {response.status} {response.reason}"
                )
                logging.error(f"Response content: {data}")
        except Exception as err:
            logging.error(f"Other error occurred: {err}")
        finally:
            conn.close()

        return None

    def _refresh_token_if_needed(self):
        """Automatically refresh the token if it has expired or is missing."""
        _token_expiration = self._is_token_expired()
        if self.access_token and not _token_expiration:
            return
        
        if not self.access_token:
            logging.debug("No access token available. Requesting a new one.")
        elif _token_expiration:
            logging.debug("Access token has expired. Requesting a new one.")

        payload = self._prepare_payload()
        token_data = self._send_post_request(payload)
        if token_data:
            self.access_token = token_data["access_token"]
            self.token_expiration_time = int(token_data["issued_at"]) + int(self.token_lifetime)
            logging.debug("Access token refreshed successfully.")
        else:
            logging.error("Failed to refresh access token.")


    def _is_token_expired(self):
        """Check if the access token has expired."""
        return time.time() >= self.token_expiration_time

    def query(self, query, tooling=False):
        """Query Salesforce using SOQL or Tooling API, depending on the `tooling` parameter."""
        self._refresh_token_if_needed()

        if not self.access_token:
            logging.error("No access token available to make the query.")
            return None

        if tooling:
            query_endpoint = f"/services/data/{self.api_version}/tooling/query"
        else:
            query_endpoint = f"/services/data/{self.api_version}/query"

        headers = {"Authorization": f"Bearer {self.access_token}"}

        # Handle special characters in the query
        encoded_query = quote(query)
        params = f"?q={encoded_query}"

        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)

        try:
            conn.request("GET", query_endpoint + params, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            if response.status == 200:
                return json.loads(data)
            else:
                logging.error(f"HTTP error occurred during query: {response.status} {response.reason}")
                logging.error(f"Response content: {data}")
        except Exception as err:
            logging.error(f"Other error occurred during query: {err}")
        finally:
            conn.close()

        return None
