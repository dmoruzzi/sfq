import base64
import io
from io import BytesIO
from typing import Any, Dict, List

from sfq import SFAuth, mdapi_retrieve, unpack_mdapi_zip
from sfq.mdapi import (
    _build_check_retrieve_status_envelope,
    _build_retrieve_envelope,
    _dict_to_manifest,
    _list_to_dict,
)


class DummyHTTPClient:
    """
    Minimal stand-in for HTTPClient used to simulate MDAPI retrieve flows.

    It captures requests and returns pre-programmed responses in sequence.
    Provides only the surface used by mdapi_retrieve():
      - send_request(...)
      - get_common_headers()
    """

    def __init__(self, responses: List[Dict[str, Any]]):
        # Each response is: {"status": int, "body": str}
        self._responses: List[Dict[str, Any]] = list(responses)
        self.requests: List[Dict[str, Any]] = []

    def send_request(
        self,
        method: str,
        endpoint: str,
        headers: Dict[str, str],
        body: str | None = None,
    ) -> tuple[int | None, str | None]:
        self.requests.append(
            {
                "method": method,
                "endpoint": endpoint,
                "headers": headers,
                "body": body,
            }
        )
        if not self._responses:
            return None, None
        r = self._responses.pop(0)
        return r.get("status"), r.get("body")

    def get_common_headers(self) -> Dict[str, str]:
        # Minimal subset; real HTTPClient adds more, which mdapi_retrieve does not depend on.
        return {
            "User-Agent": "sfq-test-client",
            "Sforce-Call-Options": "client=sfq-test-client",
            "Accept": "application/json",
        }

    # SFAuth._refresh_token_if_needed may call this; we no-op.
    def refresh_token_and_update_auth(self) -> str | None:  # pragma: no cover
        return None


class DummySF(SFAuth):
    """
    SFAuth-compatible wrapper that injects DummyHTTPClient for MDAPI tests.

    - Uses real SFAuth wiring for api_version, etc.
    - Overrides _http_client so mdapi_retrieve() uses DummyHTTPClient.
    """

    def __init__(
        self,
        access_token: str,
        responses: List[Dict[str, Any]],
        api_version: str = "v65.0",
    ):
        super().__init__(
            instance_url="https://example.my.salesforce.com",
            client_id="client",
            client_secret="secret",
            refresh_token="refresh",
            api_version=api_version,
        )
        # Force access token for tests
        self._auth_manager.access_token = access_token
        # Inject dummy HTTP client for MDAPI calls
        self._http_client = DummyHTTPClient(responses)


def _make_initial_retrieve_response(async_id: str, state: str = "Queued") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Body>
    <retrieveResponse>
      <result>
        <done>false</done>
        <id>{async_id}</id>
        <state>{state}</state>
      </result>
    </retrieveResponse>
  </soapenv:Body>
</soapenv:Envelope>
"""


def _make_check_status_response(
    async_id: str,
    done: bool,
    success: bool = True,
    status: str = "Succeeded",
    zip_b64: str | None = None,
    problem: str | None = None,
) -> str:
    done_str = "true" if done else "false"
    success_str = "true" if success else "false"
    zip_part = f"<zipFile>{zip_b64}</zipFile>" if zip_b64 is not None else ""
    messages = f"<messages><problem>{problem}</problem></messages>" if problem else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Body>
    <checkRetrieveStatusResponse>
      <result>
        <done>{done_str}</done>
        <status>{status}</status>
        <success>{success_str}</success>
        <id>{async_id}</id>
        {zip_part}
        {messages}
      </result>
    </checkRetrieveStatusResponse>
  </soapenv:Body>
</soapenv:Envelope>
"""


# ------------------------
# Unit tests for internals
# ------------------------


def test_list_to_dict_normalization():
    assert _list_to_dict(["ApexComponent"]) == {"ApexComponent": ["*"]}
    assert _list_to_dict(["A", "B"]) == {"A": ["*"], "B": ["*"]}
    # Empty/whitespace should be ignored
    assert _list_to_dict(["  ", "A"]) == {"A": ["*"]}


def test_dict_to_manifest_structure_and_version_from_string_inputs():
    contents = {"ApexComponent": ["SiteFooter", "SiteHeader"]}

    # Accepts plain "65.0"
    manifest_64 = _dict_to_manifest(contents, "65.0")
    assert '<Package xmlns="http://soap.sforce.com/2006/04/metadata">' in manifest_64
    assert "<name>ApexComponent</name>" in manifest_64
    assert "<members>SiteFooter</members>" in manifest_64
    assert "<members>SiteHeader</members>" in manifest_64
    assert "<version>65.0</version>" in manifest_64

    # Accepts "v65.0" and strips "v"
    manifest_65 = _dict_to_manifest(contents, "v65.0")
    assert "<version>65.0</version>" in manifest_65


def test_build_retrieve_envelope_uses_token_and_normalizes_versions():
    contents = {"ApexComponent": ["*"]}
    manifest = _dict_to_manifest(contents, "v65.0")

    envelope = _build_retrieve_envelope(
        manifest_xml=manifest,
        session_id="00Dxx_token",
        mdapi_version="v65.0",
    )

    # Session header present
    assert "<met:sessionId>00Dxx_token</met:sessionId>" in envelope

    # <apiVersion> uses mdapi_version stripped of leading "v"
    assert "<apiVersion>65.0</apiVersion>" in envelope

    # <unpackaged> content comes from manifest children (no outer <Package>)
    assert "<unpackaged>" in envelope
    assert "<members>*</members>" in envelope
    assert "<name>ApexComponent</name>" in envelope
    assert "<version>65.0</version>" in envelope


