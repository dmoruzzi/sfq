"""
SOAP client module for Salesforce API operations.

This module provides SOAP envelope generation, XML parsing, and result field extraction
functionality for interacting with Salesforce's SOAP APIs (Enterprise and Tooling).
"""

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Union

from .utils import get_logger

logger = get_logger("sfq.soap")


class SOAPClient:
    """
    SOAP client for Salesforce API operations.

    Handles SOAP envelope generation, XML parsing, and result field extraction
    for both Enterprise and Tooling APIs.
    """

    def __init__(self, http_client, api_version: str = "v65.0"):
        """
        Initialize the SOAP client.

        :param http_client: HTTPClient instance for making requests
        :param api_version: Salesforce API version (e.g., "v65.0")
        """
        self.http_client = http_client
        self.api_version = api_version

    def generate_soap_envelope(self, header: str, body: str, api_type: str) -> str:
        """
        Generate a full SOAP envelope with all required namespaces for Salesforce API.

        :param header: SOAP header content
        :param body: SOAP body content
        :param api_type: API type - either "enterprise" or "tooling"
        :return: Complete SOAP envelope as XML string
        :raises ValueError: If api_type is not "enterprise" or "tooling"
        """
        if api_type == "enterprise":
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<soapenv:Envelope "
                'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
                'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns="urn:enterprise.soap.sforce.com" '
                'xmlns:sf="urn:sobject.enterprise.soap.sforce.com">'
                f"{header}{body}"
                "</soapenv:Envelope>"
            )
        elif api_type == "tooling":
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<soapenv:Envelope "
                'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
                'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns="urn:tooling.soap.sforce.com" '
                'xmlns:mns="urn:metadata.tooling.soap.sforce.com" '
                'xmlns:sf="urn:sobject.tooling.soap.sforce.com">'
                f"{header}{body}"
                "</soapenv:Envelope>"
            )
        else:
            raise ValueError(
                f"Unsupported API type: {api_type}. Must be 'enterprise' or 'tooling'."
            )

    def generate_soap_header(self, session_id: str) -> str:
        """
        Generate the SOAP header for Salesforce API requests.

        :param session_id: OAuth access token to use as session ID
        :return: SOAP header XML string
        """
        return f"<soapenv:Header><SessionHeader><sessionId>{session_id}</sessionId></SessionHeader></soapenv:Header>"

    def generate_soap_body(
        self,
        sobject: str,
        method: str,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
    ) -> str:
        """
        Generate a SOAP request body for one or more records.

        :param sobject: Salesforce object type (e.g., "Account", "Contact")
        :param method: SOAP method name (e.g., "create", "update")
        :param data: Single record dict or list of record dicts
        :return: SOAP body XML string
        """
        # Accept both a single dict and a list of dicts
        if isinstance(data, dict):
            records = [data]
        else:
            records = data

        if method == "delete":
            # For delete, records is a list of IDs (strings)
            id_tags = "".join(f"<ID>{id}</ID>" for id in records)
            return f"<soapenv:Body><delete>{id_tags}</delete></soapenv:Body>"
        else:
            sobjects = "".join(
                f'<sObjects xsi:type="{sobject}">'
                + "".join(f"<{k}>{v}</{k}>" for k, v in record.items())
                + "</sObjects>"
                for record in records
            )
            return f"<soapenv:Body><{method}>{sobjects}</{method}></soapenv:Body>"

    def extract_soap_result_fields(
        self, xml_string: str
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        Parse SOAP XML response and extract all child fields from <result> elements as dict(s).

        :param xml_string: SOAP response XML string
        :return: Single dict for one result, list of dicts for multiple results, or None on parse error
        """

        def strip_namespace(tag):
            """Remove XML namespace from tag name."""
            return tag.split("}", 1)[-1] if "}" in tag else tag

        try:
            root = ET.fromstring(xml_string)
            results = []

            # Find all elements that end with "result" (handles namespaced tags)
            for result in root.iter():
                if result.tag.endswith("result"):
                    result_dict = {}
                    for child in result:
                        result_dict[strip_namespace(child.tag)] = child.text
                    results.append(result_dict)

            if not results:
                return None
            if len(results) == 1:
                return results[0]
            return results

        except ET.ParseError as e:
            logger.error("Failed to parse SOAP XML: %s", e)
            return None

    def xml_to_dict(self, xml_string: str) -> Optional[Dict[str, Any]]:
        """
        Convert an XML string to a JSON-like dictionary.

        :param xml_string: The XML string to convert
        :return: A dictionary representation of the XML or None on failure
        """
        try:
            root = ET.fromstring(xml_string)
            return self._xml_element_to_dict(root)
        except ET.ParseError as e:
            logger.error("Failed to parse XML: %s", e)
            return None

    def _xml_element_to_dict(self, element: ET.Element) -> Union[str, Dict[str, Any]]:
        """
        Recursively convert an XML Element to a dictionary.

        :param element: The XML Element to convert
        :return: A dictionary representation of the XML Element or text content
        """
        if len(element) == 0:
            return element.text or ""

        result = {}
        for child in element:
            child_dict = self._xml_element_to_dict(child)
            if child.tag not in result:
                result[child.tag] = child_dict
            else:
                # Handle multiple children with same tag name
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_dict)
        return result
