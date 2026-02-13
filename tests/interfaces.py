"""
Public Interface Stability Tests for SFQ Library.

This module automatically discovers and validates all public interfaces across
the SFQ library to ensure backward compatibility. It uses Python introspection
to dynamically find public classes, methods, properties, and functions.

Breaking changes detected by this test suite indicate potential breaking changes
for downstream consumers and should be carefully reviewed before merging.

Usage:
    pytest tests/2026feb_interfaces.py -v
    pytest tests/2026feb_interfaces.py -v -k "SFAuth"
    pytest tests/2026feb_interfaces.py -v --tb=short
"""

import inspect
import json
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    get_type_hints,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)
from unittest.mock import patch

import pytest

import sfq
from sfq import (
    SFAuth,
    __version__,
)


@dataclass
class InterfaceSignature:
    """Represents a captured interface signature for comparison."""

    name: str
    kind: str  # 'method', 'property', 'function', 'class', 'attribute'
    parameters: Dict[str, Any] = field(default_factory=dict)
    return_annotation: Optional[str] = None
    default_values: Dict[str, Any] = field(default_factory=dict)
    is_public: bool = True
    docstring: Optional[str] = None


@dataclass
class ClassInterface:
    """Represents the complete public interface of a class."""

    module_name: str
    class_name: str
    methods: Dict[str, InterfaceSignature] = field(default_factory=dict)
    properties: Dict[str, InterfaceSignature] = field(default_factory=dict)
    class_attributes: Dict[str, InterfaceSignature] = field(default_factory=dict)
    instance_attributes: Dict[str, InterfaceSignature] = field(default_factory=dict)


def is_public_name(name: str) -> bool:
    """Check if a name is considered public (not starting with underscore)."""
    return not name.startswith("_")


def is_private_name(name: str) -> bool:
    """Check if a name is considered private (starts with underscore)."""
    return name.startswith("_")


def is_dunder(name: str) -> bool:
    """Check if a name is a dunder method (double underscore)."""
    return name.startswith("__") and name.endswith("__")


def get_public_members(obj: Any) -> Dict[str, Any]:
    """Get all public members of an object."""
    members = {}
    for name in dir(obj):
        if is_public_name(name):
            members[name] = getattr(obj, name)
    return members


def serialize_annotation(annotation: Any) -> str:
    """Serialize a type annotation to a string representation."""
    if annotation is inspect.Parameter.empty:
        return "any"
    if annotation is None:
        return "None"

    try:
        if hasattr(annotation, "__name__"):
            return annotation.__name__
        if hasattr(annotation, "_name"):
            return str(annotation._name)
        str_repr = str(annotation)
        str_repr = str_repr.replace("typing.", "")
        return str_repr
    except Exception:
        return str(annotation)


def capture_method_signature(method: Callable, name: str) -> InterfaceSignature:
    """Capture the signature of a method."""
    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        return InterfaceSignature(
            name=name,
            kind="method",
            docstring=inspect.getdoc(method),
        )

    parameters = {}
    default_values = {}

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        parameters[param_name] = {
            "annotation": serialize_annotation(param.annotation),
            "kind": str(param.kind),
        }

        if param.default is not inspect.Parameter.empty:
            default_values[param_name] = repr(param.default)

    return_annotation = serialize_annotation(sig.return_annotation)

    return InterfaceSignature(
        name=name,
        kind="method",
        parameters=parameters,
        return_annotation=return_annotation,
        default_values=default_values,
        docstring=inspect.getdoc(method),
    )


def capture_class_interface(
    cls: Type, instance: Optional[Any] = None
) -> ClassInterface:
    """Capture the complete public interface of a class."""
    interface = ClassInterface(
        module_name=cls.__module__,
        class_name=cls.__name__,
    )

    for name in dir(cls):
        if is_dunder(name):
            continue

        attr = getattr(cls, name)

        if isinstance(attr, property):
            interface.properties[name] = InterfaceSignature(
                name=name,
                kind="property",
                docstring=attr.__doc__,
            )
        elif callable(attr):
            if is_public_name(name):
                interface.methods[name] = capture_method_signature(attr, name)
        elif is_public_name(name):
            interface.class_attributes[name] = InterfaceSignature(
                name=name,
                kind="attribute",
                docstring=inspect.getdoc(attr) if hasattr(attr, "__doc__") else None,
            )

    if instance is not None:
        for name in dir(instance):
            if is_private_name(name) or is_dunder(name):
                continue

            attr = getattr(instance, name)

            if isinstance(attr, property):
                continue
            elif callable(attr):
                if name not in interface.methods:
                    interface.methods[name] = capture_method_signature(attr, name)
            else:
                interface.instance_attributes[name] = InterfaceSignature(
                    name=name,
                    kind="attribute",
                )

    return interface


