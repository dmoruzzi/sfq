"""
Integration tests for HTTPClient with CI-aware header attachment.

Tests that CI headers are properly integrated into HTTP requests.
"""

import os
from unittest.mock import Mock, patch

import pytest

from sfq.auth import AuthManager
from sfq.http_client import HTTPClient


class TestHTTPClientCIIntegration:
    """Integration tests for HTTPClient with CI headers."""

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
        auth_manager.get_token_request_headers.return_value = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        auth_manager.format_token_request_body.return_value = (
            "grant_type=refresh_token&client_id=test"
        )
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    def test_get_common_headers_in_github_ci(self, http_client):
        """Test that CI headers are added when running in GitHub Actions."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_WORKFLOW": "Release",
            "GITHUB_REF": "refs/heads/main",
            "RUNNER_OS": "Linux",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Verify standard headers
            assert headers["User-Agent"] == "test-agent/1.0"
            assert headers["Sforce-Call-Options"] == "client=test-client"
            assert headers["Authorization"] == "Bearer test_token_123"
            
            # Verify CI headers
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert headers["x-sfdc-addinfo-run_id"] == "123456"
            assert headers["x-sfdc-addinfo-repository"] == "org/repo"
            assert headers["x-sfdc-addinfo-workflow"] == "Release"
            assert headers["x-sfdc-addinfo-ref"] == "refs/heads/main"
            assert headers["x-sfdc-addinfo-runner_os"] == "Linux"

    def test_get_common_headers_in_gitlab_ci(self, http_client):
        """Test that CI headers are added when running in GitLab CI."""
        env = {
            "GITLAB_CI": "true",
            "CI_PIPELINE_ID": "789012",
            "CI_PROJECT_PATH": "org/project",
            "CI_JOB_NAME": "deploy",
            "CI_COMMIT_REF_NAME": "main",
            "CI_RUNNER_ID": "456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Verify CI headers
            assert headers["x-sfdc-addinfo-ci_provider"] == "gitlab"
            assert headers["x-sfdc-addinfo-pipeline_id"] == "789012"
            assert headers["x-sfdc-addinfo-project_path"] == "org/project"
            assert headers["x-sfdc-addinfo-job_name"] == "deploy"
            assert headers["x-sfdc-addinfo-commit_ref_name"] == "main"
            assert headers["x-sfdc-addinfo-runner_id"] == "456"

    def test_get_common_headers_in_circleci(self, http_client):
        """Test that CI headers are added when running in CircleCI."""
        env = {
            "CIRCLECI": "true",
            "CIRCLE_WORKFLOW_ID": "abc123",
            "CIRCLE_PROJECT_REPONAME": "myrepo",
            "CIRCLE_BRANCH": "develop",
            "CIRCLE_BUILD_NUM": "456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Verify CI headers
            assert headers["x-sfdc-addinfo-ci_provider"] == "circleci"
            assert headers["x-sfdc-addinfo-workflow_id"] == "abc123"
            assert headers["x-sfdc-addinfo-project_reponame"] == "myrepo"
            assert headers["x-sfdc-addinfo-branch"] == "develop"
            assert headers["x-sfdc-addinfo-build_num"] == "456"

    def test_get_common_headers_local(self, http_client):
        """Test that no CI headers are added when running locally."""
        with patch.dict(os.environ, {}, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Verify only standard headers
            expected = {
                "User-Agent": "test-agent/1.0",
                "Sforce-Call-Options": "client=test-client",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer test_token_123",
            }
            
            assert headers == expected

    def test_get_common_headers_with_pii_opt_in(self, http_client):
        """Test that PII headers are added when opted in."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_ACTOR": "octocat",
            "GITHUB_ACTOR_ID": "12345",
            "SFQ_ATTACH_CI_PII": "true",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Verify PII headers are included
            assert headers["x-sfdc-addinfo-pii-actor"] == "octocat"
            assert headers["x-sfdc-addinfo-pii-actor_id"] == "12345"
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert headers["x-sfdc-addinfo-run_id"] == "123456"

    def test_get_common_headers_with_pii_opt_out(self, http_client):
        """Test that PII headers are excluded when opted out."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_ACTOR": "octocat",
            "SFQ_ATTACH_CI_PII": "false",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Verify PII headers are excluded
            assert "x-sfdc-addinfo-pii-actor" not in headers
            assert "x-sfdc-addinfo-ci_provider" in headers
            assert headers["x-sfdc-addinfo-run_id"] == "123456"

    def test_get_common_headers_without_auth(self, http_client):
        """Test CI headers are added even without auth."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=False)
            
            # Should have CI headers but no auth
            assert "x-sfdc-addinfo-ci_provider" in headers
            assert "Authorization" not in headers

    def test_get_common_headers_recursive_call(self, http_client):
        """Test CI headers are added even for recursive calls."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(
                include_auth=True, 
                recursive_call=True
            )
            
            # Should have CI headers but no auth (recursive call)
            assert "x-sfdc-addinfo-ci_provider" in headers
            assert "Authorization" not in headers

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_send_authenticated_request_includes_ci_headers(self, mock_send_request, http_client):
        """Test that send_authenticated_request includes CI headers."""
        mock_send_request.return_value = (200, '{"result": "success"}')
        
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REPOSITORY": "org/repo",
        }
        
        with patch.dict(os.environ, env, clear=True):
            status, data = http_client.send_authenticated_request(
                "GET", "/test/endpoint"
            )
            
            # Verify the request was made
            assert status == 200
            assert data == '{"result": "success"}'
            
            # Get the headers that were passed to send_request
            call_args = mock_send_request.call_args
            headers = call_args[0][2]  # Third argument is headers
            
            # Verify CI headers are included
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert headers["x-sfdc-addinfo-run_id"] == "123456"
            assert headers["x-sfdc-addinfo-repository"] == "org/repo"
            
            # Verify standard headers
            assert headers["Authorization"] == "Bearer test_token_123"
            assert headers["User-Agent"] == "test-agent/1.0"

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_send_authenticated_request_with_additional_headers(self, mock_send_request, http_client):
        """Test that additional headers are merged with CI headers."""
        mock_send_request.return_value = (200, '{"result": "success"}')
        
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            status, data = http_client.send_authenticated_request(
                "GET", 
                "/test/endpoint",
                additional_headers={"Custom-Header": "custom-value"}
            )
            
            # Get the headers that were passed to send_request
            call_args = mock_send_request.call_args
            headers = call_args[0][2]
            
            # Verify all headers are present
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert headers["x-sfdc-addinfo-run_id"] == "123456"
            assert headers["Custom-Header"] == "custom-value"
            assert headers["Authorization"] == "Bearer test_token_123"

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_send_token_request_no_ci_headers(self, mock_send_request, http_client):
        """Test that token requests don't include CI headers (they use get_common_headers with recursive_call=True)."""
        mock_send_request.return_value = (200, '{"access_token": "new_token"}')
        
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            payload = {"grant_type": "refresh_token", "client_id": "test"}
            status, data = http_client.send_token_request(payload, "/oauth2/token")
            
            # Get the headers that were passed to send_request
            call_args = mock_send_request.call_args
            headers = call_args[0][2]
            
            # Token requests should have CI headers but no auth
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert "Authorization" not in headers

    def test_ci_headers_in_request_flow(self, http_client):
        """Test end-to-end flow with CI headers."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_WORKFLOW": "Test",
            "SFQ_ATTACH_CI_PII": "true",
            "GITHUB_ACTOR": "testuser",
        }
        
        with patch.dict(os.environ, env, clear=True):
            # Get headers as they would be in a real request
            headers = http_client.get_common_headers(include_auth=True)
            
            # Verify all expected headers are present
            expected_keys = {
                "User-Agent",
                "Sforce-Call-Options",
                "Accept",
                "Content-Type",
                "Authorization",
                "x-sfdc-addinfo-ci_provider",
                "x-sfdc-addinfo-run_id",
                "x-sfdc-addinfo-repository",
                "x-sfdc-addinfo-workflow",
                "x-sfdc-addinfo-pii-actor",
            }
            
            assert set(headers.keys()) == expected_keys
            
            # Verify specific values
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert headers["x-sfdc-addinfo-run_id"] == "123456"
            assert headers["x-sfdc-addinfo-repository"] == "org/repo"
            assert headers["x-sfdc-addinfo-workflow"] == "Test"
            assert headers["x-sfdc-addinfo-pii-actor"] == "testuser"

    def test_multiple_ci_providers_not_detected(self, http_client):
        """Test that only one CI provider is detected even if multiple env vars exist."""
        # This shouldn't happen in practice, but test the behavior
        env = {
            "GITHUB_ACTIONS": "true",
            "GITLAB_CI": "true",  # Should not be detected
            "GITHUB_RUN_ID": "123456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Should detect GitHub (first in the list)
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert headers["x-sfdc-addinfo-run_id"] == "123456"
            # Should not have GitLab headers
            assert "x-sfdc-addinfo-pipeline_id" not in headers

    def test_sfq_attach_ci_false_disables_headers(self, http_client):
        """Test that SFQ_ATTACH_CI=false prevents CI headers from being added."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REPOSITORY": "org/repo",
            "SFQ_ATTACH_CI": "false",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Should have standard headers but no CI headers
            assert "User-Agent" in headers
            assert "Authorization" in headers
            assert "x-sfdc-addinfo-ci_provider" not in headers
            assert "x-sfdc-addinfo-run_id" not in headers

    def test_sfq_attach_ci_false_with_pii(self, http_client):
        """Test that SFQ_ATTACH_CI=false overrides PII setting."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_ACTOR": "octocat",
            "SFQ_ATTACH_CI": "false",
            "SFQ_ATTACH_CI_PII": "true",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Should have standard headers but no CI headers at all
            assert "User-Agent" in headers
            assert "Authorization" in headers
            assert "x-sfdc-addinfo-ci_provider" not in headers
            assert "x-sfdc-addinfo-pii-actor" not in headers

    def test_sfq_attach_ci_default_enabled(self, http_client):
        """Test that CI headers are enabled by default when SFQ_ATTACH_CI is not set."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REPOSITORY": "org/repo",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = http_client.get_common_headers(include_auth=True)
            
            # Should have CI headers by default
            assert headers["x-sfdc-addinfo-ci_provider"] == "github"
            assert headers["x-sfdc-addinfo-run_id"] == "123456"
            assert headers["x-sfdc-addinfo-repository"] == "org/repo"

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_send_authenticated_request_sfq_attach_ci_false(self, mock_send_request, http_client):
        """Test that send_authenticated_request respects SFQ_ATTACH_CI=false."""
        mock_send_request.return_value = (200, '{"result": "success"}')
        
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "SFQ_ATTACH_CI": "false",
        }
        
        with patch.dict(os.environ, env, clear=True):
            status, data = http_client.send_authenticated_request(
                "GET", "/test/endpoint"
            )
            
            # Get the headers that were passed to send_request
            call_args = mock_send_request.call_args
            headers = call_args[0][2]
            
            # Should have standard headers but no CI headers
            assert headers["Authorization"] == "Bearer test_token_123"
            assert headers["User-Agent"] == "test-agent/1.0"
            assert "x-sfdc-addinfo-ci_provider" not in headers