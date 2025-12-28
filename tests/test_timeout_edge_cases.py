"""
Edge case handling and validation tests for timeout retry functionality.

This module tests edge cases, malformed responses, connection reuse,
different HTTP methods, retry count validation, and thread safety considerations.
"""

import errno
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch, call

import pytest

from sfq.auth import AuthManager
from sfq.exceptions import QueryTimeoutError
from sfq.http_client import HTTPClient
from sfq.timeout_detector import TimeoutDetector


class TestMalformedResponseHandling:
    """Test handling of malformed responses during timeout detection."""

    @pytest.fixture
    def auth_manager(self):
        """Create a mock AuthManager for testing."""
        auth_manager = Mock(spec=AuthManager)
        auth_manager.instance_url = "https://test.my.salesforce.com"
        auth_manager.api_version = "v65.0"
        auth_manager.access_token = "test_token_123"
        auth_manager.get_proxy_config.return_value = None
        auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
        auth_manager.needs_token_refresh.return_value = False
        auth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    def test_malformed_json_response_not_detected_as_timeout(self, http_client):
        """Test that malformed JSON responses without timeout message are not detected as timeouts."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return malformed JSON with 400 status but no timeout message
            mock_internal.return_value = (400, '{"message":"Invalid query syntax", "errorCode":}')

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            # Should not retry because it's not a timeout response
            assert status == 400
            assert mock_internal.call_count == 1

    def test_empty_response_body_with_400_status(self, http_client):
        """Test that empty response body with 400 status is not detected as timeout."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return empty body with 400 status
            mock_internal.return_value = (400, "")

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            # Should not retry because empty body doesn't contain timeout message
            assert status == 400
            assert data == ""
            assert mock_internal.call_count == 1

    def test_null_response_body_with_400_status(self, http_client):
        """Test that null response body with 400 status is not detected as timeout."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return None body with 400 status
            mock_internal.return_value = (400, None)

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            # Should not retry because None body doesn't contain timeout message
            assert status == 400
            assert data is None
            assert mock_internal.call_count == 1

    def test_partial_timeout_message_in_malformed_response(self, http_client):
        """Test partial timeout message in malformed response."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return response with partial timeout message but malformed structure
            mock_internal.side_effect = [
                (400, 'Your query request was running for too long. {"invalid": json}'),
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            # Should retry because timeout message is present regardless of JSON validity
            assert status == 200
            assert data == '{"records": []}'
            assert mock_internal.call_count == 2

    def test_timeout_message_in_html_error_response(self, http_client):
        """Test timeout message detection in HTML error response."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return HTML response with timeout message
            html_response = """
            <html>
                <body>
                    <h1>Error</h1>
                    <p>Your query request was running for too long. Please try again.</p>
                </body>
            </html>
            """
            mock_internal.side_effect = [
                (400, html_response),
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            # Should retry because timeout message is present in HTML
            assert status == 200
            assert data == '{"records": []}'
            assert mock_internal.call_count == 2

    def test_case_sensitive_timeout_message_detection(self, http_client):
        """Test that timeout message detection is case sensitive."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return response with lowercase timeout message
            mock_internal.return_value = (400, "your query request was running for too long.")

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            # Should not retry because message is case sensitive
            assert status == 400
            assert mock_internal.call_count == 1

    def test_unicode_characters_in_timeout_response(self, http_client):
        """Test handling of unicode characters in timeout response."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return response with unicode characters and timeout message
            unicode_response = '{"message":"Your query request was running for too long. 请重试","errorCode":"QUERY_TIMEOUT"}'
            mock_internal.side_effect = [
                (400, unicode_response),
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            # Should retry because timeout message and error code are present
            assert status == 200
            assert data == '{"records": []}'
            assert mock_internal.call_count == 2


class TestConnectionReuseValidation:
    """Test connection reuse during retry attempts."""

    @pytest.fixture
    def auth_manager(self):
        """Create a mock AuthManager for testing."""
        auth_manager = Mock(spec=AuthManager)
        auth_manager.instance_url = "https://test.my.salesforce.com"
        auth_manager.api_version = "v65.0"
        auth_manager.access_token = "test_token_123"
        auth_manager.get_proxy_config.return_value = None
        auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
        auth_manager.needs_token_refresh.return_value = False
        auth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    @patch('sfq.http_client.http.client.HTTPSConnection')
    def test_connection_reuse_during_retries(self, mock_https_connection, http_client):
        """Test that connection creation patterns are consistent during retries."""
        # Mock the connection instance
        mock_conn_instance = Mock()
        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.read.return_value = b'{"records": []}'
        mock_response.getheaders.return_value = []
        
        mock_conn_instance.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn_instance

        # Mock the internal method to simulate timeout then success
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 200
            assert data == '{"records": []}'
            assert mock_internal.call_count == 2

            # Verify that both calls used the same parameters (indicating consistent connection handling)
            first_call = mock_internal.call_args_list[0]
            second_call = mock_internal.call_args_list[1]
            assert first_call == second_call

    def test_connection_parameters_preserved_across_retries(self, http_client):
        """Test that connection parameters are preserved across retry attempts."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Mock timeout then success
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (200, '{"success": true}')
            ]

            # Test with custom headers and body
            method = "POST"
            endpoint = "/services/data/v65.0/composite"
            body = '{"compositeRequest": [{"method": "GET", "url": "/services/data/v65.0/sobjects/Account/001"}]}'
            additional_headers = {
                "Custom-Header": "test-value",
                "X-Request-ID": "12345",
                "Content-Length": str(len(body))
            }

            status, data = http_client.send_authenticated_request_with_retry(
                method, endpoint, body, additional_headers, max_retries=3
            )

            assert status == 200
            assert data == '{"success": true}'
            assert mock_internal.call_count == 2

            # Verify exact parameter preservation
            first_call_args = mock_internal.call_args_list[0][0]
            second_call_args = mock_internal.call_args_list[1][0]
            
            assert first_call_args == second_call_args
            assert first_call_args == (method, endpoint, body, additional_headers)

    def test_auth_headers_consistency_across_retries(self, http_client):
        """Test that authentication headers remain consistent across retries."""
        with patch.object(http_client, 'get_common_headers') as mock_get_headers:
            with patch.object(http_client, 'send_request') as mock_send_request:
                # Mock headers method to return consistent headers
                mock_headers = {
                    "Authorization": "Bearer test_token_123",
                    "User-Agent": "test-agent/1.0",
                    "Content-Type": "application/json"
                }
                mock_get_headers.return_value = mock_headers

                # Mock send_request to simulate timeout then success
                mock_send_request.side_effect = [
                    (400, "Your query request was running for too long."),
                    (200, '{"records": []}')
                ]

                status, data = http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=3
                )

                assert status == 200
                assert data == '{"records": []}'
                
                # Verify get_common_headers was called consistently
                assert mock_get_headers.call_count == 2
                for call in mock_get_headers.call_args_list:
                    assert call[1]['include_auth'] is True

                # Verify send_request was called with same headers both times
                assert mock_send_request.call_count == 2
                first_headers = mock_send_request.call_args_list[0][0][2]
                second_headers = mock_send_request.call_args_list[1][0][2]
                assert first_headers == second_headers == mock_headers