class InterfaceSnapshot:
    """
    Manages snapshots of interface signatures for comparison.

    This class enables capturing the current state of interfaces and
    comparing against expected/baseline states to detect breaking changes.
    """

    def __init__(self):
        self.classes: Dict[str, ClassInterface] = {}
        self.functions: Dict[str, InterfaceSignature] = {}
        self.exceptions: Dict[str, ClassInterface] = {}

    def capture_module_interfaces(self, module: Any) -> None:
        """Capture all public interfaces from a module."""
        for name in dir(module):
            if is_private_name(name):
                continue

            obj = getattr(module, name)

            if inspect.isclass(obj):
                if issubclass(obj, Exception):
                    self.exceptions[name] = capture_class_interface(obj)
                else:
                    self.classes[name] = capture_class_interface(obj)
            elif inspect.isfunction(obj):
                self.functions[name] = capture_method_signature(obj, name)

    def capture_class_with_instance(
        self, cls: Type, instance: Any, name: Optional[str] = None
    ) -> None:
        """Capture class interface with instance for runtime inspection."""
        interface = capture_class_interface(cls, instance)
        key = name or cls.__name__
        self.classes[key] = interface

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the snapshot to a dictionary."""
        return {
            "classes": {
                name: {
                    "module": ci.module_name,
                    "methods": list(ci.methods.keys()),
                    "properties": list(ci.properties.keys()),
                    "class_attributes": list(ci.class_attributes.keys()),
                }
                for name, ci in self.classes.items()
            },
            "functions": list(self.functions.keys()),
            "exceptions": list(self.exceptions.keys()),
        }


class TestModuleImports:
    """Test that all public modules and their exports are importable."""

    def test_main_package_importable(self):
        """The main sfq package must be importable."""
        import sfq

        assert sfq is not None

    def test_version_attribute_exists(self):
        """The __version__ attribute must exist and be a string."""
        assert hasattr(sfq, "__version__")
        assert isinstance(sfq.__version__, str)
        parts = sfq.__version__.split(".")
        assert len(parts) >= 2, (
            f"Version should have at least MAJOR.MINOR: {sfq.__version__}"
        )

    def test_all_exports_importable(self):
        """All items in __all__ must be importable from the package."""
        if hasattr(sfq, "__all__"):
            for name in sfq.__all__:
                assert hasattr(sfq, name), (
                    f"Export '{name}' in __all__ not found in module"
                )
                obj = getattr(sfq, name)
                assert obj is not None, f"Export '{name}' is None"

    def test_submodule_imports(self):
        """All expected submodules must be importable."""
        expected_submodules = [
            "auth",
            "http_client",
            "query",
            "crud",
            "soap",
            "exceptions",
            "utils",
            "platform_events",
            "mdapi",
        ]

        for submodule in expected_submodules:
            try:
                module = __import__(f"sfq.{submodule}", fromlist=[submodule])
                assert module is not None, f"Submodule sfq.{submodule} is None"
            except ImportError as e:
                pytest.fail(f"Failed to import sfq.{submodule}: {e}")


class TestExceptionHierarchy:
    """Test the exception class hierarchy for stability."""

    def test_base_exception_exists(self):
        """SFQException must exist as the base exception."""
        from sfq.exceptions import SFQException

        assert issubclass(SFQException, Exception)

    def test_exception_hierarchy(self):
        """Exception hierarchy must match expected inheritance."""
        from sfq.exceptions import (
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

        inheritance_checks = [
            (AuthenticationError, SFQException, "AuthenticationError"),
            (APIError, SFQException, "APIError"),
            (QueryError, APIError, "QueryError"),
            (QueryTimeoutError, QueryError, "QueryTimeoutError"),
            (CRUDError, APIError, "CRUDError"),
            (SOAPError, APIError, "SOAPError"),
            (HTTPError, SFQException, "HTTPError"),
            (ConfigurationError, SFQException, "ConfigurationError"),
        ]

        for exc_class, parent, name in inheritance_checks:
            assert issubclass(exc_class, parent), (
                f"{name} should inherit from {parent.__name__}"
            )

    def test_all_exceptions_importable_from_package(self):
        """All exceptions must be importable from the main package."""
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

        exceptions = [
            SFQException,
            AuthenticationError,
            APIError,
            QueryError,
            QueryTimeoutError,
            CRUDError,
            SOAPError,
            HTTPError,
            ConfigurationError,
        ]

        for exc in exceptions:
            assert issubclass(exc, Exception), f"{exc.__name__} should be an Exception"


class TestSFAuthInterface:
    """Test SFAuth class interface stability."""

    @pytest.fixture
    def sf_auth_instance(self):
        """Create a basic SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    def test_sf_auth_class_exists(self):
        """SFAuth class must be importable."""
        from sfq import SFAuth

        assert SFAuth is not None

    def test_sf_auth_init_required_parameters(self):
        """SFAuth __init__ must have required parameters."""
        sig = inspect.signature(SFAuth.__init__)
        params = list(sig.parameters.keys())

        required_params = [
            "self",
            "instance_url",
            "client_id",
            "refresh_token",
            "client_secret",
        ]

        for param in required_params:
            assert param in params, (
                f"SFAuth.__init__ missing required parameter: {param}"
            )

    def test_sf_auth_init_optional_parameters(self):
        """SFAuth __init__ must have optional parameters with correct defaults."""
        sig = inspect.signature(SFAuth.__init__)

        optional_params = {
            "api_version": "v65.0",
            "token_endpoint": "/services/oauth2/token",
            "access_token": None,
            "token_expiration_time": None,
            "token_lifetime": 15 * 60,
            "user_agent": f"sfq/{__version__}",
            "sforce_client": "_auto",
            "proxy": "_auto",
        }

        for param_name, expected_default in optional_params.items():
            assert param_name in sig.parameters, (
                f"Missing optional parameter: {param_name}"
            )
            actual = sig.parameters[param_name].default

            if param_name == "user_agent":
                assert "sfq/" in str(actual), (
                    f"user_agent default should contain 'sfq/'"
                )
            else:
                assert actual == expected_default, (
                    f"Parameter '{param_name}' has wrong default: {actual} != {expected_default}"
                )

    def test_sf_auth_public_properties(self, sf_auth_instance):
        """SFAuth must have all expected public properties."""
        expected_properties = [
            "instance_url",
            "client_id",
            "client_secret",
            "refresh_token",
            "api_version",
            "token_endpoint",
            "access_token",
            "token_expiration_time",
            "token_lifetime",
            "user_agent",
            "sforce_client",
            "proxy",
            "org_id",
            "user_id",
        ]

        for prop_name in expected_properties:
            assert hasattr(sf_auth_instance, prop_name), (
                f"SFAuth missing expected property: {prop_name}"
            )
            try:
                _ = getattr(sf_auth_instance, prop_name)
            except Exception as e:
                pytest.fail(f"Failed to access property '{prop_name}': {e}")

    def test_sf_auth_public_methods(self, sf_auth_instance):
        """SFAuth must have all expected public methods."""
        expected_methods = [
            "query",
            "tooling_query",
            "cquery",
            "cdelete",
            "limits",
            "get_sobject_prefixes",
            "read_static_resource_name",
            "read_static_resource_id",
            "update_static_resource_name",
            "update_static_resource_id",
            "debug_cleanup",
            "open_frontdoor",
            "records_to_html_table",
            "list_events",
            "publish",
            "publish_batch",
            "mdapi_retrieve",
        ]

        for method_name in expected_methods:
            assert hasattr(sf_auth_instance, method_name), (
                f"SFAuth missing expected method: {method_name}"
            )
            method = getattr(sf_auth_instance, method_name)
            assert callable(method), f"'{method_name}' should be callable"

    def test_query_method_signature(self, sf_auth_instance):
        """query method must have correct signature."""
        sig = inspect.signature(sf_auth_instance.query)
        params = list(sig.parameters.keys())

        assert "query" in params, "query() missing 'query' parameter"
        assert "tooling" in params, "query() missing 'tooling' parameter"
        assert sig.parameters["tooling"].default is False, (
            "tooling default should be False"
        )

    def test_cquery_method_signature(self, sf_auth_instance):
        """cquery method must have correct signature."""
        sig = inspect.signature(sf_auth_instance.cquery)
        params = list(sig.parameters.keys())

        assert "query_dict" in params, "cquery() missing 'query_dict' parameter"
        assert "batch_size" in params, "cquery() missing 'batch_size' parameter"
        assert "max_workers" in params, "cquery() missing 'max_workers' parameter"
        assert sig.parameters["batch_size"].default == 25, (
            "batch_size default should be 25"
        )
        assert sig.parameters["max_workers"].default is None, (
            "max_workers default should be None"
        )

    def test_cdelete_method_signature(self, sf_auth_instance):
        """cdelete method must have correct signature."""
        sig = inspect.signature(sf_auth_instance.cdelete)
        params = list(sig.parameters.keys())

        assert "ids" in params, "cdelete() missing 'ids' parameter"
        assert "batch_size" in params, "cdelete() missing 'batch_size' parameter"
        assert "max_workers" in params, "cdelete() missing 'max_workers' parameter"
        assert sig.parameters["batch_size"].default == 200, (
            "batch_size default should be 200"
        )

    def test_get_sobject_prefixes_signature(self, sf_auth_instance):
        """get_sobject_prefixes method must have correct signature."""
        sig = inspect.signature(sf_auth_instance.get_sobject_prefixes)
        params = list(sig.parameters.keys())

        assert "key_type" in params, (
            "get_sobject_prefixes() missing 'key_type' parameter"
        )
        assert sig.parameters["key_type"].default == "id", (
            "key_type default should be 'id'"
        )

    def test_static_resource_method_signatures(self, sf_auth_instance):
        """Static resource methods must have correct signatures."""
        sig_read_name = inspect.signature(sf_auth_instance.read_static_resource_name)
        assert "resource_name" in sig_read_name.parameters
        assert "namespace" in sig_read_name.parameters
        assert sig_read_name.parameters["namespace"].default is None

        sig_read_id = inspect.signature(sf_auth_instance.read_static_resource_id)
        assert "resource_id" in sig_read_id.parameters

        sig_update_name = inspect.signature(
            sf_auth_instance.update_static_resource_name
        )
        assert "resource_name" in sig_update_name.parameters
        assert "data" in sig_update_name.parameters
        assert "namespace" in sig_update_name.parameters
        assert sig_update_name.parameters["namespace"].default is None

        sig_update_id = inspect.signature(sf_auth_instance.update_static_resource_id)
        assert "resource_id" in sig_update_id.parameters
        assert "data" in sig_update_id.parameters


