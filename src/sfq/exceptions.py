"""
Custom exception classes for the SFQ library.

This module defines the exception hierarchy used throughout the SFQ library
to provide consistent error handling and meaningful error messages.
"""


class SFQException(Exception):
    """Base exception for SFQ library."""

    pass


class AuthenticationError(SFQException):
    """Raised when authentication fails."""

    pass


class APIError(SFQException):
    """Raised when API requests fail."""

    pass


class QueryError(APIError):
    """Raised when query operations fail."""

    pass


class QueryTimeoutError(QueryError):
    """Raised when query operations timeout after all retry attempts."""

    pass


class CRUDError(APIError):
    """Raised when CRUD operations fail."""

    pass


class SOAPError(APIError):
    """Raised when SOAP operations fail."""

    pass


class HTTPError(SFQException):
    """Raised when HTTP communication fails."""

    pass


class ConfigurationError(SFQException):
    """Raised when configuration is invalid."""

    pass
