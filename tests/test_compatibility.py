"""
Backward compatibility validation tests for the SFQ library refactor.

These tests ensure that the refactored modular implementation maintains
complete backward compatibility with the original monolithic implementation.
"""

import inspect
import json
from unittest.mock import patch

import pytest

from sfq import (
    SFAuth,
    __version__,
)


class TestImportCompatibility:
    """Test that all imports work exactly as they did before the refactor."""

    def test_main_class_import(self):
        """Test that SFAuth can be imported from the main package."""
        from sfq import SFAuth

        assert SFAuth is not None
        assert hasattr(SFAuth, "__init__")

    def test_exception_imports(self):
        """Test that all exception classes can be imported."""
        from sfq import (
            APIError,
            AuthenticationError,
            ConfigurationError,
            CRUDError,
            HTTPError,
            QueryError,
            QueryTimeoutError,
            SFQException,
            SOAPError,
        )

        # Verify exception hierarchy
        assert issubclass(AuthenticationError, SFQException)
        assert issubclass(APIError, SFQException)
        assert issubclass(QueryError, APIError)
        assert issubclass(QueryTimeoutError, QueryError)
        assert issubclass(CRUDError, APIError)
        assert issubclass(SOAPError, APIError)
        assert issubclass(
            HTTPError, SFQException
        )  # HTTPError inherits from SFQException, not APIError
        assert issubclass(ConfigurationError, SFQException)

    def test_utility_imports(self):
        """Test that utility functions can be imported."""
        from sfq import get_logger

        assert callable(get_logger)

    def test_package_metadata_imports(self):
        """Test that package metadata is accessible."""
        import sfq

        assert hasattr(sfq, "__version__")
        assert isinstance(sfq.__version__, str)