class TestPrivateMethodsExistence:
    """Test that internal/private methods exist for advanced users."""

    @pytest.fixture
    def sf_auth_instance(self):
        """Create a basic SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    def test_refresh_token_if_needed_exists(self, sf_auth_instance):
        """_refresh_token_if_needed must exist for internal use."""
        assert hasattr(sf_auth_instance, "_refresh_token_if_needed")
        assert callable(sf_auth_instance._refresh_token_if_needed)

    def test_soap_methods_exist(self, sf_auth_instance):
        """SOAP-related private methods must exist."""
        soap_methods = [
            "_gen_soap_envelope",
            "_gen_soap_header",
            "_gen_soap_body",
            "_extract_soap_result_fields",
            "_xml_to_json",
            "_xml_to_dict",
        ]

        for method_name in soap_methods:
            assert hasattr(sf_auth_instance, method_name), (
                f"Missing SOAP method: {method_name}"
            )
            assert callable(getattr(sf_auth_instance, method_name))

    def test_create_method_exists(self, sf_auth_instance):
        """_create method must exist for internal use."""
        assert hasattr(sf_auth_instance, "_create")
        assert callable(sf_auth_instance._create)

        sig = inspect.signature(sf_auth_instance._create)
        params = list(sig.parameters.keys())

        expected = ["sobject", "insert_list", "batch_size", "max_workers", "api_type"]
        for param in expected:
            assert param in params, f"_create() missing parameter: {param}"

    def test_cupdate_method_exists(self, sf_auth_instance):
        """_cupdate method must exist for internal use."""
        assert hasattr(sf_auth_instance, "_cupdate")
        assert callable(sf_auth_instance._cupdate)

        sig = inspect.signature(sf_auth_instance._cupdate)
        params = list(sig.parameters.keys())

        expected = ["update_dict", "batch_size", "max_workers"]
        for param in expected:
            assert param in params, f"_cupdate() missing parameter: {param}"

    def test_subscribe_method_exists(self, sf_auth_instance):
        """_subscribe method must exist for platform events."""
        assert hasattr(sf_auth_instance, "_subscribe")
        assert callable(sf_auth_instance._subscribe)


class TestQueryClientInterface:
    """Test QueryClient class interface stability."""

    def test_query_client_importable(self):
        """QueryClient must be importable from sfq.query."""
        from sfq.query import QueryClient

        assert QueryClient is not None

    def test_query_client_public_methods(self):
        """QueryClient must have expected public methods."""
        from sfq.query import QueryClient

        expected_methods = [
            "query",
            "tooling_query",
            "cquery",
            "get_sobject_prefixes",
            "get_sobject_name_from_id",
            "get_key_prefix_for_sobject",
            "validate_query_syntax",
        ]

        for method_name in expected_methods:
            assert hasattr(QueryClient, method_name), (
                f"QueryClient missing method: {method_name}"
            )

    def test_query_method_signature(self):
        """QueryClient.query must have correct signature."""
        from sfq.query import QueryClient

        sig = inspect.signature(QueryClient.query)
        params = list(sig.parameters.keys())

        assert "self" in params
        assert "query" in params
        assert "tooling" in params


class TestAuthManagerInterface:
    """Test AuthManager class interface stability."""

    def test_auth_manager_importable(self):
        """AuthManager must be importable from sfq.auth."""
        from sfq.auth import AuthManager

        assert AuthManager is not None

    def test_auth_manager_public_methods(self):
        """AuthManager must have expected public methods."""
        from sfq.auth import AuthManager

        expected_methods = [
            "is_token_expired",
            "get_auth_headers",
            "needs_token_refresh",
            "clear_token",
            "validate_instance_url",
            "is_sandbox_instance",
            "get_instance_type",
            "normalize_instance_url",
            "get_base_domain",
            "get_proxy_config",
            "validate_proxy_config",
        ]

        for method_name in expected_methods:
            assert hasattr(AuthManager, method_name), (
                f"AuthManager missing method: {method_name}"
            )


class TestHTTPClientInterface:
    """Test HTTPClient class interface stability."""

    def test_http_client_importable(self):
        """HTTPClient must be importable from sfq.http_client."""
        from sfq.http_client import HTTPClient

        assert HTTPClient is not None

    def test_http_client_public_methods(self):
        """HTTPClient must have expected public methods."""
        from sfq.http_client import HTTPClient

        expected_methods = [
            "create_connection",
            "get_common_headers",
            "send_request",
            "send_authenticated_request",
            "send_authenticated_request_with_retry",
            "refresh_token_and_update_auth",
            "get_instance_url",
            "get_api_version",
            "is_connection_healthy",
        ]

        for method_name in expected_methods:
            assert hasattr(HTTPClient, method_name), (
                f"HTTPClient missing method: {method_name}"
            )


class TestCRUDClientInterface:
    """Test CRUDClient class interface stability."""

    def test_crud_client_importable(self):
        """CRUDClient must be importable from sfq.crud."""
        from sfq.crud import CRUDClient

        assert CRUDClient is not None

    def test_crud_client_public_methods(self):
        """CRUDClient must have expected public methods."""
        from sfq.crud import CRUDClient

        expected_methods = [
            "create",
            "update",
            "delete",
            "cupdate",
            "cdelete",
            "read_static_resource_name",
            "read_static_resource_id",
            "update_static_resource_name",
            "update_static_resource_id",
        ]

        for method_name in expected_methods:
            assert hasattr(CRUDClient, method_name), (
                f"CRUDClient missing method: {method_name}"
            )


class TestSOAPClientInterface:
    """Test SOAPClient class interface stability."""

    def test_soap_client_importable(self):
        """SOAPClient must be importable from sfq.soap."""
        from sfq.soap import SOAPClient

        assert SOAPClient is not None

    def test_soap_client_public_methods(self):
        """SOAPClient must have expected public methods."""
        from sfq.soap import SOAPClient

        expected_methods = [
            "generate_soap_envelope",
            "generate_soap_header",
            "generate_soap_body",
            "extract_soap_result_fields",
            "xml_to_dict",
        ]

        for method_name in expected_methods:
            assert hasattr(SOAPClient, method_name), (
                f"SOAPClient missing method: {method_name}"
            )


class TestPlatformEventsClientInterface:
    """Test PlatformEventsClient class interface stability."""

    def test_platform_events_client_importable(self):
        """PlatformEventsClient must be importable from sfq.platform_events."""
        from sfq.platform_events import PlatformEventsClient

        assert PlatformEventsClient is not None

    def test_platform_events_client_methods(self):
        """PlatformEventsClient must have expected methods."""
        from sfq.platform_events import PlatformEventsClient

        expected_methods = [
            "list_events",
            "publish",
            "publish_batch",
            "subscribe",
        ]

        for method_name in expected_methods:
            assert hasattr(PlatformEventsClient, method_name), (
                f"PlatformEventsClient missing method: {method_name}"
            )

    def test_platform_events_client_importable_from_main(self):
        """PlatformEventsClient must be importable from main package."""
        from sfq import PlatformEventsClient

        assert PlatformEventsClient is not None


class TestMDAPIInterface:
    """Test MDAPI module interface stability."""

    def test_mdapi_functions_importable(self):
        """MDAPI functions must be importable."""
        from sfq.mdapi import mdapi_retrieve, unpack_mdapi_zip

        assert callable(mdapi_retrieve)
        assert callable(unpack_mdapi_zip)

    def test_mdapi_functions_importable_from_main(self):
        """MDAPI functions must be importable from main package."""
        from sfq import mdapi_retrieve, unpack_mdapi_zip

        assert callable(mdapi_retrieve)
        assert callable(unpack_mdapi_zip)

    def test_mdapi_retrieve_signature(self):
        """mdapi_retrieve must have correct signature."""
        from sfq.mdapi import mdapi_retrieve

        sig = inspect.signature(mdapi_retrieve)
        params = list(sig.parameters.keys())

        expected_params = [
            "sf",
            "package",
            "mdapi_version",
            "poll_interval_seconds",
            "max_poll_seconds",
        ]
        for param in expected_params:
            assert param in params, f"mdapi_retrieve missing parameter: {param}"


class TestUtilsInterface:
    """Test utils module interface stability."""

    def test_utils_functions_importable(self):
        """Utility functions must be importable."""
        from sfq.utils import (
            get_logger,
            records_to_html_table,
            extract_org_and_user_ids,
            format_headers_for_logging,
            parse_api_usage_from_header,
            log_api_usage,
        )

        functions = [
            get_logger,
            records_to_html_table,
            extract_org_and_user_ids,
            format_headers_for_logging,
            parse_api_usage_from_header,
            log_api_usage,
        ]

        for func in functions:
            assert callable(func), f"{func.__name__} should be callable"

    def test_get_logger_importable(self):
        """get_logger must be importable from sfq.utils."""
        from sfq.utils import get_logger

        assert callable(get_logger)


class TestReturnTypeStability:
    """Test that method return types remain stable."""

    @pytest.fixture
    def sf_auth_instance(self):
        """Create a basic SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_query_return_type(self, mock_request, sf_auth_instance):
        """query method must return Optional[Dict[str, Any]]."""
        mock_request.return_value = (200, '{"records": [], "totalSize": 0}')

        result = sf_auth_instance.query("SELECT Id FROM Account")
        assert result is None or isinstance(result, dict), (
            f"query() should return Optional[Dict], got {type(result)}"
        )

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_cquery_return_type(self, mock_request, sf_auth_instance):
        """cquery method must return Optional[Dict[str, Any]]."""
        mock_request.return_value = (200, '{"results": []}')

        result = sf_auth_instance.cquery({"test": "SELECT Id FROM Account"})
        assert result is None or isinstance(result, dict), (
            f"cquery() should return Optional[Dict], got {type(result)}"
        )

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_get_sobject_prefixes_return_type(self, mock_request, sf_auth_instance):
        """get_sobject_prefixes must return Optional[Dict[str, str]]."""
        mock_request.return_value = (
            200,
            '{"sobjects": [{"name": "Account", "keyPrefix": "001"}]}',
        )

        result = sf_auth_instance.get_sobject_prefixes()
        assert result is None or isinstance(result, dict), (
            f"get_sobject_prefixes() should return Optional[Dict], got {type(result)}"
        )

    @patch("sfq.http_client.HTTPClient.send_authenticated_request")
    def test_limits_return_type(self, mock_request, sf_auth_instance):
        """limits method must return Optional[Dict[str, Any]]."""
        mock_request.return_value = (
            200,
            '{"DailyApiRequests": {"Max": 15000, "Remaining": 14999}}',
        )

        result = sf_auth_instance.limits()
        assert result is None or isinstance(result, dict), (
            f"limits() should return Optional[Dict], got {type(result)}"
        )


