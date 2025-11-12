"""
End-to-end tests for Salesforce Metadata API retrieval.
"""

from io import BytesIO
import base64
import os
import zipfile
from dataclasses import dataclass
from typing import Any, List, Union, Dict
import pytest
from sfq import SFAuth

# --- Required Salesforce environment variables ---
REQUIRED_ENV_VARS = [
    "SF_INSTANCE_URL",
    "SF_CLIENT_ID",
    "SF_CLIENT_SECRET",
    "SF_REFRESH_TOKEN",
]


# --- Dataclass for test cases ---
@dataclass
class MdapiTestCase:
    input_value: Union[List[str], Dict[str, List[str]]]
    expected_member_string: str
    expected_names: List[str]


# --- Define test cases ---
inputs = [
    MdapiTestCase(
        input_value=["ApexComponent"],
        expected_member_string="<members>*</members>",
        expected_names=["ApexComponent"],
    ),
    MdapiTestCase(
        input_value=["ApexComponent", "RemoteSiteSetting", "ApexEmailNotifications"],
        expected_member_string="<members>*</members>",
        expected_names=["ApexComponent", "RemoteSiteSetting", "ApexEmailNotifications"],
    ),
    MdapiTestCase(
        input_value={"ApexEmailNotifications": ["ApexEmailNotifications"]},
        expected_member_string="<members>ApexEmailNotifications</members>",
        expected_names=["ApexEmailNotifications"],
    ),
]

# --- Define output permutations ---
outputs = [
    {"raw_response": True, "raw_bytes": False},  # raw zip in base64
    {"raw_response": False, "raw_bytes": True},  # raw bytes dict
    {"raw_response": False, "raw_bytes": False},  # decoded string dict
]


# --- Pytest fixture for authenticated SF instance ---
@pytest.fixture(scope="module")
def sf_instance() -> SFAuth:
    """Create an authenticated SFAuth instance for E2E testing."""
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing_vars:
        pytest.skip(
            f"Skipping MDAPI E2E tests; missing required env vars: {', '.join(missing_vars)}"
        )

    return SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET", "").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
        api_version="v65.0",
    )


# --- Parameterized test for all permutations ---
@pytest.mark.parametrize("test_case", inputs)
@pytest.mark.parametrize("output_opts", outputs)
def test_mdapi_retrieve_all_permutations(
    sf_instance: SFAuth, test_case: MdapiTestCase, output_opts: Dict[str, bool]
):
    """
    Test all permutations of input types and output modes for the Metadata API.
    """

    # Call the Metadata API
    result = sf_instance.mdapi_retrieve(
        test_case.input_value,
        raw_response=output_opts["raw_response"],
        raw_bytes=output_opts["raw_bytes"],
    )

    # Extract package.xml content based on output type
    if output_opts["raw_response"]:
        # raw_response returns a dict with 'zipFile' (base64)
        zip_bytes = BytesIO(base64.b64decode(result["zipFile"]))
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            with zf.open("unpackaged/package.xml") as pkg_file:
                package_xml = pkg_file.read().decode("utf-8")
    elif output_opts["raw_bytes"]:
        # raw_bytes returns a dict of bytes
        package_xml = result["unpackaged/package.xml"].decode("utf-8")
    else:
        # default: already decoded string
        package_xml = result["unpackaged/package.xml"]

    # Assertions
    assert test_case.expected_member_string in package_xml
    for name in test_case.expected_names:
        assert f"<name>{name}</name>" in package_xml
    assert (
        f"<version>{str(sf_instance.api_version).removeprefix('v')}</version>"
        in package_xml
    )
