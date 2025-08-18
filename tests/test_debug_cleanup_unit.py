import pytest
from unittest.mock import MagicMock
from sfq.debug_cleanup import DebugCleanup

class DummySFAuth:
    def __init__(self):
        self._crud_client = MagicMock()
        self.cdelete = MagicMock()
        self.query = MagicMock()
        self.tooling_query = MagicMock()

@pytest.fixture
def dummy_sf_auth():
    return DummySFAuth()

@pytest.fixture
def debug_cleanup(dummy_sf_auth):
    return DebugCleanup(dummy_sf_auth)

def test_debug_cleanup_apex_logs(debug_cleanup, dummy_sf_auth):
    dummy_sf_auth.query.return_value = {"records": [{"Id": "log1"}, {"Id": "log2"}]}
    debug_cleanup._debug_cleanup_apex_logs()
    dummy_sf_auth.cdelete.assert_called_once_with(["log1", "log2"])

def test_debug_cleanup_apex_logs_no_logs(debug_cleanup, dummy_sf_auth):
    dummy_sf_auth.query.return_value = {"records": []}
    debug_cleanup._debug_cleanup_apex_logs()
    dummy_sf_auth.cdelete.assert_not_called()

def test_debug_cleanup_trace_flags_expired(debug_cleanup, dummy_sf_auth):
    dummy_sf_auth.tooling_query.return_value = {"totalSize": 2, "records": [{"Id": "tf1"}, {"Id": "tf2"}]}
    debug_cleanup._sf_auth._crud_client.delete.return_value = "deleted"
    debug_cleanup._debug_cleanup_trace_flags(expired_only=True)
    dummy_sf_auth._crud_client.delete.assert_called_once_with("TraceFlag", ["tf1", "tf2"], api_type="tooling")

def test_debug_cleanup_trace_flags_none(debug_cleanup, dummy_sf_auth):
    dummy_sf_auth.tooling_query.return_value = {"totalSize": 0, "records": []}
    debug_cleanup._debug_cleanup_trace_flags(expired_only=True)
    dummy_sf_auth._crud_client.delete.assert_not_called()

def test_debug_cleanup_dispatch(debug_cleanup, dummy_sf_auth):
    # Test all_apex_flags True
    dummy_sf_auth.tooling_query.return_value = {"totalSize": 1, "records": [{"Id": "tf1"}]}
    debug_cleanup._sf_auth._crud_client.delete.reset_mock()
    debug_cleanup.debug_cleanup(apex_logs=False, expired_apex_flags=True, all_apex_flags=True)
    dummy_sf_auth._crud_client.delete.assert_called_once_with("TraceFlag", ["tf1"], api_type="tooling")

    # Test expired_apex_flags True, all_apex_flags False
    debug_cleanup._sf_auth._crud_client.delete.reset_mock()
    debug_cleanup.debug_cleanup(apex_logs=False, expired_apex_flags=True, all_apex_flags=False)
    dummy_sf_auth._crud_client.delete.assert_called_once_with("TraceFlag", ["tf1"], api_type="tooling")

    # Test apex_logs True
    dummy_sf_auth.query.return_value = {"records": [{"Id": "log1"}]}
    debug_cleanup._sf_auth.cdelete.reset_mock()
    debug_cleanup.debug_cleanup(apex_logs=True, expired_apex_flags=False, all_apex_flags=False)
    dummy_sf_auth.cdelete.assert_called_once_with(["log1"])