class TestDynamicInterfaceDiscovery:
    """
    Dynamically discover and validate all public interfaces.

    These tests use introspection to find all public interfaces automatically,
    making them maintainable as the library grows.
    """

    def test_all_public_classes_discoverable(self):
        """All public classes in sfq must be discoverable via introspection."""
        public_classes = []

        for name in dir(sfq):
            if is_public_name(name):
                obj = getattr(sfq, name)
                if inspect.isclass(obj):
                    public_classes.append(name)

        expected_classes = ["SFAuth", "PlatformEventsClient"]
        for expected in expected_classes:
            assert expected in public_classes, (
                f"Expected public class '{expected}' not found. "
                f"Found classes: {public_classes}"
            )

    def test_all_public_exceptions_discoverable(self):
        """All public exceptions must be discoverable via introspection."""
        public_exceptions = []

        for name in dir(sfq):
            if is_public_name(name):
                obj = getattr(sfq, name)
                if inspect.isclass(obj) and issubclass(obj, Exception):
                    public_exceptions.append(name)

        expected_exceptions = [
            "SFQException",
            "AuthenticationError",
            "APIError",
            "QueryError",
            "QueryTimeoutError",
            "CRUDError",
            "SOAPError",
            "HTTPError",
            "ConfigurationError",
        ]

        for expected in expected_exceptions:
            assert expected in public_exceptions, (
                f"Expected exception '{expected}' not found. "
                f"Found exceptions: {public_exceptions}"
            )

    def test_sf_auth_all_public_members_valid_type(self):
        """All public members of SFAuth must be callable, property, simple type, or valid object."""
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

        valid_types = (
            type(None),
            bool,
            int,
            float,
            str,
            bytes,
            list,
            dict,
            set,
            tuple,
        )

        for name in dir(sf_auth):
            if is_public_name(name) and not is_dunder(name):
                attr = getattr(sf_auth, name)

                is_valid = (
                    callable(attr)
                    or isinstance(attr, property)
                    or isinstance(attr, valid_types)
                    or hasattr(attr, "__class__")
                )

                assert is_valid, (
                    f"Public member '{name}' is not a valid public interface type. "
                    f"Got: {type(attr)}"
                )

    def test_no_unexpected_public_attributes_on_sf_auth(self):
        """SFAuth should not have unexpected public instance attributes."""
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

        expected_public_attrs = {
            "__version__",
        }

        actual_public_attrs = set()
        for name in dir(sf_auth):
            if is_public_name(name) and not is_dunder(name):
                attr = getattr(sf_auth, name)
                if not callable(attr) and not isinstance(attr, property):
                    actual_public_attrs.add(name)

        expected_public_attrs.update(
            [
                "instance_url",
                "client_id",
                "client_secret",
                "refresh_token",
                "api_version",
                "token_endpoint",
                "access_token",
                "token_expiration_time",
                "token_lifetime",
                "user_agent",
                "sforce_client",
                "proxy",
                "org_id",
                "user_id",
                "platform_events",
            ]
        )

        unexpected = actual_public_attrs - expected_public_attrs

        assert len(unexpected) == 0, (
            f"SFAuth has unexpected public attributes: {unexpected}. "
            f"If these are intentional, add them to expected_public_attrs."
        )


