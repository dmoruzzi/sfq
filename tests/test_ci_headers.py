"""
Unit tests for CI-aware HTTP header attachment.

Tests CI environment detection, header generation, and PII opt-in functionality.
"""

import os
from unittest.mock import patch

import pytest

from sfq.ci_headers import CIHeaders


class TestCIHeaders:
    """Test cases for CIHeaders class."""

    def test_detect_ci_provider_github(self):
        """Test GitHub Actions detection."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REPOSITORY": "org/repo",
        }
        
        with patch.dict(os.environ, env, clear=True):
            provider = CIHeaders.detect_ci_provider()
            assert provider == "github"

    def test_detect_ci_provider_gitlab(self):
        """Test GitLab CI detection."""
        env = {
            "GITLAB_CI": "true",
            "CI_PIPELINE_ID": "789012",
        }
        
        with patch.dict(os.environ, env, clear=True):
            provider = CIHeaders.detect_ci_provider()
            assert provider == "gitlab"

    def test_detect_ci_provider_circleci(self):
        """Test CircleCI detection."""
        env = {
            "CIRCLECI": "true",
            "CIRCLE_WORKFLOW_ID": "abc123",
        }
        
        with patch.dict(os.environ, env, clear=True):
            provider = CIHeaders.detect_ci_provider()
            assert provider == "circleci"

    def test_detect_ci_provider_local(self):
        """Test local environment (no CI)."""
        with patch.dict(os.environ, {}, clear=True):
            provider = CIHeaders.detect_ci_provider()
            assert provider is None

    def test_detect_ci_provider_wrong_value(self):
        """Test detection with wrong value (should not detect)."""
        env = {
            "GITHUB_ACTIONS": "false",  # Wrong value
        }
        
        with patch.dict(os.environ, env, clear=True):
            provider = CIHeaders.detect_ci_provider()
            assert provider is None

    def test_is_ci_environment_true(self):
        """Test is_ci_environment returns True when in CI."""
        env = {
            "GITHUB_ACTIONS": "true",
        }
        
        with patch.dict(os.environ, env, clear=True):
            assert CIHeaders.is_ci_environment() is True

    def test_is_ci_environment_false(self):
        """Test is_ci_environment returns False when not in CI."""
        with patch.dict(os.environ, {}, clear=True):
            assert CIHeaders.is_ci_environment() is False

    def test_should_include_pii_default(self):
        """Test PII opt-in defaults to False."""
        with patch.dict(os.environ, {}, clear=True):
            assert CIHeaders._should_include_pii() is False

    def test_should_include_pii_true_variants(self):
        """Test PII opt-in with various true values."""
        true_values = ["true", "True", "TRUE", "1", "yes", "Yes", "YES", "y", "Y"]
        
        for value in true_values:
            with patch.dict(os.environ, {"SFQ_ATTACH_CI_PII": value}, clear=True):
                assert CIHeaders._should_include_pii() is True, f"Failed for value: {value}"

    def test_should_include_pii_false_variants(self):
        """Test PII opt-in with various false values."""
        false_values = ["false", "False", "FALSE", "0", "no", "No", "NO", "n", "N", "", "random"]
        
        for value in false_values:
            with patch.dict(os.environ, {"SFQ_ATTACH_CI_PII": value}, clear=True):
                assert CIHeaders._should_include_pii() is False, f"Failed for value: {value}"

    def test_get_header_name(self):
        """Test header name formatting."""
        assert CIHeaders._get_header_name("run_id") == "x-sfdc-addinfo-run_id"
        assert CIHeaders._get_header_name("ci_provider") == "x-sfdc-addinfo-ci_provider"
        assert CIHeaders._get_header_name("repository") == "x-sfdc-addinfo-repository"

    def test_get_pii_header_name(self):
        """Test PII header name formatting."""
        assert CIHeaders._get_pii_header_name("user_login") == "x-sfdc-addinfo-pii-user_login"
        assert CIHeaders._get_pii_header_name("actor") == "x-sfdc-addinfo-pii-actor"
        assert CIHeaders._get_pii_header_name("user_email") == "x-sfdc-addinfo-pii-user_email"

    def test_get_ci_headers_github_non_pii(self):
        """Test GitHub Actions non-PII headers."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_WORKFLOW": "Release",
            "GITHUB_REF": "refs/heads/main",
            "RUNNER_OS": "Linux",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            expected = {
                "x-sfdc-addinfo-ci_provider": "github",
                "x-sfdc-addinfo-run_id": "123456",
                "x-sfdc-addinfo-repository": "org/repo",
                "x-sfdc-addinfo-workflow": "Release",
                "x-sfdc-addinfo-ref": "refs/heads/main",
                "x-sfdc-addinfo-runner_os": "Linux",
            }
            
            assert headers == expected

    def test_get_ci_headers_github_with_pii(self):
        """Test GitHub Actions with PII opt-in."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_ACTOR": "octocat",
            "GITHUB_ACTOR_ID": "12345",
            "SFQ_ATTACH_CI_PII": "true",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            expected = {
                "x-sfdc-addinfo-ci_provider": "github",
                "x-sfdc-addinfo-run_id": "123456",
                "x-sfdc-addinfo-pii-actor": "octocat",
                "x-sfdc-addinfo-pii-actor_id": "12345",
            }
            
            assert headers == expected

    def test_get_ci_headers_github_missing_vars(self):
        """Test GitHub Actions with missing environment variables."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            # Missing other vars
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            # Should only include what's available
            expected = {
                "x-sfdc-addinfo-ci_provider": "github",
                "x-sfdc-addinfo-run_id": "123456",
            }
            
            assert headers == expected

    def test_get_ci_headers_gitlab_non_pii(self):
        """Test GitLab CI non-PII headers."""
        env = {
            "GITLAB_CI": "true",
            "CI_PIPELINE_ID": "789012",
            "CI_PROJECT_PATH": "org/project",
            "CI_JOB_NAME": "deploy",
            "CI_COMMIT_REF_NAME": "main",
            "CI_RUNNER_ID": "456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            expected = {
                "x-sfdc-addinfo-ci_provider": "gitlab",
                "x-sfdc-addinfo-pipeline_id": "789012",
                "x-sfdc-addinfo-project_path": "org/project",
                "x-sfdc-addinfo-job_name": "deploy",
                "x-sfdc-addinfo-commit_ref_name": "main",
                "x-sfdc-addinfo-runner_id": "456",
            }
            
            assert headers == expected

    def test_get_ci_headers_gitlab_with_pii(self):
        """Test GitLab CI with PII opt-in."""
        env = {
            "GITLAB_CI": "true",
            "CI_PIPELINE_ID": "789012",
            "GITLAB_USER_LOGIN": "jdoe",
            "GITLAB_USER_EMAIL": "jdoe@corp.com",
            "GITLAB_USER_ID": "48291",
            "SFQ_ATTACH_CI_PII": "true",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            expected = {
                "x-sfdc-addinfo-ci_provider": "gitlab",
                "x-sfdc-addinfo-pipeline_id": "789012",
                "x-sfdc-addinfo-pii-user_login": "jdoe",
                "x-sfdc-addinfo-pii-user_email": "jdoe@corp.com",
                "x-sfdc-addinfo-pii-user_id": "48291",
            }
            
            assert headers == expected

    def test_get_ci_headers_circleci_non_pii(self):
        """Test CircleCI non-PII headers."""
        env = {
            "CIRCLECI": "true",
            "CIRCLE_WORKFLOW_ID": "abc123",
            "CIRCLE_PROJECT_REPONAME": "myrepo",
            "CIRCLE_BRANCH": "develop",
            "CIRCLE_BUILD_NUM": "456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            expected = {
                "x-sfdc-addinfo-ci_provider": "circleci",
                "x-sfdc-addinfo-workflow_id": "abc123",
                "x-sfdc-addinfo-project_reponame": "myrepo",
                "x-sfdc-addinfo-branch": "develop",
                "x-sfdc-addinfo-build_num": "456",
            }
            
            assert headers == expected

    def test_get_ci_headers_circleci_with_pii(self):
        """Test CircleCI with PII opt-in."""
        env = {
            "CIRCLECI": "true",
            "CIRCLE_WORKFLOW_ID": "abc123",
            "CIRCLE_USERNAME": "jdoe",
            "SFQ_ATTACH_CI_PII": "true",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            expected = {
                "x-sfdc-addinfo-ci_provider": "circleci",
                "x-sfdc-addinfo-workflow_id": "abc123",
                "x-sfdc-addinfo-pii-username": "jdoe",
            }
            
            assert headers == expected

    def test_get_ci_headers_local(self):
        """Test local environment returns empty headers."""
        with patch.dict(os.environ, {}, clear=True):
            headers = CIHeaders.get_ci_headers()
            assert headers == {}

    def test_get_ci_headers_pii_opt_out(self):
        """Test PII is excluded when opt-out is set."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_ACTOR": "octocat",
            "SFQ_ATTACH_CI_PII": "false",  # Explicit opt-out
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            # Should not include PII
            assert "x-sfdc-addinfo-pii-actor" not in headers
            assert "x-sfdc-addinfo-run_id" in headers

    def test_get_ci_headers_case_insensitive_pii(self):
        """Test PII opt-in is case insensitive."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_ACTOR": "octocat",
            "SFQ_ATTACH_CI_PII": "TrUe",  # Mixed case
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            assert "x-sfdc-addinfo-pii-actor" in headers

    def test_get_ci_headers_empty_env_vars(self):
        """Test handling of empty environment variable values."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "",  # Empty value
            "GITHUB_REPOSITORY": "org/repo",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            
            # Empty values should be skipped
            assert "x-sfdc-addinfo-run_id" not in headers
            assert "x-sfdc-addinfo-repository" in headers

    def test_sfq_attach_ci_disabled(self):
        """Test that CI headers are not attached when SFQ_ATTACH_CI=false."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "SFQ_ATTACH_CI": "false",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            assert headers == {}

    def test_sfq_attach_ci_disabled_variants(self):
        """Test various ways to disable CI headers."""
        disabled_values = ["false", "False", "FALSE", "0", "no", "No", "NO", "n", "N"]
        
        for value in disabled_values:
            env = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_RUN_ID": "123456",
                "SFQ_ATTACH_CI": value,
            }
            
            with patch.dict(os.environ, env, clear=True):
                headers = CIHeaders.get_ci_headers()
                assert headers == {}, f"Failed for value: {value}"

    def test_sfq_attach_ci_enabled_variants(self):
        """Test various ways to enable CI headers."""
        enabled_values = ["true", "True", "TRUE", "1", "yes", "Yes", "YES", "y", "Y", ""]
        
        for value in enabled_values:
            env = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_RUN_ID": "123456",
                "SFQ_ATTACH_CI": value,
            }
            
            with patch.dict(os.environ, env, clear=True):
                headers = CIHeaders.get_ci_headers()
                assert "x-sfdc-addinfo-run_id" in headers, f"Failed for value: {value}"

    def test_sfq_attach_ci_default_enabled(self):
        """Test that CI headers are enabled by default (when SFQ_ATTACH_CI is not set)."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            assert "x-sfdc-addinfo-run_id" in headers

    def test_sfq_attach_ci_disabled_with_pii(self):
        """Test that SFQ_ATTACH_CI=false overrides PII setting."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_ACTOR": "octocat",
            "SFQ_ATTACH_CI": "false",
            "SFQ_ATTACH_CI_PII": "true",
        }
        
        with patch.dict(os.environ, env, clear=True):
            headers = CIHeaders.get_ci_headers()
            assert headers == {}