class TestSFAuthSignatureCompatibility:
    """Test that SFAuth class maintains all expected method signatures."""

    @pytest.fixture
    def mock_sf_auth(self):
        """Create a mock SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    def test_init_signature(self):
        """Test that __init__ method has the expected signature."""
        sig = inspect.signature(SFAuth.__init__)
        params = list(sig.parameters.keys())

        # Check required parameters are present
        expected_params = [
            "self",
            "instance_url",
            "client_id",
            "refresh_token",
            "client_secret",
            "api_version",
            "token_endpoint",
            "access_token",
            "token_expiration_time",
            "token_lifetime",
            "user_agent",
            "sforce_client",
            "proxy",
        ]

        for param in expected_params:
            assert param in params, f"Missing parameter: {param}"

    def test_query_method_signature(self, mock_sf_auth):
        """Test that query method has the expected signature."""
        sig = inspect.signature(mock_sf_auth.query)
        params = list(sig.parameters.keys())

        assert "query" in params
        assert "tooling" in params

        # Check default values
        assert sig.parameters["tooling"].default is False

    def test_tooling_query_method_signature(self, mock_sf_auth):
        """Test that tooling_query method has the expected signature."""
        sig = inspect.signature(mock_sf_auth.tooling_query)
        params = list(sig.parameters.keys())

        assert "query" in params

    def test_cquery_method_signature(self, mock_sf_auth):
        """Test that cquery method has the expected signature."""
        sig = inspect.signature(mock_sf_auth.cquery)
        params = list(sig.parameters.keys())

        assert "query_dict" in params
        assert "batch_size" in params
        assert "max_workers" in params

        # Check default values
        assert sig.parameters["batch_size"].default == 25
        assert sig.parameters["max_workers"].default is None

    def test_cdelete_method_signature(self, mock_sf_auth):
        """Test that cdelete method has the expected signature."""
        sig = inspect.signature(mock_sf_auth.cdelete)
        params = list(sig.parameters.keys())

        assert "ids" in params
        assert "batch_size" in params
        assert "max_workers" in params

        # Check default values
        assert sig.parameters["batch_size"].default == 200
        assert sig.parameters["max_workers"].default is None

    def test_cupdate_method_signature(self, mock_sf_auth):
        """Test that _cupdate method has the expected signature."""
        sig = inspect.signature(mock_sf_auth._cupdate)
        params = list(sig.parameters.keys())

        assert "update_dict" in params
        assert "batch_size" in params
        assert "max_workers" in params

        # Check default values
        assert sig.parameters["batch_size"].default == 25
        assert sig.parameters["max_workers"].default is None

    def test_create_method_signature(self, mock_sf_auth):
        """Test that _create method has the expected signature."""
        sig = inspect.signature(mock_sf_auth._create)
        params = list(sig.parameters.keys())

        assert "sobject" in params
        assert "insert_list" in params
        assert "batch_size" in params
        assert "max_workers" in params
        assert "api_type" in params

        # Check default values
        assert sig.parameters["batch_size"].default == 200
        assert sig.parameters["max_workers"].default is None
        assert sig.parameters["api_type"].default == "enterprise"

    def test_get_sobject_prefixes_method_signature(self, mock_sf_auth):
        """Test that get_sobject_prefixes method has the expected signature."""
        sig = inspect.signature(mock_sf_auth.get_sobject_prefixes)
        params = list(sig.parameters.keys())

        assert "key_type" in params

        # Check default values
        assert sig.parameters["key_type"].default == "id"

    def test_static_resource_methods_signatures(self, mock_sf_auth):
        """Test that static resource methods have expected signatures."""
        # read_static_resource_name
        sig = inspect.signature(mock_sf_auth.read_static_resource_name)
        params = list(sig.parameters.keys())
        assert "resource_name" in params
        assert "namespace" in params
        assert sig.parameters["namespace"].default is None

        # read_static_resource_id
        sig = inspect.signature(mock_sf_auth.read_static_resource_id)
        params = list(sig.parameters.keys())
        assert "resource_id" in params

        # update_static_resource_name
        sig = inspect.signature(mock_sf_auth.update_static_resource_name)
        params = list(sig.parameters.keys())
        assert "resource_name" in params
        assert "data" in params
        assert "namespace" in params
        assert sig.parameters["namespace"].default is None

        # update_static_resource_id
        sig = inspect.signature(mock_sf_auth.update_static_resource_id)
        params = list(sig.parameters.keys())
        assert "resource_id" in params
        assert "data" in params


class TestAttributeCompatibility:
    """Test that all public attributes are accessible and behave correctly."""

    @pytest.fixture
    def mock_sf_auth(self):
        """Create a mock SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
            api_version="v65.0",
            user_agent="test_agent",
            sforce_client="test_client",
        )

    def test_instance_url_attribute(self, mock_sf_auth):
        """Test that instance_url attribute is accessible."""
        assert hasattr(mock_sf_auth, "instance_url")
        assert mock_sf_auth.instance_url == "https://test.my.salesforce.com"

    def test_client_id_attribute(self, mock_sf_auth):
        """Test that client_id attribute is accessible."""
        assert hasattr(mock_sf_auth, "client_id")
        assert mock_sf_auth.client_id == "test_client_id"

    def test_client_secret_attribute(self, mock_sf_auth):
        """Test that client_secret attribute is accessible."""
        assert hasattr(mock_sf_auth, "client_secret")
        assert mock_sf_auth.client_secret == "test_client_secret"

    def test_refresh_token_attribute(self, mock_sf_auth):
        """Test that refresh_token attribute is accessible."""
        assert hasattr(mock_sf_auth, "refresh_token")
        assert mock_sf_auth.refresh_token == "test_refresh_token"

    def test_api_version_attribute(self, mock_sf_auth):
        """Test that api_version attribute is accessible."""
        assert hasattr(mock_sf_auth, "api_version")
        assert mock_sf_auth.api_version == "v65.0"

    def test_token_endpoint_attribute(self, mock_sf_auth):
        """Test that token_endpoint attribute is accessible."""
        assert hasattr(mock_sf_auth, "token_endpoint")
        assert mock_sf_auth.token_endpoint == "/services/oauth2/token"

    def test_access_token_attribute(self, mock_sf_auth):
        """Test that access_token attribute is accessible."""
        assert hasattr(mock_sf_auth, "access_token")
        # Initially None
        assert mock_sf_auth.access_token is None

    def test_token_expiration_time_attribute(self, mock_sf_auth):
        """Test that token_expiration_time attribute is accessible."""
        assert hasattr(mock_sf_auth, "token_expiration_time")
        # Initially None
        assert mock_sf_auth.token_expiration_time is None

    def test_token_lifetime_attribute(self, mock_sf_auth):
        """Test that token_lifetime attribute is accessible."""
        assert hasattr(mock_sf_auth, "token_lifetime")
        assert mock_sf_auth.token_lifetime == 15 * 60  # 15 minutes

    def test_user_agent_attribute(self, mock_sf_auth):
        """Test that user_agent attribute is accessible."""
        assert hasattr(mock_sf_auth, "user_agent")
        assert mock_sf_auth.user_agent == "test_agent"

    def test_sforce_client_attribute(self, mock_sf_auth):
        """Test that sforce_client attribute is accessible."""
        assert hasattr(mock_sf_auth, "sforce_client")
        assert mock_sf_auth.sforce_client == "test_client"

    def test_proxy_attribute(self, mock_sf_auth):
        """Test that proxy attribute is accessible."""
        assert hasattr(mock_sf_auth, "proxy")
        # Should be None when no proxy is configured
        assert mock_sf_auth.proxy is None

    def test_org_id_attribute(self, mock_sf_auth):
        """Test that org_id attribute is accessible."""
        assert hasattr(mock_sf_auth, "org_id")
        # Initially None
        assert mock_sf_auth.org_id is None

    def test_user_id_attribute(self, mock_sf_auth):
        """Test that user_id attribute is accessible."""
        assert hasattr(mock_sf_auth, "user_id")
        # Initially None
        assert mock_sf_auth.user_id is None

    def test_version_attribute(self, mock_sf_auth):
        """Test that __version__ attribute is accessible."""
        assert hasattr(mock_sf_auth, "__version__")
        assert isinstance(mock_sf_auth.__version__, str)