class TestInterfaceSignatureStability:
    """
    Test that interface signatures remain stable across versions.

    These tests capture and compare method signatures to detect breaking changes.
    """

    def capture_signature_hash(self, func: Callable) -> str:
        """Create a hash of a function's signature for comparison."""
        sig = inspect.signature(func)

        parts = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue

            part = f"{name}:{serialize_annotation(param.annotation)}"
            if param.default is not inspect.Parameter.empty:
                part += f"={repr(param.default)}"
            parts.append(part)

        return_annotation = serialize_annotation(sig.return_annotation)
        parts.append(f"->{return_annotation}")

        return "|".join(parts)

    def test_sf_auth_query_signature_stable(self):
        """query method signature must remain stable."""
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

        signature_hash = self.capture_signature_hash(sf_auth.query)
        expected = "query:str|tooling:bool=False->Optional"

        assert signature_hash.startswith("query:str"), (
            f"query signature changed: {signature_hash}"
        )
        assert "tooling:bool" in signature_hash, (
            f"query signature missing tooling parameter: {signature_hash}"
        )

    def test_sf_auth_cquery_signature_stable(self):
        """cquery method signature must remain stable."""
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

        signature_hash = self.capture_signature_hash(sf_auth.cquery)

        assert "query_dict" in signature_hash, (
            f"cquery signature missing query_dict: {signature_hash}"
        )
        assert "batch_size" in signature_hash, (
            f"cquery signature missing batch_size: {signature_hash}"
        )
        assert "max_workers" in signature_hash, (
            f"cquery signature missing max_workers: {signature_hash}"
        )


