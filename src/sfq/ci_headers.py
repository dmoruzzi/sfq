"""
CI-aware HTTP header attachment module.

This module provides automatic detection of CI environments and attachment
of traceable CI metadata to outbound HTTP requests.
"""

import os
from typing import Dict, Optional, TypedDict

from .utils import get_logger


class CIProviderConfig(TypedDict):
    detect_var: str
    non_pii_vars: Dict[str, str]
    pii_vars: Dict[str, str]


class CIHeaders:
    """
    Handles CI environment detection and header generation.

    Supports GitHub Actions, GitLab CI, and CircleCI with automatic
    detection via environment variables. PII attachment requires explicit
    opt-in via SFQ_ATTACH_CI_PII environment variable.
    """

    CI_PROVIDERS: Dict[str, CIProviderConfig] = {
        "github": {
            "detect_var": "GITHUB_ACTIONS",
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

        Detection is presence-based to support partial / reusable CI contexts.
        """
        for provider, config in CIHeaders.CI_PROVIDERS.items():
            detect_value = os.environ.get(config["detect_var"])
            if detect_value and detect_value.lower() in {"true", "1", "yes", "y"}:
                return provider
        return None

    @staticmethod
    def _should_include_pii() -> bool:
        """
        Check if PII headers should be included.

        Controlled by SFQ_ATTACH_CI_PII environment variable.
        Default is False (explicit opt-in required).
        """
        return os.environ.get("SFQ_ATTACH_CI_PII", "").lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    @staticmethod
    def _get_header_name(field: str) -> str:
        return f"x-sfdc-addinfo-{field}"

    @staticmethod
    def _get_pii_header_name(field: str) -> str:
        return f"x-sfdc-addinfo-pii-{field}"

    @staticmethod
    def _normalize_insert_value(value: str) -> str:
        """
        Normalizes values to only allow alphanumeric characters, '-', and '_'.
        
        Performs common character replacements first, then filters to only allow
        alphanumeric characters, '-', and '_'.
        
        Args:
            value: The original value from environment variable
            
        Returns:
            str: The sanitized value with only allowed characters.
        """
        # Common replacements
        value = value.replace('@', '_at_')
        value = value.replace('/', '_')
        value = value.replace('\\', '_')
        value = value.replace(' ', '_')
        value = value.replace('.', '_')
        value = value.replace("[", "")
        value = value.replace("]", "")
        
        # Only allow alphanumeric, '-', and '_' characters
        # This ensures the final result only contains allowed characters
        sanitized: list[str] = []
        for char in value:
            if char.isalnum() or char in ('-', '_'):
                sanitized.append(char)
        return ''.join(sanitized)

    @staticmethod
    def get_ci_headers() -> Dict[str, str]:
        """
        Generate CI metadata headers for the current environment.

        Returns:
            Dict[str, str]: Headers to attach, or empty dict if not applicable.
        """
        if os.environ.get("SFQ_ATTACH_CI", "").lower() not in {
            "",
            "true",
            "1",
            "yes",
            "y",
        }:
            return {}

        provider = CIHeaders.detect_ci_provider()
        if not provider:
            return {}

        config = CIHeaders.CI_PROVIDERS[provider]
        headers: Dict[str, str] = {}

        # Always include the CI provider header
        headers[CIHeaders._get_header_name("ci_provider")] = provider

        # Add non-PII headers (no sanitization)
        for env_var, field_name in config["non_pii_vars"].items():
            value = os.environ.get(env_var)
            if value:
                headers[CIHeaders._get_header_name(field_name)] = value

        # Add PII headers if opted in (with sanitization)
        if CIHeaders._should_include_pii():
            for env_var, field_name in config.get("pii_vars", {}).items():
                value = os.environ.get(env_var)
                if value:
                    cleaned_value = CIHeaders._normalize_insert_value(value)
                    headers[CIHeaders._get_pii_header_name(field_name)] = cleaned_value

        return headers

    @staticmethod
    def is_ci_environment() -> bool:
        """
        Check if currently running in a CI environment.
        """
        return CIHeaders.detect_ci_provider() is not None

    @staticmethod
    def get_addinfo_headers() -> Dict[str, str]:
        """
        Generate custom addinfo headers from SFQ_HEADERS environment variable.

        The SFQ_HEADERS environment variable should be in the format:
        "key1:value1|key2:value2"

        This will create headers like:
        x-sfdc-addinfo-key1 = value1
        x-sfdc-addinfo-key2 = value2

        Returns:
            Dict[str, str]: Headers to attach, or empty dict if not applicable.
        """
        # Respect SFQ_ATTACH_CI setting - if explicitly set to false, don't attach any headers
        if os.environ.get("SFQ_ATTACH_CI", "").lower() in {
            "false",
            "0",
            "no",
            "n",
        }:
            return {}
        
        headers: Dict[str, str] = {}
         
        # Get the environment variable
        sfq_headers_env = os.environ.get("SFQ_HEADERS", "")
        if not sfq_headers_env:
            return headers
         
        # Parse the key:value pairs separated by |
        try:
            header_pairs = sfq_headers_env.split("|")
            for pair in header_pairs:
                if ":" in pair:
                    key, value = pair.split(":", 1)  # Split on first : only
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        header_name = f"x-sfdc-addinfo-{key}"
                        headers[header_name] = value
        except Exception as e:
            # If parsing fails, log and return empty headers
            logger = get_logger(__name__)
            logger.warning("Failed to parse SFQ_HEADERS environment variable: %s", e)
         
        return headers
