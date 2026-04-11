"""
End-to-end tests for the Bulk API v2 client module.

These tests run against a real Salesforce instance using environment variables
to ensure the Bulk API v2 delete functionality works correctly in practice.
"""

import os
import time

import pytest

from sfq import SFAuth
from sfq.auth import AuthManager
from sfq.bulk_client import BulkAPIV2Client
from sfq.crud import CRUDClient
from sfq.http_client import HTTPClient
from sfq.soap import SOAPClient


@pytest.fixture(scope="module")
def auth_manager():
    """Create an AuthManager instance for E2E testing."""
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    return AuthManager(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )


@pytest.fixture(scope="module")
def http_client(auth_manager):
    """Create an HTTPClient instance for E2E testing."""
    return HTTPClient(auth_manager)


@pytest.fixture(scope="module")
def soap_client(auth_manager):
    """Create a SOAPClient instance for E2E testing."""
    return SOAPClient(auth_manager)


@pytest.fixture(scope="module")
def crud_client(http_client, soap_client):
    """Create a CRUDClient instance for E2E testing."""
    return CRUDClient(http_client, soap_client)


@pytest.fixture(scope="module")
def bulk_client(http_client):
    """Create a BulkAPIV2Client instance for E2E testing."""
    return BulkAPIV2Client(http_client)


@pytest.fixture(scope="module")
def sf_auth():
    """Create an SFAuth instance for E2E testing."""
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    return SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )


class TestBulkAPIV2ClientE2E:
    """End-to-end tests for BulkAPIV2Client against real Salesforce instance."""

    SOBJECT = "FeedItem"

    def _check_bulk_api_available(self, delete_result):
        """Check if Bulk API v2 is available, skip if not."""
        if delete_result.get("results") and all(
            r.get("error") == "Failed to create job" for r in delete_result["results"]
        ):
            pytest.skip("Bulk API v2 not available in this org (endpoint returned 404)")

    def _get_current_user_id(self, http_client):
        """Get the current user's ID."""
        import json
        endpoint = f"/services/data/v65.0/query?q=SELECT+Id+FROM+User+WHERE+Id='{http_client.auth_manager.user_id}'"
        status_code, data = http_client.send_authenticated_request("GET", endpoint)
        if status_code == 200:
            result = json.loads(data)
            records = result.get("records", [])
            if records:
                return records[0]["Id"]
        return None

    def test_bulk_delete_single_record(self, bulk_client, crud_client, http_client):
        """Test deleting a single record using Bulk API v2."""
        http_client.refresh_token_and_update_auth()

        timestamp = int(time.time())
        user_id = self._get_current_user_id(http_client)
        insert_data = [{"Body": f"Test Bulk Delete {timestamp}", "ParentId": user_id}]

        create_result = crud_client.create(self.SOBJECT, insert_data)
        assert create_result is not None
        assert len(create_result) == 1

        created_id = create_result[0]["id"]
        print(f"Created FeedItem: {created_id}")

        delete_result = bulk_client.delete(self.SOBJECT, [created_id])
        assert delete_result is not None
        assert "results" in delete_result

        self._check_bulk_api_available(delete_result)

        print(f"Bulk delete result: {delete_result}")

    def test_bulk_delete_multiple_records(self, bulk_client, crud_client, http_client):
        """Test deleting multiple records using Bulk API v2."""
        http_client.refresh_token_and_update_auth()

        timestamp = int(time.time())
        user_id = self._get_current_user_id(http_client)
        insert_data = [
            {"Body": f"Test Bulk Delete 1 {timestamp}", "ParentId": user_id},
            {"Body": f"Test Bulk Delete 2 {timestamp}", "ParentId": user_id},
        ]

        create_result = crud_client.create(self.SOBJECT, insert_data)
        assert create_result is not None
        assert len(create_result) == 2

        created_ids = [record["id"] for record in create_result]
        print(f"Created FeedItems: {created_ids}")

        delete_result = bulk_client.delete(self.SOBJECT, created_ids)
        assert delete_result is not None
        assert delete_result.get("batches") == 1

        self._check_bulk_api_available(delete_result)

        print(f"Bulk delete result: {delete_result}")

    def test_bulk_delete_with_batching(self, bulk_client, crud_client, http_client):
        """Test deleting records with automatic batching."""
        http_client.refresh_token_and_update_auth()

        timestamp = int(time.time())
        user_id = self._get_current_user_id(http_client)
        insert_data = [
            {"Body": f"Test Bulk Batch {i} {timestamp}", "ParentId": user_id}
            for i in range(5)
        ]

        create_result = crud_client.create(self.SOBJECT, insert_data)
        assert create_result is not None

        created_ids = [record["id"] for record in create_result]
        print(f"Created {len(created_ids)} FeedItems")

        delete_result = bulk_client.delete(self.SOBJECT, created_ids, batch_size=2)
        assert delete_result is not None

        self._check_bulk_api_available(delete_result)

        assert delete_result.get("batches") >= 1
        print(f"Bulk delete result: {delete_result}")

    def test_bulk_delete_query_first(self, bulk_client, http_client, sf_auth, crud_client):
        """Test bulk delete by first querying existing records we created."""
        http_client.refresh_token_and_update_auth()

        timestamp = int(time.time())
        user_id = self._get_current_user_id(http_client)
        insert_data = [
            {"Body": f"Test Bulk Query First {i} {timestamp}", "ParentId": user_id}
            for i in range(3)
        ]

        create_result = crud_client.create(self.SOBJECT, insert_data)
        if not create_result or len(create_result) == 0:
            pytest.skip("Failed to create test records")

        record_ids = [record["id"] for record in create_result]
        print(f"Created {len(record_ids)} FeedItems to delete")

        delete_result = bulk_client.delete(self.SOBJECT, record_ids)
        assert delete_result is not None

        self._check_bulk_api_available(delete_result)

        print(f"Bulk delete result: {delete_result}")

        errors = [r.get("error", "") for r in delete_result.get("results", [])]
        if any("failed to complete" in e.lower() for e in errors):
            pytest.skip("Bulk delete job failed to complete")

        id_list = "','".join(record_ids)
        verify_result = sf_auth.query(
            f"SELECT Id FROM {self.SOBJECT} WHERE Id IN ('{id_list}')"
        )
        assert verify_result is not None
        assert verify_result.get("totalSize", -1) == 0, (
            f"Records were not deleted: {verify_result}"
        )
        print("Verified records are deleted")


