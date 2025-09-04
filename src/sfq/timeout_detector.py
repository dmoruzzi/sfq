"""
Timeout detection module for the SFQ library.

This module provides utilities for detecting different types of timeout errors
that can occur during HTTP requests to Salesforce APIs.
"""

from typing import Optional
import errno


class TimeoutDetector:
    """Utility class for detecting timeout conditions in HTTP responses."""
    
    # Server timeout message pattern
    SERVER_TIMEOUT_MESSAGE = "Your query request was running for too long."
    # Server timeout error code pattern
    SERVER_TIMEOUT_ERROR_CODE = "QUERY_TIMEOUT"
    
    @staticmethod
    def is_server_timeout(status_code: Optional[int], response_body: Optional[str]) -> bool:
        """
        Detect server-side query timeout from HTTP response.
        
        Server timeouts are indicated by:
        - HTTP status code 400
        - Response body containing the specific timeout message OR timeout error code
        
        Args:
            status_code: HTTP status code from the response
            response_body: Response body content as string
            
        Returns:
            bool: True if this is a server timeout, False otherwise
        """
        if status_code != 400:
            return False
            
        if response_body is None or response_body == "":
            return False
            
        # Check for either the timeout message or the error code
        # Handle potential encoding issues by using string containment check
        try:
            return (TimeoutDetector.SERVER_TIMEOUT_MESSAGE in response_body or 
                    TimeoutDetector.SERVER_TIMEOUT_ERROR_CODE in response_body)
        except (TypeError, UnicodeError):
            # If there are encoding issues, assume it's not a timeout
            return False
    
    @staticmethod
    def is_connection_timeout(
        status_code: Optional[int], 
        response_body: Optional[str], 
        exception: Optional[Exception] = None
    ) -> bool:
        """
        Detect connection timeout from HTTP response and exception context.
        
        Connection timeouts are indicated by:
        - HTTP status code is None
        - Response body is None
        - Exception with errno 110 (Connection timed out)
        
        Args:
            status_code: HTTP status code from the response (should be None)
            response_body: Response body content (should be None)
            exception: Exception that occurred during the request
            
        Returns:
            bool: True if this is a connection timeout, False otherwise
        """
        # Check for the basic connection timeout pattern
        if status_code is not None or response_body is not None:
            return False
            
        # Check if we have an exception with errno 110
        if exception is None:
            return False
            
        # Check for errno 110 in various exception types
        if hasattr(exception, 'errno') and exception.errno == errno.ETIMEDOUT:
            return True
            
        # Check for errno in nested exceptions (common in urllib/http.client)
        if hasattr(exception, '__cause__') and exception.__cause__ is not None:
            cause = exception.__cause__
            if hasattr(cause, 'errno') and cause.errno == errno.ETIMEDOUT:
                return True
                
        # Check for errno in args (some exceptions store it there)
        if hasattr(exception, 'args') and exception.args:
            for arg in exception.args:
                if hasattr(arg, 'errno') and arg.errno == errno.ETIMEDOUT:
                    return True
                    
        return False
    
    @staticmethod
    def is_timeout_error(
        status_code: Optional[int], 
        response_body: Optional[str], 
        exception: Optional[Exception] = None
    ) -> bool:
        """
        Unified timeout detection for both server and connection timeout scenarios.
        
        This method combines both server timeout and connection timeout detection
        to provide a single interface for timeout checking.
        
        Args:
            status_code: HTTP status code from the response
            response_body: Response body content as string
            exception: Exception that occurred during the request
            
        Returns:
            bool: True if this is any type of timeout error, False otherwise
        """
        return (
            TimeoutDetector.is_server_timeout(status_code, response_body) or
            TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        )
    
    @staticmethod
    def get_timeout_type(
        status_code: Optional[int], 
        response_body: Optional[str], 
        exception: Optional[Exception] = None
    ) -> Optional[str]:
        """
        Determine the type of timeout error.
        
        Args:
            status_code: HTTP status code from the response
            response_body: Response body content as string
            exception: Exception that occurred during the request
            
        Returns:
            str: 'server' for server timeouts, 'connection' for connection timeouts,
                 None if not a timeout error
        """
        if TimeoutDetector.is_server_timeout(status_code, response_body):
            return 'server'
        elif TimeoutDetector.is_connection_timeout(status_code, response_body, exception):
            return 'connection'
        else:
            return None