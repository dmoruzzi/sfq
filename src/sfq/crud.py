"""
CRUD operations module for SFQ library.

This module provides CRUD (Create, Read, Update, Delete) operations for Salesforce records
using various APIs including SOAP, REST, and Composite APIs.
"""

import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Literal, Optional
from urllib.parse import quote

from .query import QueryClient
from .utils import get_logger

logger = get_logger("sfq.crud")


class CRUDClient:
    """
    Client for CRUD operations on Salesforce records.

    This class handles create, update, and delete operations using appropriate
    Salesforce APIs with batch processing and threading support.
    """

    def __init__(self, http_client, soap_client, api_version: str = "v65.0"):
        """
        Initialize the CRUD client.

        :param http_client: HTTPClient instance for making HTTP requests
        :param soap_client: SOAPClient instance for SOAP operations
        :param api_version: Salesforce API version to use
        """
        self.http_client = http_client
        self.soap_client = soap_client
        self.api_version = api_version

    def _soap_batch_operation(
        self,
        sobject: str,
        data_list,
        method: str,
        batch_size: int = 200,
        max_workers: int = None,
        api_type: Literal["enterprise", "tooling"] = "enterprise",
    ) -> Optional[Dict[str, Any]]:
        """
        Internal helper for batch SOAP operations (create/delete).
        """
        endpoint = "/services/Soap/"
        if api_type == "enterprise":
            endpoint += f"c/{self.api_version}"
        elif api_type == "tooling":
            endpoint += f"T/{self.api_version}"
        else:
            logger.error(
                "Invalid API type: %s. Must be one of: 'enterprise', 'tooling'.",
                api_type,
            )
            return None

        endpoint = endpoint.replace("/v", "/")

        if isinstance(data_list, dict) and method == "create":
            data_list = [data_list]
        if isinstance(data_list, str) and method == "delete":
            data_list = [data_list]

        chunks = [
            data_list[i : i + batch_size]
            for i in range(0, len(data_list), batch_size)
        ]

        def process_chunk(chunk):
            try:
                access_token = self.http_client.auth_manager.access_token
                if not access_token:
                    logger.error("No access token available for SOAP request")
                    return None

                header = self.soap_client.generate_soap_header(access_token)
                body = self.soap_client.generate_soap_body(
                    sobject=sobject, method=method, data=chunk
                )
                envelope = self.soap_client.generate_soap_envelope(
                    header=header, body=body, api_type=api_type
                )

                soap_headers = self.http_client.get_common_headers().copy()
                soap_headers["Content-Type"] = "text/xml; charset=UTF-8"
                soap_headers["SOAPAction"] = '""'

                logger.trace(f"SOAP {method} request envelope: %s", envelope)
                logger.trace(f"SOAP {method} request headers: %s", soap_headers)

                status_code, resp_data = self.http_client.send_request(
                    method="POST",
                    endpoint=endpoint,
                    headers=soap_headers,
                    body=envelope,
                )

                logger.trace(f"SOAP {method} response status: {status_code}")
                logger.trace(f"SOAP {method} raw response: {resp_data}")

                if status_code == 200:
                    logger.debug(f"{method.capitalize()} API request successful.")
                    logger.trace(f"{method.capitalize()} API response: %s", resp_data)
                    result = self.soap_client.extract_soap_result_fields(resp_data)
                    if result:
                        return result
                    logger.error("Failed to extract fields from SOAP response.")
                else:
                    logger.error(f"{method.capitalize()} API request failed: %s", status_code)
                    logger.debug("Response body: %s", resp_data)
                    return None
            except Exception as e:
                logger.exception(f"Exception during {method} chunk: %s", e)
                return None

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        combined_response = [
            item
            for result in results
            for item in (result if isinstance(result, list) else [result])
            if isinstance(result, (dict, list))
        ]

        return combined_response or None

    def create(
        self,
        sobject: str,
        insert_list: List[Dict[str, Any]],
        batch_size: int = 200,
        max_workers: int = None,
        api_type: Literal["enterprise", "tooling"] = "enterprise",
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Insert API to insert multiple records via SOAP calls.
        """
        return self._soap_batch_operation(
            sobject=sobject,
            data_list=insert_list,
            method="create",
            batch_size=batch_size,
            max_workers=max_workers,
            api_type=api_type,
        )
    
    def update(
        self,
        sobject: str,
        update_list: List[Dict[str, Any]],
        batch_size: int = 200,
        max_workers: int = None,
        api_type: Literal["enterprise", "tooling"] = "enterprise",
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Update API to update multiple records via SOAP calls.
        :param sobject: The name of the sObject to update.
        :param update_list: A list of dictionaries, each representing a record to update (must include Id).
        :param batch_size: The number of records to update in each batch (default is 200).
        :param max_workers: The maximum number of threads to spawn for concurrent execution.
        :param api_type: API type to use ('enterprise' or 'tooling').
        :return: JSON response from the update request or None on failure.
        """
        return self._soap_batch_operation(
            sobject=sobject,
            data_list=update_list,
            method="update",
            batch_size=batch_size,
            max_workers=max_workers,
            api_type=api_type,
        )
    
    def delete(
        self,
        sobject: str,
        id_list: List[str],
        batch_size: int = 200,
        max_workers: int = None,
        api_type: Literal["enterprise", "tooling"] = "enterprise",
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Delete API to remove multiple records via SOAP calls.
        :param sobject: The name of the sObject to delete from.
        :param id_list: A list of record IDs to delete (strings, not dicts).
        :param batch_size: The number of records to delete in each batch (default is 200).
        :param max_workers: The maximum number of threads to spawn for concurrent execution.
        :param api_type: API type to use ('enterprise' or 'tooling').
        :return: JSON response from the delete request or None on failure.
        """
        # Pass list of IDs directly for SOAP delete
        return self._soap_batch_operation(
            sobject=sobject,
            data_list=id_list,
            method="delete",
            batch_size=batch_size,
            max_workers=max_workers,
            api_type=api_type,
        )

    def cupdate(
        self, update_dict: Dict[str, Any], batch_size: int = 25, max_workers: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Composite Update API to update multiple records.

        :param update_dict: A dictionary of keys of records to be updated, and a dictionary
                           of field-value pairs to be updated, with a special key '_' overriding
                           the sObject type which is otherwise inferred from the key.
        :param batch_size: The number of records to update in each batch (default is 25).
        :param max_workers: The maximum number of threads to spawn for concurrent execution.
        :return: JSON response from the update request or None on failure.
        """
        allOrNone = False
        endpoint = f"/services/data/{self.api_version}/composite"

        compositeRequest_payload = []
        sobject_prefixes = {}

        for key, record in update_dict.items():
            record_copy = record.copy()
            sobject = record_copy.pop("_", None)
            if not sobject and not sobject_prefixes:
                # Get sObject prefixes from query client if available
                # For now, we'll require the sobject to be specified or use key prefix
                sobject_prefixes = self._get_sobject_prefixes()

            if not sobject:
                sobject = str(sobject_prefixes.get(str(key[:3]), None))

            compositeRequest_payload.append(
                {
                    "method": "PATCH",
                    "url": f"/services/data/{self.api_version}/sobjects/{sobject}/{key}",
                    "referenceId": key,
                    "body": record_copy,
                }
            )

        chunks = [
            compositeRequest_payload[i : i + batch_size]
            for i in range(0, len(compositeRequest_payload), batch_size)
        ]

        def update_chunk(chunk: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            """Update a chunk of records using Composite API."""
            try:
                payload = {"allOrNone": bool(allOrNone), "compositeRequest": chunk}

                status_code, resp_data = self.http_client.send_request(
                    method="POST",
                    endpoint=endpoint,
                    headers=self.http_client.get_common_headers(),
                    body=json.dumps(payload),
                )

                if status_code == 200:
                    logger.debug("Composite update API response without errors.")
                    return json.loads(resp_data)
                else:
                    logger.error("Composite update API request failed: %s", status_code)
                    logger.debug("Response body: %s", resp_data)
                    return None

            except Exception as e:
                logger.exception("Exception during update chunk: %s", e)
                return None

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(update_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        combined_response = [
            item
            for result in results
            for item in (result if isinstance(result, list) else [result])
            if isinstance(result, (dict, list))
        ]

        return combined_response or None

    def cdelete(
        self, ids: Iterable[str], batch_size: int = 200, max_workers: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Collections Delete API to delete multiple records using multithreading.

        :param ids: A list of record IDs to delete.
        :param batch_size: The number of records to delete in each batch (default is 200).
        :param max_workers: The maximum number of threads to spawn for concurrent execution.
        :return: Combined JSON response from all batches or None on complete failure.
        """
        ids = list(ids)
        chunks = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]

        def delete_chunk(chunk: List[str]) -> Optional[Dict[str, Any]]:
            """Delete a chunk of records using Collections API."""
            try:
                endpoint = f"/services/data/{self.api_version}/composite/sobjects?ids={','.join(chunk)}&allOrNone=false"
                headers = self.http_client.get_common_headers()

                status_code, resp_data = self.http_client.send_request(
                    method="DELETE",
                    endpoint=endpoint,
                    headers=headers,
                )

                if status_code == 200:
                    logger.debug("Collections delete API response without errors.")
                    return json.loads(resp_data)
                else:
                    logger.error(
                        "Collections delete API request failed: %s", status_code
                    )
                    logger.debug("Response body: %s", resp_data)
                    return None

            except Exception as e:
                logger.exception("Exception during delete chunk: %s", e)
                return None

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(delete_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        combined_response = [
            item
            for result in results
            for item in (result if isinstance(result, list) else [result])
            if isinstance(result, (dict, list))
        ]
        return combined_response or None

    def read_static_resource_name(
        self, resource_name: str, namespace: Optional[str] = None
    ) -> Optional[str]:
        """
        Read a static resource for a given name from the Salesforce instance.

        :param resource_name: Name of the static resource to read.
        :param namespace: Namespace of the static resource to read (default is None).
        :return: Static resource content or None on failure.
        """
        _safe_resource_name = quote(resource_name, safe="")
        query = f"SELECT Id FROM StaticResource WHERE Name = '{_safe_resource_name}'"
        if namespace:
            namespace = quote(namespace, safe="")
            query += f" AND NamespacePrefix = '{namespace}'"
        query += " LIMIT 1"

        # Make the query directly via HTTP client
        query_endpoint = f"/services/data/{self.api_version}/query?q={quote(query)}"
        status_code, response_data = self.http_client.send_authenticated_request(
            method="GET",
            endpoint=query_endpoint,
        )

        if status_code == 200:
            _static_resource_id_response = json.loads(response_data)
        else:
            logger.error("Failed to query for static resource: %s", status_code)
            _static_resource_id_response = None

        if (
            _static_resource_id_response
            and _static_resource_id_response.get("records")
            and len(_static_resource_id_response["records"]) > 0
        ):
            return self.read_static_resource_id(
                _static_resource_id_response["records"][0].get("Id")
            )

        logger.error(f"Failed to read static resource with name {_safe_resource_name}.")
        return None

    def read_static_resource_id(self, resource_id: str) -> Optional[str]:
        """
        Read a static resource for a given ID from the Salesforce instance.

        :param resource_id: ID of the static resource to read.
        :return: Static resource content or None on failure.
        """
        endpoint = f"/services/data/{self.api_version}/sobjects/StaticResource/{resource_id}/Body"

        # Use a special method for binary content
        status, data = self.http_client.send_authenticated_request("GET", endpoint)

        if status == 200:
            logger.debug("Static resource fetched successfully.")
            # Try to decode as UTF-8, but handle binary content gracefully
            try:
                return data.decode("utf-8") if isinstance(data, bytes) else data
            except UnicodeDecodeError:
                # For binary content, return base64 encoded string
                import base64

                return (
                    base64.b64encode(data).decode("utf-8")
                    if isinstance(data, bytes)
                    else data
                )

        logger.error("Failed to fetch static resource: %s", status)
        return None

    def update_static_resource_name(
        self, resource_name: str, data: str, namespace: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update a static resource for a given name in the Salesforce instance.

        :param resource_name: Name of the static resource to update.
        :param data: Content to update the static resource with.
        :param namespace: Optional namespace to search for the static resource.
        :return: Static resource content or None on failure.
        """
        safe_resource_name = quote(resource_name, safe="")
        query = f"SELECT Id FROM StaticResource WHERE Name = '{safe_resource_name}'"
        if namespace:
            namespace = quote(namespace, safe="")
            query += f" AND NamespacePrefix = '{namespace}'"
        query += " LIMIT 1"

        # We need to use the HTTP client to make a query request
        query_endpoint = f"/services/data/{self.api_version}/query?q={quote(query)}"
        status_code, response_data = self.http_client.send_authenticated_request(
            method="GET",
            endpoint=query_endpoint,
        )

        if status_code == 200:
            static_resource_id_response = json.loads(response_data)
        else:
            logger.error("Failed to query for static resource: %s", status_code)
            static_resource_id_response = None

        if (
            static_resource_id_response
            and static_resource_id_response.get("records")
            and len(static_resource_id_response["records"]) > 0
        ):
            return self.update_static_resource_id(
                static_resource_id_response["records"][0].get("Id"), data
            )

        logger.error(
            f"Failed to update static resource with name {safe_resource_name}."
        )
        return None

    def update_static_resource_id(
        self, resource_id: str, data: str
    ) -> Optional[Dict[str, Any]]:
        """
        Replace the content of a static resource in the Salesforce instance by ID.

        :param resource_id: ID of the static resource to update.
        :param data: Content to update the static resource with.
        :return: Parsed JSON response or None on failure.
        """
        payload = {"Body": base64.b64encode(data.encode("utf-8")).decode("utf-8")}

        endpoint = (
            f"/services/data/{self.api_version}/sobjects/StaticResource/{resource_id}"
        )
        status_code, response_data = self.http_client.send_authenticated_request(
            method="PATCH",
            endpoint=endpoint,
            body=json.dumps(payload),
        )

        if status_code in [200, 204]:  # 204 No Content is also success for PATCH
            logger.debug("Patch Static Resource request successful.")
            if response_data and response_data.strip():
                return json.loads(response_data)
            else:
                return {"success": True}  # Return success indicator for 204 responses

        logger.error(
            "Patch Static Resource API request failed: %s",
            status_code,
        )
        logger.error("Response body: %s", response_data)

        return None

    def _get_sobject_prefixes(self) -> Dict[str, str]:
        """
        Get sObject prefixes mapping. This is a placeholder that would normally
        call the query client to get prefixes.

        :return: Dictionary mapping key prefixes to sObject names
        """
        return QueryClient.get_sobject_prefixes(self)