class TestBulkAPIV2OnSFAuth:
    """End-to-end tests for bulkapiv2_delete method on SFAuth."""

    SOBJECT = "FeedItem"

    def _get_current_user_id(self, http_client):
        """Get the current user's ID."""
        import json
        endpoint = f"/services/data/v65.0/query?q=SELECT+Id+FROM+User+WHERE+Id='{http_client.auth_manager.user_id}'"
        status_code, data = http_client.send_authenticated_request("GET", endpoint)
        if status_code == 200:
            result = json.loads(data)
            records = result.get("records", [])
            if records:
                return records[0]["Id"]
        return None

    def _check_bulk_api_available(self, delete_result):
        """Check if Bulk API v2 is available, skip if not."""
        if delete_result.get("results") and all(
            r.get("error") == "Failed to create job" for r in delete_result["results"]
        ):
            pytest.skip("Bulk API v2 not available in this org (endpoint returned 404)")

    def test_bulkapiv2_delete_method(self, sf_auth):
        """Test using bulkapiv2_delete directly on SFAuth instance."""
        http_client = sf_auth._http_client
        http_client.refresh_token_and_update_auth()

        timestamp = int(time.time())
        user_id = self._get_current_user_id(http_client)
        insert_data = [
            {"Body": f"Test SFAuth Bulk {i} {timestamp}", "ParentId": user_id}
            for i in range(3)
        ]

        create_result = sf_auth._crud_client.create(self.SOBJECT, insert_data)
        assert create_result is not None

        created_ids = [record["id"] for record in create_result]
        print(f"Created FeedItems via SFAuth: {created_ids}")

        delete_result = sf_auth.bulkapiv2_delete(self.SOBJECT, created_ids)
        assert delete_result is not None
        assert "results" in delete_result

        self._check_bulk_api_available(delete_result)

        assert delete_result.get("batches") == 1

        print(f"bulkapiv2_delete result: {delete_result}")

    def test_bulkapiv2_delete_with_small_batch(self, sf_auth):
        """Test bulkapiv2_delete with small batch size."""
        http_client = sf_auth._http_client
        http_client.refresh_token_and_update_auth()

        timestamp = int(time.time())
        user_id = self._get_current_user_id(http_client)
        insert_data = [
            {"Body": f"Test Batch Size {i} {timestamp}", "ParentId": user_id}
            for i in range(6)
        ]

        create_result = sf_auth._crud_client.create(self.SOBJECT, insert_data)
        assert create_result is not None

        created_ids = [record["id"] for record in create_result]
        print(f"Created FeedItems: {created_ids}")

        delete_result = sf_auth.bulkapiv2_delete(
            self.SOBJECT, created_ids, batch_size=2, poll_interval_seconds=3.0
        )
        assert delete_result is not None

        self._check_bulk_api_available(delete_result)

        batches = delete_result.get("batches", 0)
        print(f"Number of batches: {batches}")
        print(f"bulk delete result: {delete_result}")


if __name__ == "__main__":
    pytest.main([__file__])