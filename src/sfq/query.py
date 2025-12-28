"""
Query client module for the SFQ library.

This module handles SOQL query operations, query result pagination,
composite query operations with threading, and sObject prefix management.
"""

import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote

from .utils import get_logger

logger = get_logger(__name__)


class QueryClient:
    """
    Manages SOQL query operations for Salesforce API communication.

    This class encapsulates all query-related functionality including
    standard SOQL queries, tooling API queries, composite batch queries,
    query result pagination, and sObject prefix management.
    """

    def __init__(
        self,
        http_client: "HTTPClient",  # Forward reference to avoid circular import  # noqa: F821
        api_version: str = "v65.0",
    ) -> None:
        """
        Initialize the QueryClient with HTTP client and API version.

        :param http_client: HTTPClient instance for making requests
        :param api_version: Salesforce API version to use
        """
        self.http_client = http_client
        self.api_version = api_version

    def query(self, query: str, tooling: bool = False) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query using the REST or Tooling API.

        :param query: The SOQL query string
        :param tooling: If True, use the Tooling API endpoint
        :return: Parsed JSON response with paginated results or None on failure
        """
        endpoint = f"/services/data/{self.api_version}/"
        endpoint += "tooling/query" if tooling else "query"
        query_string = f"?q={quote(query)}"
        endpoint += query_string

        try:
            status_code, data = self.http_client.send_authenticated_request(
                method="GET",
                endpoint=endpoint,
            )

            if status_code == 200:
                result = json.loads(data)
                # Paginate the results to get all records
                paginated = self._paginate_query_result(result)

                logger.debug(
                    "Query successful, returned %s records: %r",
                    paginated.get("totalSize"),
                    query,
                )
                logger.trace("Query full response: %s", paginated)
                return paginated
            else:
                logger.debug("Query failed: %r", query)
                logger.error(
                    "Query failed with HTTP status %s",
                    status_code,
                )
                logger.debug("Query response: %s", data)

        except Exception as err:
            logger.exception("Exception during query: %s", err)

        return None

    def tooling_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query using the Tooling API.

        This is a convenience method that calls query() with tooling=True.

        :param query: The SOQL query string
        :return: Parsed JSON response with paginated results or None on failure
        """
        return self.query(query, tooling=True)

    def _paginate_query_result(self, initial_result: dict) -> dict:
        """
        Helper to paginate Salesforce query results.

        This method automatically follows nextRecordsUrl to retrieve all
        records from a query result, combining them into a single response.

        :param initial_result: The initial query result from Salesforce
        :return: Dictionary with all records combined and pagination info updated
        """
        records = list(initial_result.get("records", []))
        done = initial_result.get("done", True)
        next_url = initial_result.get("nextRecordsUrl")
        total_size = initial_result.get("totalSize", len(records))

        # Get headers for subsequent requests
        headers = self.http_client.get_common_headers(include_auth=True)

        while not done and next_url:
            status_code, data = self.http_client.send_request(
                method="GET",
                endpoint=next_url,
                headers=headers,
            )

            if status_code == 200:
                next_result = json.loads(data)
                records.extend(next_result.get("records", []))
                done = next_result.get("done", True)
                next_url = next_result.get("nextRecordsUrl")
                total_size = next_result.get("totalSize", total_size)
            else:
                logger.error("Failed to fetch next records: %s", data)
                break

        # Create the paginated result
        paginated = dict(initial_result)
        paginated["records"] = records
        paginated["done"] = done
        paginated["totalSize"] = total_size

        # Remove nextRecordsUrl since we've fetched all records
        if "nextRecordsUrl" in paginated:
            del paginated["nextRecordsUrl"]

        return paginated

    def cquery(
        self,
        query_dict: Dict[str, str],
        batch_size: int = 25,
        max_workers: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute multiple SOQL queries using the Composite Batch API with threading.

        This method reduces network overhead by batching multiple queries into
        composite API calls and using threading for concurrent execution.
        Each query (subrequest) is counted as a unique API request against
        Salesforce governance limits.

        :param query_dict: Dictionary of SOQL queries with keys as logical names (referenceId) and values as SOQL queries
        :param batch_size: Number of queries to include in each batch (default is 25, max is 25)
        :param max_workers: Maximum number of threads for concurrent execution (default is None)
        :return: Dictionary mapping the original keys to their corresponding batch response or None on failure
        """
        if not query_dict:
            logger.warning("No queries to execute.")
            return None

        def _execute_batch(
            batch_keys: List[str], batch_queries: List[str]
        ) -> Dict[str, Any]:
            """
            Execute a single batch of queries using the Composite Batch API.

            :param batch_keys: List of query keys for this batch
            :param batch_queries: List of query strings for this batch
            :return: Dictionary mapping keys to their results
            """
            endpoint = f"/services/data/{self.api_version}/composite/batch"

            payload = {
                "haltOnError": False,
                "batchRequests": [
                    {
                        "method": "GET",
                        "url": f"/services/data/{self.api_version}/query?q={quote(query)}",
                    }
                    for query in batch_queries
                ],
            }

            status_code, data = self.http_client.send_authenticated_request(
                method="POST",
                endpoint=endpoint,
                body=json.dumps(payload),
            )

            batch_results = {}
            if status_code == 200:
                logger.debug("Composite query successful.")
                logger.trace("Composite query full response: %s", data)

                results = json.loads(data).get("results", [])
                for i, result in enumerate(results):
                    key = batch_keys[i]
                    if result.get("statusCode") == 200 and "result" in result:
                        # Paginate individual query results
                        paginated = self._paginate_query_result(result["result"])
                        batch_results[key] = paginated
                    else:
                        logger.error("Query failed for key %s: %s", key, result)
                        batch_results[key] = result
            else:
                logger.error(
                    "Composite query failed with HTTP status %s (%s)",
                    status_code,
                    data,
                )
                # Return error for all queries in this batch
                for key in batch_keys:
                    batch_results[key] = data
                logger.trace("Composite query response: %s", data)

            return batch_results

        # Prepare batches
        keys = list(query_dict.keys())
        results_dict = OrderedDict()

        # Execute batches with threading
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            # Create batches of queries
            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i : i + batch_size]
                batch_queries = [query_dict[key] for key in batch_keys]
                futures.append(
                    executor.submit(_execute_batch, batch_keys, batch_queries)
                )

            # Collect results as they complete
            for future in as_completed(futures):
                results_dict.update(future.result())

        logger.trace("Composite query results: %s", results_dict)
        return results_dict

    def get_sobject_prefixes(
        self, key_type: Literal["id", "name"] = "id"
    ) -> Optional[Dict[str, str]]:
        """
        Fetch all key prefixes from the Salesforce instance and map them to sObject names or vice versa.

        This method retrieves the sObject metadata to build a mapping between
        3-character key prefixes (like "001" for Account) and sObject API names.

        :param key_type: The type of key to return. Either 'id' (prefix->name) or 'name' (name->prefix)
        :return: Dictionary mapping key prefixes to sObject names (or vice versa) or None on failure
        """
        valid_key_types = {"id", "name"}
        if key_type not in valid_key_types:
            logger.error(
                "Invalid key type: %s, must be one of: %s",
                key_type,
                ", ".join(valid_key_types),
            )
            return None

        endpoint = f"/services/data/{self.api_version}/sobjects/"

        try:
            logger.trace("Request endpoint: %s", endpoint)

            status_code, data = self.http_client.send_authenticated_request(
                method="GET",
                endpoint=endpoint,
            )

            if status_code == 200:
                logger.debug("Key prefixes API request successful.")
                logger.trace("Response body: %s", data)

                prefixes = {}
                sobjects_data = json.loads(data)

                for sobject in sobjects_data.get("sobjects", []):
                    key_prefix = sobject.get("keyPrefix")
                    name = sobject.get("name")

                    # Skip sObjects without key prefix or name
                    if not key_prefix or not name:
                        continue

                    if key_type == "id":
                        prefixes[key_prefix] = name
                    elif key_type == "name":
                        prefixes[name] = key_prefix

                logger.debug("Key prefixes: %s", prefixes)
                return prefixes

            logger.error(
                "Key prefixes API request failed: %s",
                status_code,
            )
            logger.debug("Response body: %s", data)

        except Exception as err:
            logger.exception("Exception during key prefixes API request: %s", err)

        return None

    def get_sobject_name_from_id(self, record_id: str) -> Optional[str]:
        """
        Get the sObject name from a record ID using the key prefix.

        This is a convenience method that extracts the 3-character prefix
        from a record ID and looks up the corresponding sObject name.

        :param record_id: The Salesforce record ID (15 or 18 characters)
        :return: sObject API name or None if not found
        """
        if not record_id or len(record_id) < 3:
            logger.error("Invalid record ID: %s", record_id)
            return None

        # Extract the 3-character prefix
        prefix = record_id[:3]

        # Get the prefix mapping
        prefixes = self.get_sobject_prefixes(key_type="id")
        if not prefixes:
            return None

        return prefixes.get(prefix)

    def get_key_prefix_for_sobject(self, sobject_name: str) -> Optional[str]:
        """
        Get the 3-character key prefix for a given sObject name.

        :param sobject_name: The sObject API name (e.g., "Account", "Contact")
        :return: 3-character key prefix or None if not found
        """
        if not sobject_name:
            logger.error("sObject name cannot be empty")
            return None

        # Get the name-to-prefix mapping
        prefixes = self.get_sobject_prefixes(key_type="name")
        if not prefixes:
            return None

        return prefixes.get(sobject_name)

    def validate_query_syntax(self, query: str) -> bool:
        """
        Perform basic validation of SOQL query syntax.

        This method performs simple checks to catch common syntax errors
        before sending the query to Salesforce.

        :param query: The SOQL query string to validate
        :return: True if basic validation passes, False otherwise
        """
        if not query or not query.strip():
            logger.error("Query cannot be empty")
            return False

        query_upper = query.upper().strip()

        # Check for required SELECT keyword
        if not query_upper.startswith("SELECT"):
            logger.error("Query must start with SELECT")
            return False

        # Check for required FROM keyword
        if " FROM " not in query_upper:
            logger.error("Query must contain FROM clause")
            return False

        # Check for balanced parentheses
        if query.count("(") != query.count(")"):
            logger.error("Unbalanced parentheses in query")
            return False

        # Check for balanced quotes
        single_quotes = query.count("'")
        if single_quotes % 2 != 0:
            logger.error("Unbalanced single quotes in query")
            return False

        return True

    def __repr__(self) -> str:
        """String representation of QueryClient for debugging."""
        return (
            f"QueryClient(api_version='{self.api_version}', "
            f"http_client={type(self.http_client).__name__})"
        )