class TestMethodReturnTypes:
    """Test that methods return the expected types."""

    @pytest.fixture
    def mock_sf_auth(self):
        """Create a mock SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_query_return_type(self, mock_request, mock_sf_auth):
        """Test that query method returns Optional[Dict[str, Any]]."""
        # Mock successful response
        mock_request.return_value = (200, '{"records": [], "totalSize": 0}')

        result = mock_sf_auth.query("SELECT Id FROM Account")
        assert result is None or isinstance(result, dict)

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_tooling_query_return_type(self, mock_request, mock_sf_auth):
        """Test that tooling_query method returns Optional[Dict[str, Any]]."""
        # Mock successful response
        mock_request.return_value = (200, '{"records": [], "totalSize": 0}')

        result = mock_sf_auth.tooling_query("SELECT Id FROM ApexClass")
        assert result is None or isinstance(result, dict)

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_cquery_return_type(self, mock_request, mock_sf_auth):
        """Test that cquery method returns Optional[Dict[str, Any]]."""
        # Mock successful response
        mock_request.return_value = (200, '{"compositeResponse": []}')

        result = mock_sf_auth.cquery({"test": "SELECT Id FROM Account"})
        assert result is None or isinstance(result, dict)

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_cdelete_return_type(self, mock_request, mock_sf_auth):
        """Test that cdelete method returns Optional[Dict[str, Any]]."""
        # Mock successful response
        mock_request.return_value = (200, "[]")

        result = mock_sf_auth.cdelete(["001000000000001"])
        assert result is None or isinstance(result, dict)

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_cupdate_return_type(self, mock_request, mock_sf_auth):
        """Test that _cupdate method returns Optional[Dict[str, Any]]."""
        # Mock successful response
        mock_request.return_value = (200, '{"compositeResponse": []}')

        result = mock_sf_auth._cupdate({"001000000000001": {"Name": "Test"}})
        assert result is None or isinstance(result, dict)

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_get_sobject_prefixes_return_type(self, mock_request, mock_sf_auth):
        """Test that get_sobject_prefixes method returns Optional[Dict[str, str]]."""
        # Mock successful response
        mock_request.return_value = (200, '{"sobjects": []}')

        result = mock_sf_auth.get_sobject_prefixes()
        assert result is None or isinstance(result, dict)

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_limits_return_type(self, mock_request, mock_sf_auth):
        """Test that limits method returns Optional[Dict[str, Any]]."""
        # Mock successful response
        mock_request.return_value = (
            200,
            '{"DailyApiRequests": {"Max": 15000, "Remaining": 14999}}',
        )

        result = mock_sf_auth.limits()
        assert result is None or isinstance(result, dict)

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_static_resource_methods_return_types(self, mock_request, mock_sf_auth):
        """Test that static resource methods return expected types."""

        # --- READ OPERATIONS ---

        # Mock for read_static_resource_id (returns plain string)
        mock_request.return_value = (200, "test content")
        try:
            result = mock_sf_auth.read_static_resource_id("001000000000001")
            print("read_static_resource_id result:", repr(result))
            assert result is None or isinstance(result, str)
        except Exception as e:
            pytest.fail(f"read_static_resource_id raised {type(e).__name__}: {e}")

        # Mock for read_static_resource_name (expects JSON)
        mock_request.return_value = (
            200,
            '{"id": "001000000000001", "name": "TestResource"}',
        )  # valid JSON
        try:
            result = mock_sf_auth.read_static_resource_name("TestResource")
            print("read_static_resource_name result:", repr(result))
            assert result is None or isinstance(result, str)
        except Exception as e:
            pytest.fail(f"read_static_resource_name raised {type(e).__name__}: {e}")

        # --- UPDATE OPERATIONS ---
        mock_request.return_value = (200, '{"success": true}')  # valid JSON
        try:
            result = mock_sf_auth.update_static_resource_id(
                "001000000000001", "new content"
            )
            print("update_static_resource_id result:", repr(result))
            assert result is None or isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"update_static_resource_id raised {type(e).__name__}: {e}")

        try:
            result = mock_sf_auth.update_static_resource_name(
                "TestResource", "new content"
            )
            print("update_static_resource_name result:", repr(result))
            assert result is None or isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"update_static_resource_name raised {type(e).__name__}: {e}")


class TestErrorHandlingCompatibility:
    """Test that error handling behavior is preserved."""

    @pytest.fixture
    def mock_sf_auth(self):
        """Create a mock SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    def test_invalid_instance_url_handling(self):
        """Test that invalid instance URL is handled gracefully."""
        # The current implementation formats URLs but doesn't validate during init
        sf_auth = SFAuth(
            instance_url="invalid-url",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )
        # Should format to HTTPS
        assert sf_auth.instance_url == "https://invalid-url"

        # But validation method should return False
        assert sf_auth._auth_manager.validate_instance_url() is False

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_query_error_handling(self, mock_request, mock_sf_auth):
        """Test that query errors are handled consistently."""
        # Mock error response
        mock_request.return_value = (400, '{"error": "INVALID_QUERY"}')

        result = mock_sf_auth.query("INVALID QUERY")
        assert result is None

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_cquery_error_handling(self, mock_request, mock_sf_auth):
        """Test that cquery errors are handled consistently."""
        # Mock error response
        mock_request.return_value = (400, '{"error": "INVALID_REQUEST"}')

        result = mock_sf_auth.cquery({"test": "INVALID QUERY"})
        # cquery returns error data for failed queries, not None
        assert result is not None
        assert isinstance(result, dict)
        assert "test" in result
        assert "error" in result["test"]

    def test_cdelete_empty_ids_handling(self, mock_sf_auth):
        """Test that cdelete handles empty ID lists correctly."""
        result = mock_sf_auth.cdelete([])
        # Should return None or empty result for empty input
        assert result is None or (isinstance(result, dict) and len(result) == 0)