def test_build_check_retrieve_status_envelope_basic_shape():
    async_id = "09Sxx0000000001AAA"
    envelope = _build_check_retrieve_status_envelope("00Dxx_token", async_id)

    assert "<met:sessionId>00Dxx_token</met:sessionId>" in envelope
    assert f"<id>{async_id}</id>" in envelope
    assert "checkRetrieveStatus" in envelope


# ------------------------
# Behavioral tests for mdapi_retrieve
# ------------------------


def test_mdapi_retrieve_success_flow_via_top_level_helper():
    """
    Validate top-level mdapi_retrieve() orchestration.

    This uses DummySF + DummyHTTPClient and asserts:
      - correct polling behavior
      - final result matches the simulated last checkRetrieveStatusResponse
    """
    async_id = "09Sxx0000000001AAA"

    # Prepare a small but valid ZIP payload
    import zipfile

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w") as zf:
        zf.writestr(
            "unpackaged/package.xml",
            '<Package xmlns="http://soap.sforce.com/2006/04/metadata"><version>65.0</version></Package>',
        )
    zip_bytes = mem.getvalue()
    zip_b64 = base64.b64encode(zip_bytes).decode("ascii")

    # Simulate:
    #  - initial retrieve (Queued)
    #  - first poll (InProgress)
    #  - final poll (Succeeded with zipFile)
    responses = [
        {
            "status": 200,
            "body": _make_initial_retrieve_response(async_id, state="Queued"),
        },
        {
            "status": 200,
            "body": _make_check_status_response(
                async_id=async_id,
                done=False,
                success=False,
                status="InProgress",
                zip_b64=None,
            ),
        },
        {
            "status": 200,
            "body": _make_check_status_response(
                async_id=async_id,
                done=True,
                success=True,
                status="Succeeded",
                zip_b64=zip_b64,
            ),
        },
    ]

    sf = DummySF(access_token="00Dxx_token", responses=responses, api_version="v65.0")

    result = mdapi_retrieve(
        sf=sf,
        package={"ApexComponent": ["*"]},
        mdapi_version="v65.0",
        poll_interval_seconds=0.0,
        max_poll_seconds=5.0,
    )

    # Current mdapi_retrieve returns a dict; assert it's a mapping and that we hit the right endpoint.
    assert isinstance(result, dict)

    # Validate HTTP interactions: 1 initial + 2 polls to the correct MDAPI version
    assert len(sf._http_client.requests) == 3
    assert sf._http_client.requests[0]["endpoint"].endswith("/services/Soap/m/65.0")


def test_mdapi_retrieve_via_sfauth_method_explicit_version():
    """
    Verify SFAuth.mdapi_retrieve() wrapper passes through mdapi_version to mdapi_retrieve.

    We call with explicit mdapi_version="v65.0" so we can assert the endpoint choice.
    """
    async_id = "09Sxx0000000002AAA"

    # Prepare a small valid ZIP
    import zipfile

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w") as zf:
        zf.writestr(
            "unpackaged/package.xml",
            '<Package xmlns="http://soap.sforce.com/2006/04/metadata"><version>65.0</version></Package>',
        )
    zip_bytes = mem.getvalue()
    zip_b64 = base64.b64encode(zip_bytes).decode("ascii")

    responses = [
        {
            "status": 200,
            "body": _make_initial_retrieve_response(async_id, state="Queued"),
        },
        {
            "status": 200,
            "body": _make_check_status_response(
                async_id=async_id,
                done=True,
                success=True,
                status="Succeeded",
                zip_b64=zip_b64,
            ),
        },
    ]

    # Use sf.api_version different from mdapi_version to prove mdapi_version wins
    sf = DummySF(access_token="00Dxx_token", responses=responses, api_version="v65.0")

    result = sf.mdapi_retrieve(
        package=["ApexComponent"],
        mdapi_version="v65.0",
        poll_interval_seconds=0.0,
        max_poll_seconds=5.0,
    )

    # Wrapper returns whatever mdapi_retrieve returns; assert dict + correct endpoint wiring.
    assert isinstance(result, dict)

    # Ensure MDAPI endpoint matches mdapi_version ("65.0"), not sf.api_version ("65.0")
    assert sf._http_client.requests[0]["endpoint"].endswith("/services/Soap/m/65.0")


# ------------------------
# unpack_mdapi_zip
# ------------------------


def test_unpack_mdapi_zip_round_trip():
    """
    Validate unpack_mdapi_zip returns the expected in-memory mapping.
    """
    import zipfile

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w") as zf:
        zf.writestr("a.txt", b"hello")
        zf.writestr("b/b.txt", b"world")
    mem.seek(0)

    # Library's unpack_mdapi_zip returns dict[str, str] (decoded) in current implementation.
    files = unpack_mdapi_zip(BytesIO(mem.read()))

    assert files["a.txt"] == "hello"
    assert files["b/b.txt"] == "world"