class TestHTTPMethodValidation:
    """Test retry behavior with different HTTP methods."""

    @pytest.fixture
    def auth_manager(self):
        """Create a mock AuthManager for testing."""
        auth_manager = Mock(spec=AuthManager)
        auth_manager.instance_url = "https://test.my.salesforce.com"
        auth_manager.api_version = "v65.0"
        auth_manager.access_token = "test_token_123"
        auth_manager.get_proxy_config.return_value = None
        auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
        auth_manager.needs_token_refresh.return_value = False
        auth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    @pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE", "PUT"])
    def test_retry_behavior_with_different_http_methods(self, method, http_client):
        """Test that retry logic works consistently across different HTTP methods."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Mock timeout then success for each method
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (200, '{"success": true}')
            ]

            endpoint = f"/services/data/v65.0/sobjects/Account/001"
            body = '{"Name": "Test Account"}' if method in ["POST", "PATCH", "PUT"] else None

            status, data = http_client.send_authenticated_request_with_retry(
                method, endpoint, body, max_retries=3
            )

            assert status == 200
            assert data == '{"success": true}'
            assert mock_internal.call_count == 2

            # Verify method was preserved across retries
            first_call_method = mock_internal.call_args_list[0][0][0]
            second_call_method = mock_internal.call_args_list[1][0][0]
            assert first_call_method == second_call_method == method

    def test_get_request_retry_with_query_parameters(self, http_client):
        """Test GET request retry with query parameters in endpoint."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            mock_internal.side_effect = [
                (400, '[{"errorCode":"QUERY_TIMEOUT"}]'),
                (200, '{"records": [{"Id": "001"}]}')
            ]

            endpoint = "/services/data/v65.0/query?q=SELECT+Id+FROM+Account+LIMIT+1"
            
            status, data = http_client.send_authenticated_request_with_retry(
                "GET", endpoint, max_retries=3
            )

            assert status == 200
            assert data == '{"records": [{"Id": "001"}]}'
            assert mock_internal.call_count == 2

            # Verify endpoint with query parameters was preserved
            first_endpoint = mock_internal.call_args_list[0][0][1]
            second_endpoint = mock_internal.call_args_list[1][0][1]
            assert first_endpoint == second_endpoint == endpoint

    def test_post_request_retry_with_large_body(self, http_client):
        """Test POST request retry with large request body."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (200, '{"success": true}')
            ]

            # Create a large composite request body
            large_body = json.dumps({
                "compositeRequest": [
                    {
                        "method": "POST",
                        "url": "/services/data/v65.0/sobjects/Account",
                        "body": {"Name": f"Test Account {i}"}
                    }
                    for i in range(100)  # 100 records
                ]
            })

            status, data = http_client.send_authenticated_request_with_retry(
                "POST", "/services/data/v65.0/composite", large_body, max_retries=3
            )

            assert status == 200
            assert data == '{"success": true}'
            assert mock_internal.call_count == 2

            # Verify large body was preserved across retries
            first_body = mock_internal.call_args_list[0][0][2]
            second_body = mock_internal.call_args_list[1][0][2]
            assert first_body == second_body == large_body
            assert len(first_body) > 1000  # Verify it's actually large

    def test_patch_request_retry_with_custom_headers(self, http_client):
        """Test PATCH request retry with custom headers."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            mock_internal.side_effect = [
                timeout_exception,
                (200, '{"updated": true}')
            ]

            custom_headers = {
                "If-Match": "etag-value-123",
                "X-Custom-Header": "custom-value",
                "Content-Type": "application/json; charset=utf-8"
            }
            body = '{"Name": "Updated Account Name"}'

            status, data = http_client.send_authenticated_request_with_retry(
                "PATCH", "/services/data/v65.0/sobjects/Account/001", body, custom_headers, max_retries=3
            )

            assert status == 200
            assert data == '{"updated": true}'
            assert mock_internal.call_count == 2

            # Verify custom headers were preserved
            first_headers = mock_internal.call_args_list[0][0][3]
            second_headers = mock_internal.call_args_list[1][0][3]
            assert first_headers == second_headers == custom_headers

    def test_delete_request_retry_without_body(self, http_client):
        """Test DELETE request retry without request body."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            mock_internal.side_effect = [
                (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
                (204, '')  # DELETE typically returns 204 No Content
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "DELETE", "/services/data/v65.0/sobjects/Account/001", max_retries=3
            )

            assert status == 204
            assert data == ''
            assert mock_internal.call_count == 2

            # Verify DELETE method and no body
            first_call = mock_internal.call_args_list[0][0]
            second_call = mock_internal.call_args_list[1][0]
            assert first_call[0] == second_call[0] == "DELETE"
            assert first_call[2] == second_call[2] is None  # No body


class TestRetryCountValidation:
    """Test validation for retry count limits and parameter preservation."""

    @pytest.fixture
    def auth_manager(self):
        """Create a mock AuthManager for testing."""
        auth_manager = Mock(spec=AuthManager)
        auth_manager.instance_url = "https://test.my.salesforce.com"
        auth_manager.api_version = "v65.0"
        auth_manager.access_token = "test_token_123"
        auth_manager.get_proxy_config.return_value = None
        auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
        auth_manager.needs_token_refresh.return_value = False
        auth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    @pytest.mark.parametrize("max_retries", [0, 1, 2, 3, 5, 10])
    def test_retry_count_limits_respected(self, max_retries, http_client):
        """Test that retry count limits are properly respected."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # All calls return timeout
            mock_internal.return_value = (400, "Your query request was running for too long.")

            with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=max_retries
                )

            # Should try initial + max_retries attempts
            expected_calls = max_retries + 1
            assert mock_internal.call_count == expected_calls

    def test_negative_retry_count_handled_gracefully(self, http_client):
        """Test that negative retry count is handled gracefully."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            mock_internal.return_value = (400, "Your query request was running for too long.")

            with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=-1
                )

            # Should only try once (no retries for negative count)
            assert mock_internal.call_count == 1

    def test_zero_retry_count_no_retries(self, http_client):
        """Test that zero retry count results in no retries."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            mock_internal.return_value = (400, "Your query request was running for too long.")

            with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=0
                )

            # Should only try once (no retries)
            assert mock_internal.call_count == 1

    def test_large_retry_count_performance(self, http_client):
        """Test performance with large retry count."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return timeout for first 49 attempts, success on 50th
            responses = [(400, "Your query request was running for too long.")] * 49
            responses.append((200, '{"records": []}'))
            mock_internal.side_effect = responses

            start_time = time.time()
            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=50
            )
            end_time = time.time()

            assert status == 200
            assert data == '{"records": []}'
            assert mock_internal.call_count == 50

            # Should complete reasonably quickly (no artificial delays)
            assert end_time - start_time < 1.0  # Less than 1 second

    def test_parameter_preservation_across_many_retries(self, http_client):
        """Test that parameters are preserved across many retry attempts."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return timeout for first 9 attempts, success on 10th
            responses = [(400, "Your query request was running for too long.")] * 9
            responses.append((200, '{"success": true}'))
            mock_internal.side_effect = responses

            method = "POST"
            endpoint = "/services/data/v65.0/composite/batch"
            body = '{"batchRequests": [{"method": "GET", "url": "/services/data/v65.0/sobjects/Account/001"}]}'
            headers = {"Custom-Header": "test-value", "X-Batch-ID": "batch-123"}

            status, data = http_client.send_authenticated_request_with_retry(
                method, endpoint, body, headers, max_retries=10
            )

            assert status == 200
            assert data == '{"success": true}'
            assert mock_internal.call_count == 10

            # Verify all calls had identical parameters
            expected_args = (method, endpoint, body, headers)
            for call in mock_internal.call_args_list:
                assert call[0] == expected_args

    @patch("sfq.http_client.logger")
    def test_retry_count_logging_accuracy(self, mock_logger, http_client):
        """Test that retry count logging is accurate."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return timeout for first 2 attempts, success on 3rd
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (400, "Your query request was running for too long."),
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 200
            assert mock_internal.call_count == 3

            # Verify debug logging shows correct attempt numbers
            debug_calls = [call for call in mock_logger.debug.call_args_list]
            assert len(debug_calls) == 3  # 2 retry logs + 1 success log

            # Check first retry log
            first_retry = debug_calls[0]
            assert 1 in first_retry[0][1:]  # attempt 1
            assert 4 in first_retry[0][1:]  # total 4 attempts

            # Check second retry log
            second_retry = debug_calls[1]
            assert 2 in second_retry[0][1:]  # attempt 2
            assert 4 in second_retry[0][1:]  # total 4 attempts

            # Check success log
            success_log = debug_calls[2]
            assert 3 in success_log[0][1:]  # attempt 3
            assert 4 in success_log[0][1:]  # total 4 attempts


class TestConcurrentRequestScenarios:
    """Test concurrent request scenarios to ensure thread safety considerations."""

    @pytest.fixture
    def auth_manager(self):
        """Create a mock AuthManager for testing."""
        auth_manager = Mock(spec=AuthManager)
        auth_manager.instance_url = "https://test.my.salesforce.com"
        auth_manager.api_version = "v65.0"
        auth_manager.access_token = "test_token_123"
        auth_manager.get_proxy_config.return_value = None
        auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
        auth_manager.needs_token_refresh.return_value = False
        auth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        return auth_manager

    def test_multiple_http_clients_concurrent_requests(self, auth_manager):
        """Test multiple HTTPClient instances making concurrent requests."""
        # Create multiple HTTPClient instances
        clients = [
            HTTPClient(auth_manager, user_agent=f"test-agent-{i}/1.0")
            for i in range(5)
        ]

        results = []
        
        def make_request(client, client_id):
            """Make a request with a specific client."""
            with patch.object(client, '_send_authenticated_request_internal') as mock_internal:
                # Simulate timeout then success for each client
                mock_internal.side_effect = [
                    (400, "Your query request was running for too long."),
                    (200, f'{{"client_id": {client_id}, "records": []}}')
                ]

                status, data = client.send_authenticated_request_with_retry(
                    "GET", f"/services/data/v65.0/query?client={client_id}", max_retries=3
                )
                
                return (client_id, status, data, mock_internal.call_count)

        # Execute requests concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(make_request, clients[i], i)
                for i in range(5)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())

        # Verify all requests completed successfully
        assert len(results) == 5
        for client_id, status, data, call_count in results:
            assert status == 200
            assert f'"client_id": {client_id}' in data
            assert call_count == 2  # Initial + 1 retry

    def test_single_client_concurrent_requests_thread_safety(self, auth_manager):
        """Test single HTTPClient instance handling concurrent requests."""
        http_client = HTTPClient(auth_manager, user_agent="test-agent/1.0")
        results = []
        request_counter = 0
        counter_lock = threading.Lock()

        def make_concurrent_request(request_id):
            """Make a concurrent request with the same client."""
            nonlocal request_counter
            
            with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
                # Each request gets its own mock to avoid interference
                with counter_lock:
                    request_counter += 1
                    current_count = request_counter

                # Simulate different timeout scenarios for each request
                if request_id % 2 == 0:
                    # Even requests: server timeout then success
                    mock_internal.side_effect = [
                        (400, "Your query request was running for too long."),
                        (200, f'{{"request_id": {request_id}, "type": "server_timeout"}}')
                    ]
                else:
                    # Odd requests: connection timeout then success
                    timeout_exception = OSError("Connection timed out")
                    timeout_exception.errno = errno.ETIMEDOUT
                    mock_internal.side_effect = [
                        timeout_exception,
                        (200, f'{{"request_id": {request_id}, "type": "connection_timeout"}}')
                    ]

                status, data = http_client.send_authenticated_request_with_retry(
                    "GET", f"/services/data/v65.0/query?req={request_id}", max_retries=3
                )
                
                return (request_id, status, data, mock_internal.call_count, current_count)

        # Execute concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(make_concurrent_request, i)
                for i in range(10)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())

        # Verify all requests completed successfully
        assert len(results) == 10
        for request_id, status, data, call_count, count in results:
            assert status == 200
            assert f'"request_id": {request_id}' in data
            assert call_count == 2  # Initial + 1 retry
            assert count <= 10  # Counter should not exceed number of requests

    def test_concurrent_requests_with_different_retry_counts(self, auth_manager):
        """Test concurrent requests with different retry count configurations."""
        http_client = HTTPClient(auth_manager, user_agent="test-agent/1.0")
        results = []

        def make_request_with_retries(request_id, max_retries):
            """Make a request with specific retry count."""
            with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
                # Return timeout for all attempts except the last one
                timeout_responses = [(400, "Your query request was running for too long.")] * max_retries
                timeout_responses.append((200, f'{{"request_id": {request_id}, "max_retries": {max_retries}}}'))
                mock_internal.side_effect = timeout_responses

                status, data = http_client.send_authenticated_request_with_retry(
                    "GET", f"/services/data/v65.0/query?req={request_id}", max_retries=max_retries
                )
                
                return (request_id, status, data, mock_internal.call_count, max_retries)

        # Execute requests with different retry counts concurrently
        retry_counts = [1, 2, 3, 4, 5]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(make_request_with_retries, i, retry_counts[i])
                for i in range(5)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())

        # Verify all requests completed with correct retry counts
        assert len(results) == 5
        for request_id, status, data, call_count, expected_retries in results:
            assert status == 200
            assert f'"request_id": {request_id}' in data
            assert f'"max_retries": {expected_retries}' in data
            assert call_count == expected_retries + 1  # Initial + retries

    def test_concurrent_timeout_detection_consistency(self, auth_manager):
        """Test that timeout detection is consistent across concurrent requests."""
        http_client = HTTPClient(auth_manager, user_agent="test-agent/1.0")
        results = []

        def test_timeout_detection(scenario_id):
            """Test timeout detection in concurrent scenario."""
            with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
                if scenario_id % 3 == 0:
                    # Server timeout scenario
                    mock_internal.side_effect = [
                        (400, "Your query request was running for too long."),
                        (200, f'{{"scenario": {scenario_id}, "type": "server"}}')
                    ]
                elif scenario_id % 3 == 1:
                    # Connection timeout scenario
                    timeout_exception = OSError("Connection timed out")
                    timeout_exception.errno = errno.ETIMEDOUT
                    mock_internal.side_effect = [
                        timeout_exception,
                        (200, f'{{"scenario": {scenario_id}, "type": "connection"}}')
                    ]
                else:
                    # Non-timeout scenario
                    mock_internal.return_value = (400, "Invalid query syntax")

                try:
                    status, data = http_client.send_authenticated_request_with_retry(
                        "GET", f"/services/data/v65.0/query?scenario={scenario_id}", max_retries=3
                    )
                    return (scenario_id, status, data, mock_internal.call_count, "success")
                except Exception as e:
                    return (scenario_id, None, str(e), mock_internal.call_count, "exception")

        # Execute concurrent timeout detection tests
        with ThreadPoolExecutor(max_workers=9) as executor:
            futures = [
                executor.submit(test_timeout_detection, i)
                for i in range(9)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())

        # Verify timeout detection worked correctly for each scenario
        assert len(results) == 9
        
        server_timeout_results = [r for r in results if r[0] % 3 == 0]
        connection_timeout_results = [r for r in results if r[0] % 3 == 1]
        non_timeout_results = [r for r in results if r[0] % 3 == 2]

        # Server timeout scenarios should retry and succeed
        for scenario_id, status, data, call_count, result_type in server_timeout_results:
            assert status == 200
            assert '"type": "server"' in data
            assert call_count == 2
            assert result_type == "success"

        # Connection timeout scenarios should retry and succeed
        for scenario_id, status, data, call_count, result_type in connection_timeout_results:
            assert status == 200
            assert '"type": "connection"' in data
            assert call_count == 2
            assert result_type == "success"

        # Non-timeout scenarios should not retry
        for scenario_id, status, data, call_count, result_type in non_timeout_results:
            assert status == 400
            assert "Invalid query syntax" in data
            assert call_count == 1
            assert result_type == "success"

    @patch("sfq.http_client.logger")
    def test_concurrent_logging_thread_safety(self, mock_logger, auth_manager):
        """Test that logging remains consistent during concurrent operations."""
        http_client = HTTPClient(auth_manager, user_agent="test-agent/1.0")
        
        def make_logged_request(request_id):
            """Make a request that generates log entries."""
            with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
                mock_internal.side_effect = [
                    (400, "Your query request was running for too long."),
                    (200, f'{{"request_id": {request_id}}}')
                ]

                status, data = http_client.send_authenticated_request_with_retry(
                    "GET", f"/services/data/v65.0/query?req={request_id}", max_retries=3
                )
                
                return (request_id, status, data)

        # Execute concurrent requests that generate logs
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(make_logged_request, i)
                for i in range(5)
            ]
            
            results = [future.result() for future in as_completed(futures)]

        # Verify all requests completed successfully
        assert len(results) == 5
        for request_id, status, data in results:
            assert status == 200
            assert f'"request_id": {request_id}' in data

        # Verify logging calls were made (exact count may vary due to concurrency)
        # but should have at least some trace and debug calls
        assert mock_logger.trace.call_count >= 5  # At least one per request
        assert mock_logger.debug.call_count >= 10  # At least retry + success per request