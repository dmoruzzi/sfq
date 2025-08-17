"""
End-to-end tests for the CRUD client module.

These tests run against a real Salesforce instance using environment variables
to ensure the CRUD client functionality works correctly in practice.
"""

import os
import time

import pytest

from sfq import SFAuth
from sfq.auth import AuthManager
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


class TestCRUDClientE2E:
    """End-to-end tests for CRUDClient against real Salesforce instance."""

    def test_create_single_account(self, crud_client, http_client):
        """Test creating a single Account record."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Create test data
        test_account_name = f"Test Account E2E {int(time.time())}"
        insert_data = [{"Name": test_account_name, "Type": "Customer"}]

        # Execute create operation
        result = crud_client.create("Account", insert_data)

        # Verify result
        assert result is not None
        assert len(result) == 1
        assert result[0]["success"] == "true"
        assert "id" in result[0]

        created_id = result[0]["id"]
        assert created_id.startswith("001")  # Account ID prefix

        # Clean up - delete the created record
        delete_result = crud_client.cdelete([created_id])
        assert delete_result is not None
        assert len(delete_result) == 1
        assert delete_result[0]["success"] is True

    def test_create_multiple_accounts(self, crud_client, http_client):
        """Test creating multiple Account records in batch."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Create test data
        timestamp = int(time.time())
        insert_data = [
            {"Name": f"Test Account E2E Batch 1 {timestamp}", "Type": "Customer"},
            {"Name": f"Test Account E2E Batch 2 {timestamp}", "Type": "Partner"},
            {"Name": f"Test Account E2E Batch 3 {timestamp}", "Type": "Prospect"},
        ]

        # Execute create operation
        result = crud_client.create("Account", insert_data)

        # Verify result
        assert result is not None
        assert len(result) == 3

        created_ids = []
        for record_result in result:
            assert record_result["success"] == "true"
            assert "id" in record_result
            created_id = record_result["id"]
            assert created_id.startswith("001")  # Account ID prefix
            created_ids.append(created_id)

        # Clean up - delete the created records
        delete_result = crud_client.cdelete(created_ids)
        assert delete_result is not None
        assert len(delete_result) == 3
        for delete_record in delete_result:
            assert delete_record["success"] is True

    def test_create_with_tooling_api(self, crud_client, http_client):
        """Test creating a record using the Tooling API."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Create a simple Apex class
        timestamp = int(time.time())
        class_name = f"TestClass{timestamp}"
        apex_body = f"""public class {class_name} {{
    public static String getMessage() {{
        return 'Hello from {class_name}';
    }}
}}"""

        insert_data = [{"Name": class_name, "Body": apex_body}]

        # Execute create operation using tooling API
        result = crud_client.create("ApexClass", insert_data, api_type="tooling")

        # Verify result
        assert result is not None
        assert len(result) == 1
        assert result[0]["success"] == "true"
        assert "id" in result[0]

        created_id = result[0]["id"]
        assert created_id.startswith("01p")  # ApexClass ID prefix

        # Clean up - delete the created Apex class
        delete_result = crud_client.cdelete([created_id])
        assert delete_result is not None
        assert len(delete_result) == 1
        assert delete_result[0]["success"] is True

    def test_cupdate_account(self, crud_client, http_client):
        """Test updating Account records using composite API."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # First create an account to update
        timestamp = int(time.time())
        test_account_name = f"Test Account E2E Update {timestamp}"
        insert_data = [{"Name": test_account_name, "Type": "Customer"}]

        create_result = crud_client.create("Account", insert_data)
        assert create_result is not None
        assert len(create_result) == 1

        created_id = create_result[0]["id"]

        # Now update the account
        updated_name = f"Updated Account E2E {timestamp}"
        update_dict = {
            created_id: {
                "_": "Account",  # Specify sObject type
                "Name": updated_name,
                "Type": "Partner",
            }
        }

        # Execute update operation
        update_result = crud_client.cupdate(update_dict)

        # Verify update result
        assert update_result is not None
        assert len(update_result) == 1

        # The result structure depends on the composite API response
        composite_response = update_result[0]
        if "compositeResponse" in composite_response:
            response_item = composite_response["compositeResponse"][0]
            # 204 No Content is the correct response for successful PATCH
            assert response_item["httpStatusCode"] in [200, 204]
            assert response_item["referenceId"] == created_id

        # Clean up - delete the created record
        delete_result = crud_client.cdelete([created_id])
        assert delete_result is not None
        assert len(delete_result) == 1
        assert delete_result[0]["success"] is True

    def test_cupdate_multiple_accounts(self, crud_client, http_client):
        """Test updating multiple Account records using composite API."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # First create multiple accounts to update
        timestamp = int(time.time())
        insert_data = [
            {
                "Name": f"Test Account E2E Multi Update 1 {timestamp}",
                "Type": "Customer",
            },
            {
                "Name": f"Test Account E2E Multi Update 2 {timestamp}",
                "Type": "Customer",
            },
        ]

        create_result = crud_client.create("Account", insert_data)
        assert create_result is not None
        assert len(create_result) == 2

        created_ids = [record["id"] for record in create_result]

        # Now update both accounts
        update_dict = {}
        for i, account_id in enumerate(created_ids, 1):
            update_dict[account_id] = {
                "_": "Account",
                "Name": f"Updated Multi Account E2E {i} {timestamp}",
                "Type": "Partner",
            }

        # Execute update operation
        update_result = crud_client.cupdate(update_dict)

        # Verify update result
        assert update_result is not None
        assert len(update_result) >= 1  # May be batched

        # Clean up - delete the created records
        delete_result = crud_client.cdelete(created_ids)
        assert delete_result is not None
        assert len(delete_result) == 2
        for delete_record in delete_result:
            assert delete_record["success"] is True

    def test_cdelete_accounts(self, crud_client, http_client):
        """Test deleting Account records using collections API."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # First create accounts to delete
        timestamp = int(time.time())
        insert_data = [
            {"Name": f"Test Account E2E Delete 1 {timestamp}", "Type": "Customer"},
            {"Name": f"Test Account E2E Delete 2 {timestamp}", "Type": "Customer"},
            {"Name": f"Test Account E2E Delete 3 {timestamp}", "Type": "Customer"},
        ]

        create_result = crud_client.create("Account", insert_data)
        assert create_result is not None
        assert len(create_result) == 3

        created_ids = [record["id"] for record in create_result]

        # Execute delete operation
        delete_result = crud_client.cdelete(created_ids)

        # Verify delete result
        assert delete_result is not None
        assert len(delete_result) == 3

        for delete_record in delete_result:
            assert delete_record["success"] is True
            assert delete_record["id"] in created_ids

    def test_cdelete_with_batching(self, crud_client, http_client):
        """Test deleting records with batch processing."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Create 5 accounts to test batching
        timestamp = int(time.time())
        insert_data = []
        for i in range(5):
            insert_data.append(
                {
                    "Name": f"Test Account E2E Batch Delete {i} {timestamp}",
                    "Type": "Customer",
                }
            )

        create_result = crud_client.create("Account", insert_data)
        assert create_result is not None
        assert len(create_result) == 5

        created_ids = [record["id"] for record in create_result]

        # Execute delete operation with small batch size to force batching
        delete_result = crud_client.cdelete(created_ids, batch_size=2)

        # Verify delete result
        assert delete_result is not None
        assert len(delete_result) == 5

        for delete_record in delete_result:
            assert delete_record["success"] is True
            assert delete_record["id"] in created_ids

    def test_read_static_resource_id(self, crud_client, http_client, sf_auth):
        """Test reading a static resource by ID."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # First, find an existing static resource
        query_result = sf_auth.query(
            "SELECT Id, Name FROM StaticResource WHERE NamespacePrefix = null AND ContentType = 'text/plain' LIMIT 1"
        )

        if query_result and query_result.get("totalSize", 0) > 0:
            resource_id = query_result["records"][0]["Id"]
            resource_name = query_result["records"][0]["Name"]

            # Read the static resource content
            content = crud_client.read_static_resource_id(resource_id)

            # Verify we got content (could be empty but should not be None)
            assert content is not None
            print(
                f"Successfully read static resource '{resource_name}' (ID: {resource_id})"
            )
        else:
            pytest.skip("No unmanaged static resource of text/plain found")

    def test_read_static_resource_name(self, crud_client, http_client, sf_auth):
        """Test reading a static resource by name."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # First, find an existing static resource; this needs to be done via query

        query_result = sf_auth.query(
            "SELECT Id, Name FROM StaticResource WHERE NamespacePrefix = null AND ContentType = 'text/plain' LIMIT 1"
        )

        if query_result and query_result.get("totalSize", 0) > 0:
            resource_name = query_result["records"][0]["Name"]

            # Read the static resource content by name
            content = crud_client.read_static_resource_name(resource_name)

            # Verify we got content (could be empty but should not be None)
            assert content is not None
            print(f"Successfully read static resource by name: '{resource_name}'")
        else:
            pytest.skip("No unmanaged static resource of text/plain found")

    def test_update_static_resource_id(self, crud_client, http_client, sf_auth):
        """Test updating a static resource by ID."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # First, find an existing static resource
        query_result = sf_auth.query(
            "SELECT Id, Name FROM StaticResource WHERE NamespacePrefix = null AND ContentType = 'text/plain' LIMIT 1"
        )

        if query_result and query_result.get("totalSize", 0) > 0:
            resource_id = query_result["records"][0]["Id"]
            resource_name = query_result["records"][0]["Name"]

            # Read original content
            original_content = crud_client.read_static_resource_id(resource_id)

            # Update with new content
            timestamp = int(time.time())
            new_content = f"Updated content from E2E test at {timestamp}"

            update_result = crud_client.update_static_resource_id(
                resource_id, new_content
            )

            # Verify update was successful
            assert update_result is not None
            print(
                f"Successfully updated static resource '{resource_name}' (ID: {resource_id})"
            )

            # Read back the updated content to verify
            updated_content = crud_client.read_static_resource_id(resource_id)
            assert updated_content == new_content

            # Restore original content if we had any
            if original_content:
                restore_result = crud_client.update_static_resource_id(
                    resource_id, original_content
                )
                assert restore_result is not None
                print(
                    f"Restored original content for static resource '{resource_name}'"
                )
        else:
            pytest.skip("No unmanaged static resource of text/plain found")

    def test_update_static_resource_name(self, crud_client, http_client, sf_auth):
        """Test updating a static resource by name."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # First, find an existing static resource
        query_result = sf_auth.query(
            "SELECT Id, Name FROM StaticResource WHERE NamespacePrefix = null AND ContentType = 'text/plain' LIMIT 1"
        )

        if query_result and query_result.get("totalSize", 0) > 0:
            resource_name = query_result["records"][0]["Name"]

            # Read original content
            original_content = crud_client.read_static_resource_name(resource_name)

            # Update with new content
            timestamp = int(time.time())
            new_content = f"Updated content by name from E2E test at {timestamp}"

            update_result = crud_client.update_static_resource_name(
                resource_name, new_content
            )

            # Verify update was successful
            assert update_result is not None
            print(f"Successfully updated static resource by name: '{resource_name}'")

            # Read back the updated content to verify
            updated_content = crud_client.read_static_resource_name(resource_name)
            assert updated_content == new_content

            # Restore original content if we had any
            if original_content:
                restore_result = crud_client.update_static_resource_name(
                    resource_name, original_content
                )
                assert restore_result is not None
                print(
                    f"Restored original content for static resource '{resource_name}'"
                )
        else:
            pytest.skip("No unmanaged static resource of text/plain found")

    def test_create_update_delete_workflow(self, crud_client, http_client, sf_auth):
        """Test complete CRUD workflow: Create -> Update -> Delete."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        timestamp = int(time.time())

        # Step 1: Create
        original_name = f"Test CRUD Workflow {timestamp}"
        insert_data = [
            {"Name": original_name, "Type": "Customer", "Industry": "Technology"}
        ]

        create_result = crud_client.create("Account", insert_data)
        assert create_result is not None
        assert len(create_result) == 1
        assert create_result[0]["success"] == "true"

        created_id = create_result[0]["id"]
        print(f"Created Account: {created_id}")

        # Step 2: Update
        updated_name = f"Updated CRUD Workflow {timestamp}"
        update_dict = {
            created_id: {
                "_": "Account",
                "Name": updated_name,
                "Type": "Partner",
                "Industry": "Healthcare",
            }
        }

        update_result = crud_client.cupdate(update_dict)
        assert update_result is not None
        print(f"Updated Account: {created_id}")

        # Step 3: Verify update by querying
        verify_query = (
            f"SELECT Id, Name, Type, Industry FROM Account WHERE Id = '{created_id}'"
        )
        verify_result = sf_auth.query(verify_query)
        assert verify_result is not None
        assert verify_result["totalSize"] == 1

        updated_record = verify_result["records"][0]
        assert updated_record["Name"] == updated_name
        assert updated_record["Type"] == "Partner"
        assert updated_record["Industry"] == "Healthcare"
        print(f"Verified Account update: {updated_record}")

        # Step 4: Delete
        delete_result = crud_client.cdelete([created_id])
        assert delete_result is not None
        assert len(delete_result) == 1
        assert delete_result[0]["success"] is True
        print(f"Deleted Account: {created_id}")

        # Step 5: Verify deletion
        verify_delete_query = f"SELECT Id FROM Account WHERE Id = '{created_id}'"
        verify_delete_result = sf_auth.query(verify_delete_query)
        assert verify_delete_result is not None
        assert verify_delete_result["totalSize"] == 0
        print("Verified Account deletion")

    def test_error_handling_invalid_sobject(self, crud_client, http_client):
        """Test error handling with invalid sObject type."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Try to create a record for a non-existent sObject
        insert_data = [{"Name": "Test Invalid Object"}]

        result = crud_client.create("NonExistentObject", insert_data)

        # Should return None or empty result due to error
        assert result is None or result == []

    def test_error_handling_invalid_field(self, crud_client, http_client):
        """Test error handling with invalid field names."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Try to create a record with invalid field
        insert_data = [{"InvalidFieldName": "Test Value"}]

        result = crud_client.create("Account", insert_data)

        # Should return None or error result
        assert result is None or result == []

    def test_batch_processing_performance(self, crud_client, http_client):
        """Test batch processing with larger datasets."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Create 10 accounts to test batch processing
        timestamp = int(time.time())
        insert_data = []
        for i in range(10):
            insert_data.append(
                {"Name": f"Test Batch Performance {i} {timestamp}", "Type": "Customer"}
            )

        # Test with different batch sizes
        start_time = time.time()
        create_result = crud_client.create("Account", insert_data, batch_size=5)
        create_time = time.time() - start_time

        assert create_result is not None
        assert len(create_result) == 10

        created_ids = [record["id"] for record in create_result]
        print(f"Created 10 accounts in {create_time:.2f} seconds with batch_size=5")

        # Clean up with batch delete
        start_time = time.time()
        delete_result = crud_client.cdelete(created_ids, batch_size=3)
        delete_time = time.time() - start_time

        assert delete_result is not None
        assert len(delete_result) == 10

        for delete_record in delete_result:
            assert delete_record["success"] is True

        print(f"Deleted 10 accounts in {delete_time:.2f} seconds with batch_size=3")


if __name__ == "__main__":
    pytest.main([__file__])