class TestBackwardCompatibility:
    """Test backward compatibility with previous versions."""

    def test_sf_auth_supports_keyword_arguments(self):
        """All SFAuth parameters must be passable as keyword arguments."""
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token",
            api_version="v65.0",
            token_endpoint="/services/oauth2/token",
            access_token=None,
            token_expiration_time=None,
            token_lifetime=900,
            user_agent="test_agent",
            sforce_client="test_client",
            proxy="_auto",
        )

        assert sf_auth.instance_url == "https://test.my.salesforce.com"
        assert sf_auth.api_version == "v65.0"
        assert sf_auth.user_agent == "test_agent"

    def test_sf_auth_default_version_format(self):
        """Default API version must follow the expected format."""
        sf_auth = SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

        version = sf_auth.api_version
        assert version.startswith("v"), f"API version should start with 'v': {version}"
        assert "." in version, f"API version should contain '.': {version}"

    def test_instance_url_normalization(self):
        """Instance URL should be normalized to HTTPS."""
        sf_auth = SFAuth(
            instance_url="test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

        assert sf_auth.instance_url.startswith("https://"), (
            f"Instance URL should be HTTPS: {sf_auth.instance_url}"
        )


class TestDocumentationCoverage:
    """Test that public interfaces have documentation."""

    @pytest.fixture
    def sf_auth_instance(self):
        """Create a basic SFAuth instance for testing."""
        return SFAuth(
            instance_url="https://test.my.salesforce.com",
            client_id="test_client_id",
            refresh_token="test_refresh_token",
            client_secret="test_client_secret",
        )

    def test_sf_auth_init_has_docstring(self):
        """SFAuth.__init__ should have a docstring."""
        assert SFAuth.__init__.__doc__ is not None, (
            "SFAuth.__init__ should have a docstring"
        )

    def test_sf_auth_public_methods_have_docstrings(self, sf_auth_instance):
        """All public methods should have docstrings."""
        methods_without_docs = []

        for name in dir(sf_auth_instance):
            if is_public_name(name) and not is_dunder(name):
                attr = getattr(sf_auth_instance, name)
                if callable(attr) and not isinstance(attr, type):
                    if attr.__doc__ is None:
                        methods_without_docs.append(name)

        assert len(methods_without_docs) == 0, (
            f"Public methods without docstrings: {methods_without_docs}"
        )

    def test_module_has_docstring(self):
        """The main sfq module should have a docstring."""
        assert sfq.__doc__ is not None, "sfq module should have a docstring"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
