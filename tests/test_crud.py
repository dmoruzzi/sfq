"""
Unit tests for the CRUD client module.
"""

import base64
import json
from unittest.mock import Mock

from sfq.crud import CRUDClient


class TestCRUDClient:
    """Test cases for CRUDClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_http_client = Mock()
        self.mock_soap_client = Mock()
        self.crud_client = CRUDClient(
            http_client=self.mock_http_client,
            soap_client=self.mock_soap_client,
            api_version="v65.0",
        )

    def test_init(self):
        """Test CRUDClient initialization."""
        assert self.crud_client.http_client == self.mock_http_client
        assert self.crud_client.soap_client == self.mock_soap_client
        assert self.crud_client.api_version == "v65.0"

    def mock_authenticated_response(self, responses):
        """Helper to mock send_authenticated_request with single or multiple responses."""
        if isinstance(responses, list):
            self.mock_http_client.send_authenticated_request.side_effect = responses
        else:
            self.mock_http_client.send_authenticated_request.return_value = responses

    def test_create_single_record_success(self):
        """Test successful creation of a single record."""
        # Setup mocks
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"
        self.mock_soap_client.extract_soap_result_fields.return_value = {
            "id": "001xx000003DHPh",
            "success": "true",
        }

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
        }
        self.mock_http_client.send_request.return_value = (200, "<soap:response/>")

        # Test data
        sobject = "Account"
        insert_list = [{"Name": "Test Account"}]

        # Execute
        result = self.crud_client.create(sobject, insert_list)

        # Verify
        assert result == [{"id": "001xx000003DHPh", "success": "true"}]

        # Verify SOAP client calls
        self.mock_soap_client.generate_soap_header.assert_called_once()
        self.mock_soap_client.generate_soap_body.assert_called_once_with(
            sobject="Account", method="create", data=[{"Name": "Test Account"}]
        )
        self.mock_soap_client.generate_soap_envelope.assert_called_once_with(
            header="<header/>", body="<body/>", api_type="enterprise"
        )

        # Verify HTTP client calls
        self.mock_http_client.send_request.assert_called_once()
        call_args = self.mock_http_client.send_request.call_args
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["endpoint"] == "/services/Soap/c/65.0"
        assert call_args[1]["headers"]["Content-Type"] == "text/xml; charset=UTF-8"
        assert call_args[1]["headers"]["SOAPAction"] == '""'
        assert call_args[1]["body"] == "<envelope/>"

    def test_create_multiple_records_success(self):
        """Test successful creation of multiple records."""
        # Setup mocks
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"
        self.mock_soap_client.extract_soap_result_fields.return_value = [
            {"id": "001xx000003DHPh", "success": "true"},
            {"id": "001xx000003DHPi", "success": "true"},
        ]

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (200, "<soap:response/>")

        # Test data
        sobject = "Account"
        insert_list = [{"Name": "Test Account 1"}, {"Name": "Test Account 2"}]

        # Execute
        result = self.crud_client.create(sobject, insert_list)

        # Verify
        expected = [
            {"id": "001xx000003DHPh", "success": "true"},
            {"id": "001xx000003DHPi", "success": "true"},
        ]
        assert result == expected

    def test_create_with_tooling_api(self):
        """Test creation using tooling API."""
        # Setup mocks
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"
        self.mock_soap_client.extract_soap_result_fields.return_value = {
            "id": "01pxx000000001",
            "success": "true",
        }

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (200, "<soap:response/>")

        # Test data
        sobject = "ApexClass"
        insert_list = [{"Name": "TestClass", "Body": "public class TestClass {}"}]

        # Execute
        result = self.crud_client.create(sobject, insert_list, api_type="tooling")

        # Verify endpoint
        call_args = self.mock_http_client.send_request.call_args
        assert call_args[1]["endpoint"] == "/services/Soap/T/65.0"

        # Verify SOAP envelope generation
        self.mock_soap_client.generate_soap_envelope.assert_called_once_with(
            header="<header/>", body="<body/>", api_type="tooling"
        )

    def test_create_invalid_api_type(self):
        """Test creation with invalid API type."""
        result = self.crud_client.create(
            "Account", [{"Name": "Test"}], api_type="invalid"
        )

        assert result is None
        # Verify no HTTP requests were made
        self.mock_http_client.send_request.assert_not_called()

    def test_create_http_error(self):
        """Test creation with HTTP error response."""
        # Setup mocks
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (400, "Bad Request")

        # Execute
        result = self.crud_client.create("Account", [{"Name": "Test"}])

        # Verify - when all chunks fail, we get None
        assert result is None

    def test_create_soap_parsing_error(self):
        """Test creation with SOAP parsing error."""
        # Setup mocks
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"
        self.mock_soap_client.extract_soap_result_fields.return_value = None

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (200, "<invalid:xml/>")

        # Execute
        result = self.crud_client.create("Account", [{"Name": "Test"}])

        # Verify - when all chunks fail, we get None
        assert result is None

    def test_create_with_batching(self):
        """Test creation with batch processing."""
        # Setup mocks for multiple batches
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"

        # Mock different responses for each batch
        self.mock_soap_client.extract_soap_result_fields.side_effect = [
            [{"id": "001xx000003DHPh", "success": "true"}],
            [{"id": "001xx000003DHPi", "success": "true"}],
        ]

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (200, "<soap:response/>")

        # Test data - 2 records with batch_size=1 to force 2 batches
        insert_list = [{"Name": "Test Account 1"}, {"Name": "Test Account 2"}]

        # Execute
        result = self.crud_client.create("Account", insert_list, batch_size=1)

        # Verify
        assert len(result) == 2
        assert {"id": "001xx000003DHPh", "success": "true"} in result
        assert {"id": "001xx000003DHPi", "success": "true"} in result

        # Verify HTTP client was called twice (once per batch)
        assert self.mock_http_client.send_request.call_count == 2

    def test_create_dict_input_converted_to_list(self):
        """Test that dict input is converted to list."""
        # Setup mocks
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"
        self.mock_soap_client.extract_soap_result_fields.return_value = {
            "id": "001xx000003DHPh",
            "success": "true",
        }

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (200, "<soap:response/>")

        # Test with dict input instead of list
        result = self.crud_client.create("Account", {"Name": "Test Account"})

        # Verify the SOAP body was called with a list
        self.mock_soap_client.generate_soap_body.assert_called_once_with(
            sobject="Account", method="create", data=[{"Name": "Test Account"}]
        )

        assert result == [{"id": "001xx000003DHPh", "success": "true"}]

    def test_create_with_max_workers_parameter(self):
        """Test creation with max_workers parameter."""
        # Setup mocks
        self.mock_soap_client.generate_soap_header.return_value = "<header/>"
        self.mock_soap_client.generate_soap_body.return_value = "<body/>"
        self.mock_soap_client.generate_soap_envelope.return_value = "<envelope/>"
        self.mock_soap_client.extract_soap_result_fields.return_value = {
            "id": "001xx000003DHPh",
            "success": "true",
        }

        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (200, "<soap:response/>")

        # Execute - just verify it doesn't crash with max_workers parameter
        result = self.crud_client.create("Account", [{"Name": "Test"}], max_workers=2)

        # Verify basic functionality still works
        assert result == [{"id": "001xx000003DHPh", "success": "true"}]

    def test_cupdate_success(self):
        """Test successful update operation."""
        # Setup mocks
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
        }
        self.mock_http_client.send_request.return_value = (
            200,
            json.dumps(
                {
                    "compositeResponse": [
                        {"httpStatusCode": 200, "referenceId": "001xx000003DHPh"}
                    ]
                }
            ),
        )

        # Test data
        update_dict = {"001xx000003DHPh": {"_": "Account", "Name": "Updated Account"}}

        # Execute
        result = self.crud_client.cupdate(update_dict)

        # Verify
        expected = [
            {
                "compositeResponse": [
                    {"httpStatusCode": 200, "referenceId": "001xx000003DHPh"}
                ]
            }
        ]
        assert result == expected

        # Verify HTTP client call
        self.mock_http_client.send_request.assert_called_once()
        call_args = self.mock_http_client.send_request.call_args
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["endpoint"] == "/services/data/v65.0/composite"

        # Verify request body
        body = json.loads(call_args[1]["body"])
        assert body["allOrNone"] == False
        assert len(body["compositeRequest"]) == 1
        assert body["compositeRequest"][0]["method"] == "PATCH"
        assert body["compositeRequest"][0]["referenceId"] == "001xx000003DHPh"
        assert body["compositeRequest"][0]["body"] == {"Name": "Updated Account"}

    def test_cupdate_without_sobject_type(self):
        """Test update operation without explicit sObject type."""
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }

        self.mock_http_client.send_request.return_value = (
            200,
            json.dumps(
                {
                    "compositeResponse": [
                        {"httpStatusCode": 200, "referenceId": "001xx000003DHPh"}
                    ]
                }
            ),
        )

        self.mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(
                {
                    "compositeResponse": [
                        {"httpStatusCode": 200, "referenceId": "001xx000003DHPh"}
                    ]
                }
            ),
        )

        update_dict = {  # no '_' key, so will need to fetch type
            "001xx000003DHPh": {"Name": "Updated Account"}
        }

        result = self.crud_client.cupdate(update_dict)

        assert result is not None

        call_args = self.mock_http_client.send_request.call_args
        body = json.loads(call_args[1]["body"])
        assert "None" in body["compositeRequest"][0]["url"]

    def test_cupdate_with_batching(self):
        """Test update operation with batch processing."""
        # Setup mocks
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (
            200,
            json.dumps({"compositeResponse": [{"httpStatusCode": 200}]}),
        )

        # Test data - 2 records with batch_size=1 to force 2 batches
        update_dict = {
            "001xx000003DHPh": {"_": "Account", "Name": "Account 1"},
            "001xx000003DHPi": {"_": "Account", "Name": "Account 2"},
        }

        # Execute
        result = self.crud_client.cupdate(update_dict, batch_size=1)

        # Verify
        assert len(result) == 2

        # Verify HTTP client was called twice (once per batch)
        assert self.mock_http_client.send_request.call_count == 2

    def test_cupdate_http_error(self):
        """Test update operation with HTTP error."""
        # Setup mocks
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (400, "Bad Request")

        # Test data
        update_dict = {"001xx000003DHPh": {"_": "Account", "Name": "Test"}}

        # Execute
        result = self.crud_client.cupdate(update_dict)

        # Verify
        assert result is None

    def test_cdelete_success(self):
        """Test successful delete operation."""
        # Setup mocks
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (
            200,
            json.dumps(
                [
                    {"id": "001xx000003DHPh", "success": True},
                    {"id": "001xx000003DHPi", "success": True},
                ]
            ),
        )

        # Test data
        ids = ["001xx000003DHPh", "001xx000003DHPi"]

        # Execute
        result = self.crud_client.cdelete(ids)

        # Verify
        expected = [
            {"id": "001xx000003DHPh", "success": True},
            {"id": "001xx000003DHPi", "success": True},
        ]
        assert result == expected

        # Verify HTTP client call
        self.mock_http_client.send_request.assert_called_once()
        call_args = self.mock_http_client.send_request.call_args
        assert call_args[1]["method"] == "DELETE"
        assert "001xx000003DHPh,001xx000003DHPi" in call_args[1]["endpoint"]
        assert "allOrNone=false" in call_args[1]["endpoint"]

    def test_cdelete_with_batching(self):
        """Test delete operation with batch processing."""
        # Setup mocks
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (
            200,
            json.dumps([{"id": "001xx000003DHPh", "success": True}]),
        )

        # Test data - 2 IDs with batch_size=1 to force 2 batches
        ids = ["001xx000003DHPh", "001xx000003DHPi"]

        # Execute
        result = self.crud_client.cdelete(ids, batch_size=1)

        # Verify
        assert len(result) == 2

        # Verify HTTP client was called twice (once per batch)
        assert self.mock_http_client.send_request.call_count == 2

    def test_cdelete_http_error(self):
        """Test delete operation with HTTP error."""
        # Setup mocks
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_request.return_value = (400, "Bad Request")

        # Test data
        ids = ["001xx000003DHPh"]

        # Execute
        result = self.crud_client.cdelete(ids)

        # Verify
        assert result is None

    def test_cdelete_empty_ids(self):
        """Test delete operation with empty IDs list."""
        # Execute
        result = self.crud_client.cdelete([])

        # Verify
        assert result is None

        # Verify no HTTP requests were made
        self.mock_http_client.send_request.assert_not_called()

    def test_read_static_resource_id_success(self):
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_authenticated_request.return_value = (
            200,
            "static resource content",
        )

        result = self.crud_client.read_static_resource_id("081xx000000001")

        assert result == "static resource content"
        self.mock_http_client.send_authenticated_request.assert_called_once_with(
            "GET", "/services/data/v65.0/sobjects/StaticResource/081xx000000001/Body"
        )

    def test_read_static_resource_name_with_namespace(self):
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        query_response = {"records": [{"Id": "081xx000000001"}], "totalSize": 1}

        self.mock_http_client.send_authenticated_request.side_effect = [
            (200, json.dumps(query_response)),
            (200, "static resource content"),
        ]

        result = self.crud_client.read_static_resource_name(
            "TestResource", "MyNamespace"
        )

        assert result == "static resource content"

        first_call = self.mock_http_client.send_authenticated_request.call_args_list[0]
        args, kwargs = first_call

        # Inspect for debugging:
        print("args:", args)
        print("kwargs:", kwargs)

        # Now check if endpoint is positional or keyword argument:
        endpoint_arg = None

        # If 2 or more positional args, endpoint is probably args[1]
        if len(args) > 1:
            endpoint_arg = args[1]
        # Else maybe keyword argument 'endpoint'
        elif "endpoint" in kwargs:
            endpoint_arg = kwargs["endpoint"]

        assert endpoint_arg is not None, "Endpoint argument missing in call"
        assert "MyNamespace" in endpoint_arg

    def test_read_static_resource_name_not_found(self):
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        query_response = {"records": [], "totalSize": 0}
        self.mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(query_response),
        )

        result = self.crud_client.read_static_resource_name("NonExistentResource")

        assert result is None
        assert self.mock_http_client.send_authenticated_request.call_count == 1

    def test_update_static_resource_id_success(self):
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        update_response = {"success": True}
        self.mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(update_response),
        )

        result = self.crud_client.update_static_resource_id(
            "081xx000000001", "new content"
        )

        assert result == {"success": True}
        self.mock_http_client.send_authenticated_request.assert_called_once()

        call_args = self.mock_http_client.send_authenticated_request.call_args
        args, kwargs = call_args

        # All arguments are keywords, so check kwargs
        assert kwargs.get("method") == "PATCH"
        assert (
            "/services/data/v65.0/sobjects/StaticResource/081xx000000001"
            in kwargs.get("endpoint", "")
        )

        body = kwargs.get("body")
        assert body is not None, "Request body missing in call"

        body_json = json.loads(body)
        expected_encoded = base64.b64encode("new content".encode("utf-8")).decode(
            "utf-8"
        )
        assert body_json["Body"] == expected_encoded

    def test_update_static_resource_id_error(self):
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        self.mock_http_client.send_authenticated_request.return_value = (
            400,
            "Bad Request",
        )

        result = self.crud_client.update_static_resource_id("081xx000000001", "content")

        assert result is None

    def test_update_static_resource_name_success(self):
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        query_response = {"records": [{"Id": "081xx000000001"}], "totalSize": 1}
        update_response = {"success": True}
        self.mock_http_client.send_authenticated_request.side_effect = [
            (200, json.dumps(query_response)),
            (200, json.dumps(update_response)),
        ]

        result = self.crud_client.update_static_resource_name(
            "TestResource", "new content"
        )

        assert result == {"success": True}
        assert self.mock_http_client.send_authenticated_request.call_count == 2

    def test_update_static_resource_name_not_found(self):
        self.mock_http_client.get_common_headers.return_value = {
            "Authorization": "Bearer token123"
        }
        query_response = {"records": [], "totalSize": 0}
        self.mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(query_response),
        )

        result = self.crud_client.update_static_resource_name(
            "NonExistentResource", "content"
        )

        assert result is None
        self.mock_http_client.send_authenticated_request.assert_called_once()
