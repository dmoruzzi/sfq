"""
CI-aware HTTP header attachment module.

This module provides automatic detection of CI environments and attachment
of traceable CI metadata to outbound HTTP requests.
"""

import os
from typing import Dict, Optional


class CIHeaders:
    """
    Handles CI environment detection and header generation.
    
    Supports GitHub Actions, GitLab CI, and CircleCI with automatic
    detection via environment variables. PII attachment requires explicit
    opt-in via SFQ_ATTACH_CI_PII environment variable.
    """
    
    # Environment variable mapping for CI detection
    CI_PROVIDERS = {
        "github": {
            "detect_var": "GITHUB_ACTIONS",
            "detect_value": "true",
            "non_pii_vars": {
                "GITHUB_RUN_ID": "run_id",
                "GITHUB_REPOSITORY": "repository",
                "GITHUB_WORKFLOW": "workflow",
                "GITHUB_REF": "ref",
                "RUNNER_OS": "runner_os",
            },
            "pii_vars": {
                "GITHUB_ACTOR": "actor",
                "GITHUB_ACTOR_ID": "actor_id",
                "GITHUB_TRIGGERING_ACTOR": "triggering_actor",
            },
        },
        "gitlab": {
            "detect_var": "GITLAB_CI",
            "detect_value": "true",
            "non_pii_vars": {
                "CI_PIPELINE_ID": "pipeline_id",
                "CI_PROJECT_PATH": "project_path",
                "CI_JOB_NAME": "job_name",
                "CI_COMMIT_REF_NAME": "commit_ref_name",
                "CI_RUNNER_ID": "runner_id",
            },
            "pii_vars": {
                "GITLAB_USER_LOGIN": "user_login",
                "GITLAB_USER_NAME": "user_name",
                "GITLAB_USER_EMAIL": "user_email",
                "GITLAB_USER_ID": "user_id",
            },
        },
        "circleci": {
            "detect_var": "CIRCLECI",
            "detect_value": "true",
            "non_pii_vars": {
                "CIRCLE_WORKFLOW_ID": "workflow_id",
                "CIRCLE_PROJECT_REPONAME": "project_reponame",
                "CIRCLE_BRANCH": "branch",
                "CIRCLE_BUILD_NUM": "build_num",
            },
            "pii_vars": {
                "CIRCLE_USERNAME": "username",
            },
        },
    }
    
    @staticmethod
    def detect_ci_provider() -> Optional[str]:
        """
        Detect which CI provider is running, if any.
        
        Returns:
            str: CI provider name ('github', 'gitlab', 'circleci') or None
        """
        for provider, config in CIHeaders.CI_PROVIDERS.items():
            detect_var = config["detect_var"]
            detect_value = config["detect_value"]
            
            if os.environ.get(detect_var) == detect_value:
                return provider
        
        return None
    
    @staticmethod
    def _should_include_pii() -> bool:
        """
        Check if PII headers should be included.
        
        Controlled by SFQ_ATTACH_CI_PII environment variable.
        Default is False (PII excluded).
        
        Returns:
            bool: True if PII should be included, False otherwise
        """
        # Explicit opt-in required
        pii_env = os.environ.get("SFQ_ATTACH_CI_PII", "false").lower()
        return pii_env in ("true", "1", "yes", "y")
    
    @staticmethod
    def _get_header_name(field: str) -> str:
        """
        Convert field name to header name format.
        
        Args:
            field: Field name (e.g., 'run_id')
        
        Returns:
            str: Header name (e.g., 'x-sfdc-addinfo-run_id')
        """
        return f"x-sfdc-addinfo-{field}"
    
    @staticmethod
    def _get_pii_header_name(field: str) -> str:
        """
        Convert PII field name to header name format.
        
        Args:
            field: PII field name (e.g., 'user_login')
        
        Returns:
            str: PII header name (e.g., 'x-sfdc-addinfo-pii-user_login')
        """
        return f"x-sfdc-addinfo-pii-{field}"
    
    @staticmethod
    def get_ci_headers() -> Dict[str, str]:
        """
        Generate CI metadata headers for the current environment.

        Returns:
            Dict[str, str]: Dictionary of headers to attach, empty if not in CI or disabled
        """
        # Check if CI headers are globally disabled
        attach_ci_env = os.environ.get("SFQ_ATTACH_CI", "true").lower()
        if attach_ci_env not in ("true", "1", "yes", "y", ""):
            return {}

        provider = CIHeaders.detect_ci_provider()

        if not provider:
            # Not in CI environment - return empty headers
            return {}

        headers = {}
        config = CIHeaders.CI_PROVIDERS[provider]
        include_pii = CIHeaders._should_include_pii()

        # Add non-PII headers
        for env_var, field_name in config["non_pii_vars"].items():
            value = os.environ.get(env_var)
            if value:
                header_name = CIHeaders._get_header_name(field_name)
                headers[header_name] = value

        # Add provider header
        headers[CIHeaders._get_header_name("ci_provider")] = provider

        # Add PII headers if opted in
        if include_pii and "pii_vars" in config:
            for env_var, field_name in config["pii_vars"].items():
                value = os.environ.get(env_var)
                if value:
                    header_name = CIHeaders._get_pii_header_name(field_name)
                    headers[header_name] = value

        return headers
    
    @staticmethod
    def is_ci_environment() -> bool:
        """
        Check if currently running in a CI environment.
        
        Returns:
            bool: True if in CI, False otherwise
        """
        return CIHeaders.detect_ci_provider() is not None