class TestPrivateMethodCompatibility:
    """Test that private methods used by consumers are still available."""

    @pytest.fixture
    def mock_sf_auth(self):
        """Create a mock SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    def test_refresh_token_if_needed_method(self, mock_sf_auth):
        """Test that _refresh_token_if_needed method is available."""
        assert hasattr(mock_sf_auth, "_refresh_token_if_needed")
        assert callable(mock_sf_auth._refresh_token_if_needed)

    def test_soap_methods_available(self, mock_sf_auth):
        """Test that SOAP-related private methods are available."""
        assert hasattr(mock_sf_auth, "_gen_soap_envelope")
        assert callable(mock_sf_auth._gen_soap_envelope)

        assert hasattr(mock_sf_auth, "_gen_soap_header")
        assert callable(mock_sf_auth._gen_soap_header)

        assert hasattr(mock_sf_auth, "_gen_soap_body")
        assert callable(mock_sf_auth._gen_soap_body)

        assert hasattr(mock_sf_auth, "_extract_soap_result_fields")
        assert callable(mock_sf_auth._extract_soap_result_fields)

    def test_xml_conversion_methods_available(self, mock_sf_auth):
        """Test that XML conversion methods are available."""
        assert hasattr(mock_sf_auth, "_xml_to_json")
        assert callable(mock_sf_auth._xml_to_json)

        assert hasattr(mock_sf_auth, "_xml_to_dict")
        assert callable(mock_sf_auth._xml_to_dict)

    def test_debug_methods_available(self, mock_sf_auth):
        """Test that debug methods are available."""
        assert hasattr(mock_sf_auth, "debug_cleanup")
        assert callable(mock_sf_auth.debug_cleanup)

    def test_frontdoor_method_available(self, mock_sf_auth):
        """Test that open_frontdoor method is available."""
        assert hasattr(mock_sf_auth, "open_frontdoor")
        assert callable(mock_sf_auth.open_frontdoor)


class TestBehaviorConsistency:
    """Test that the behavior of methods is consistent with the original implementation."""

    @pytest.fixture
    def mock_sf_auth(self):
        """Create a mock SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    def test_instance_url_normalization(self):
        """Test that instance URL normalization works as expected."""
        # Test with trailing slash - current implementation preserves it during init
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com/",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )
        # The init preserves trailing slash, but normalize method removes it
        assert sf_auth.instance_url == "https://test.my.salesforce.com/"
        assert (
            sf_auth._auth_manager.normalize_instance_url()
            == "https://test.my.salesforce.com"
        )

        # Test with http -> https conversion
        sf_auth = SFAuth(
            instance_url="http://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )
        assert sf_auth.instance_url == "https://test.my.salesforce.com"

    def test_sforce_client_comma_removal(self):
        """Test that commas are removed from sforce_client."""
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
            sforce_client="test,client,with,commas",
        )
        assert "," not in sf_auth.sforce_client

    @patch("sfq.http_client.HTTPClient.send_request")
    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_query_pagination_behavior(
        self, mock_auth_request, mock_request, mock_sf_auth
    ):
        """Test that query pagination behavior is preserved."""

        # Mock initial query response (triggers pagination)
        mock_auth_request.return_value = (
            200,
            json.dumps(
                {
                    "records": [{"Id": "001"}],
                    "totalSize": 2,
                    "nextRecordsUrl": "/services/data/v65.0/query/next",
                    "done": False,
                }
            ),
        )

        # Mock pagination response (final page)
        mock_request.return_value = (
            200,
            json.dumps({"records": [{"Id": "002"}], "totalSize": 2, "done": True}),
        )

        result = mock_sf_auth.query("SELECT Id FROM Account")

        # Assert that both requests were called
        assert mock_auth_request.call_count == 1
        assert mock_request.call_count == 2

        # Check that the query combined both records
        assert isinstance(result, dict)
        assert "records" in result
        assert len(result["records"]) == 2
        assert result["records"][0]["Id"] == "001"
        assert result["records"][1]["Id"] == "002"
        assert result["totalSize"] == 2
        assert result["done"] is True

    def test_cquery_empty_dict_handling(self, mock_sf_auth):
        """Test that cquery handles empty dictionary correctly."""
        result = mock_sf_auth.cquery({})
        # Should return None or empty result for empty input
        assert result is None or (isinstance(result, dict) and len(result) == 0)

    def test_default_parameter_values(self, mock_sf_auth):
        """Test that default parameter values are preserved."""
        # Test api_version default
        assert mock_sf_auth.api_version == "v65.0"

        # Test token_endpoint default
        assert mock_sf_auth.token_endpoint == "/services/oauth2/token"

        # Test token_lifetime default
        assert mock_sf_auth.token_lifetime == 15 * 60

        # Test user_agent default
        sf_auth_default = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )
        assert sf_auth_default.user_agent == f"sfq/{__version__}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
