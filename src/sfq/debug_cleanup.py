"""
Debug cleanup module for Salesforce-related debug artifacts.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("sfq")


class DebugCleanup:
    """
    Class handling debug artifact cleanup operations in Salesforce.
    """

    def __init__(self, sf_auth):
        """
        Initialize the DebugCleanup with an SFAuth instance.

        :param sf_auth: An authenticated SFAuth instance
        """
        self._sf_auth = sf_auth

    def _debug_cleanup_apex_logs(self) -> None:
        """
        This function performs cleanup operations for Apex debug logs.
        """
        apex_logs = self._sf_auth.query("SELECT Id FROM ApexLog ORDER BY LogLength DESC")
        if apex_logs and apex_logs.get("records"):
            log_ids = [log["Id"] for log in apex_logs["records"]]
            if log_ids:
                delete_response = self._sf_auth.cdelete(log_ids)
                logger.debug("Deleted Apex logs: %s", delete_response)
        else:
            logger.debug("No Apex logs found to delete.")

    def _debug_cleanup_trace_flags(self, expired_only: bool) -> None:
        """
        This function performs cleanup operations for Trace Flags.
        """
        if expired_only:
            now_iso_format = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            query = f"SELECT Id, ExpirationDate FROM TraceFlag WHERE ExpirationDate < {now_iso_format}"
        else:
            query = "SELECT Id, ExpirationDate FROM TraceFlag"

        traceflags = self._sf_auth.tooling_query(query)
        if traceflags['totalSize'] == 0:
            logger.debug("No expired Trace Flag configurations to delete.")
            return

        trace_flag_ids = [tf["Id"] for tf in traceflags["records"]]
        logger.debug("Deleting Trace Flags: %s", trace_flag_ids)
        results = self._sf_auth._crud_client.delete("TraceFlag", trace_flag_ids, api_type="tooling")
        # results = self._sf_auth.delete("TraceFlag", trace_flag_ids)
        logger.debug("Deleted Trace Flags: %s", results)

    def debug_cleanup(self, apex_logs: bool = True, expired_apex_flags: bool = True, all_apex_flags: bool = False) -> None:
        """
        Perform cleanup operations for Apex debug logs.

        :param apex_logs: Whether to clean up Apex logs (default: True)
        """
        if apex_logs:
            self._debug_cleanup_apex_logs()

        if all_apex_flags:
            self._debug_cleanup_trace_flags(expired_only=False)
        elif expired_apex_flags:
            self._debug_cleanup_trace_flags(expired_only=True)