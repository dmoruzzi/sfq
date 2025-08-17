import os
import time

import pytest

from sfq import SFAuth


@pytest.fixture(scope="module")
def sf_instance():
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    sf = SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )
    return sf


@pytest.fixture(scope="module")
def static_resource(sf_instance):
    result = sf_instance.query(
        "SELECT Id, Name FROM StaticResource WHERE NamespacePrefix = null AND ContentType = 'text/plain' LIMIT 1"
    )
    assert result is not None, "Query failed"
    if result['totalSize'] == 0:
        pytest.skip("No unmanaged static resource of text/plain found")

    record = result["records"][0]
    resource_id = record["Id"]
    resource_name = record["Name"]
    original_content = sf_instance.read_static_resource_id(resource_id)

    yield {
        "id": resource_id,
        "name": resource_name,
        "original_content": original_content,
    }

    # Teardown: Restore original content (by both ID and name)
    sf_instance.update_static_resource_id(resource_id, original_content)
    sf_instance.update_static_resource_name(resource_name, original_content)


def test_read_static_resource_by_id_and_name(sf_instance, static_resource):
    resource_id = static_resource["id"]
    resource_name = static_resource["name"]
    original_content = static_resource["original_content"]

    content_by_id = sf_instance.read_static_resource_id(resource_id)
    content_by_name = sf_instance.read_static_resource_name(resource_name)

    assert content_by_id is not None, "Failed to read by ID"
    assert content_by_name == content_by_id, "Mismatch between read by ID and name"
    assert content_by_id == original_content, "Original content mismatch"


def test_update_static_resource_by_id(sf_instance, static_resource):
    resource_id = static_resource["id"]
    test_content = (
        f"Test updated at {int(time.time())} with sfq\\{sf_instance.__version__}"
    )

    update_result = sf_instance.update_static_resource_id(resource_id, test_content)
    assert update_result is not None, "Update by ID failed"

    updated_content = sf_instance.read_static_resource_id(resource_id)
    assert updated_content == test_content, "Updated content by ID does not match"


def test_update_static_resource_by_name(sf_instance, static_resource):
    resource_name = static_resource["name"]
    test_content = (
        f"Test updated at {int(time.time())} with sfq\\{sf_instance.__version__}"
    )

    update_result = sf_instance.update_static_resource_name(resource_name, test_content)
    assert update_result is not None, "Update by name failed"

    updated_content = sf_instance.read_static_resource_name(resource_name)
    assert updated_content == test_content, "Updated content by name does not match"


def test_read_nonexistent_static_resource(sf_instance):
    result = sf_instance.read_static_resource_id("__invalid_id")
    assert result is None, "Read of nonexistent resource should return None"

    result = sf_instance.read_static_resource_name("__invalid_name")
    assert result is None, "Read of nonexistent resource should return None"
