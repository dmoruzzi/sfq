"""
Metadata API (MDAPI) support for sfq.

This module provides:

- _list_to_dict: normalize list-style MDAPI package input
- _dict_to_manifest: build Salesforce-compliant package.xml
- _build_retrieve_envelope: wrap manifest in a Metadata API SOAP retrieve envelope
- mdapi_retrieve: orchestrate a retrieve + polling until completion
- unpack_mdapi_zip: helper to unpack returned ZIP archives

The public entrypoint is mdapi_retrieve, which is also re-exported via sfq.__init__.
"""

from __future__ import annotations

import base64
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from .exceptions import SOAPError
from .http_client import HTTPClient
from .utils import get_logger

logger = get_logger("sfq.mdapi")


PackageDict = Dict[str, List[str]]
PackageInput = Union[PackageDict, List[str]]


def _list_to_dict(contents: List[str]) -> PackageDict:
    """
    Normalize a list of metadata types into the internal dict representation.

    Example:
        ["ApexComponent"] -> {"ApexComponent": ["*"]}

    This creates uniformity for downstream manifest generation.

    Args:
        contents: List of metadata type API names.

    Returns:
        Dict in the form { metadataType: ["*"] }.
    """
    normalized: PackageDict = {}
    for metadata_type in contents:
        mt = str(metadata_type).strip()
        if not mt:
            continue
        # Per design: a bare type means "all members"
        normalized[mt] = ["*"]
    # TRACE logging is provided by sfq.utils; Pylance may not be aware of .trace dynamically added.
    logger.trace("Normalized list to dict for MDAPI package: %s", normalized)  # type: ignore[attr-defined]
    return normalized


def _dict_to_manifest(
    contents: Mapping[str, Iterable[str]], version_string: str
) -> str:
    """
    Convert a normalized dictionary into a Salesforce package.xml-compatible XML string.

    Example:
        {"ApexComponent": ["SiteFooter", "SiteHeader"]} with "v65.0" ->

        <Package xmlns="http://soap.sforce.com/2006/04/metadata">
            <types>
                <members>SiteFooter</members>
                <members>SiteHeader</members>
                <name>ApexComponent</name>
            </types>
            <version>65.0</version>
        </Package>

    Notes:
        - version_string is expected as "v65.0" or "65.0"; we strip a leading 'v'.
        - Caller is responsible for input validation.
    """
    # Extract numeric API version; tolerate both "v65.0" and "65.0"
    api_version = str(version_string).strip()
    if api_version.lower().startswith("v"):
        api_version = api_version[1:]

    lines: List[str] = []
    lines.append('<Package xmlns="http://soap.sforce.com/2006/04/metadata">')

    for metadata_type, members in contents.items():
        mt = str(metadata_type).strip()
        if not mt:
            continue

        # Normalize members into a list of non-empty strings
        member_values: List[str] = []
        for m in members:
            mm = str(m).strip()
            if mm:
                member_values.append(mm)

        if not member_values:
            # No members given; for MDAPI manifest, this would be invalid.
            # We skip entirely instead of emitting an empty <types>.
            continue

        lines.append("    <types>")
        for member in member_values:
            lines.append(f"        <members>{member}</members>")
        lines.append(f"        <name>{mt}</name>")
        # Properly close the <types> element
        lines.append("    </types>")

    lines.append(f"    <version>{api_version}</version>")
    lines.append("</Package>")

    manifest_xml = "\n".join(lines)
    logger.trace("Generated MDAPI manifest package.xml:\n%s", manifest_xml)  # type: ignore[attr-defined]
    return manifest_xml


def _build_retrieve_envelope(
    manifest_xml: str,
    session_id: str,
    mdapi_version: str,
    api_version_override: Optional[str] = None,
) -> str:
    """
    Wrap the manifest XML in a Metadata API SOAP retrieve envelope.

    Args:
        manifest_xml: The package.xml content to embed as <unpackaged>.
        session_id: Salesforce session ID (sf.access_token).
        mdapi_version: Version string used for the MDAPI endpoint (e.g. "v65.0" or "65.0").
        api_version_override: If provided, the <apiVersion> value to send in retrieveRequest.
                              Defaults to mdapi_version stripped of any leading 'v'.
    """
    # Normalize "v65.0" -> "65.0" for the value inside <apiVersion>
    version_value = (
        api_version_override.strip()
        if api_version_override
        else str(mdapi_version).strip()
    )
    if version_value.lower().startswith("v"):
        version_value = version_value[1:]

    # Build envelope so that <Package> is nested directly inside <unpackaged>,
    # not wrapped in an extra <Package> element. The MDAPI expects exactly:
    #
    #   <unpackaged>
    #     <types>...</types>
    #     <version>..</version>
    #   </unpackaged>
    #
    # while manifest_xml currently already includes the outer <Package>.
    # Strip that wrapper so we only send its children under <unpackaged>.
    start = manifest_xml.find("<Package")
    if start != -1:
        # Find closing '>' of opening <Package ...> and the corresponding </Package>
        open_end = manifest_xml.find(">", start)
        close_start = manifest_xml.rfind("</Package>")
        if open_end != -1 and close_start != -1 and close_start > open_end:
            inner_manifest = manifest_xml[open_end + 1 : close_start].strip()
        else:
            inner_manifest = manifest_xml
    else:
        inner_manifest = manifest_xml

    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<soapenv:Envelope "
        'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:met="http://soap.sforce.com/2006/04/metadata" '
        'xmlns="http://soap.sforce.com/2006/04/metadata">'
        "<soapenv:Header>"
        "<met:SessionHeader>"
        f"<met:sessionId>{session_id}</met:sessionId>"
        "</met:SessionHeader>"
        "</soapenv:Header>"
        "<soapenv:Body>"
        "<met:retrieve>"
        "<retrieveRequest>"
        f"<apiVersion>{version_value}</apiVersion>"
        "<unpackaged>"
        f"{inner_manifest}"
        "</unpackaged>"
        "</retrieveRequest>"
        "</met:retrieve>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )
    logger.trace("Generated MDAPI retrieve SOAP envelope:\n%s", envelope)  # type: ignore[attr-defined]
    return envelope


def _build_check_retrieve_status_envelope(session_id: str, async_id: str) -> str:
    """
    Build the SOAP envelope for met:checkRetrieveStatus.

    Args:
        session_id: Salesforce session ID.
        async_id: Metadata AsyncResult ID returned by initial retrieve.
    """
    envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:met="http://soap.sforce.com/2006/04/metadata"
    xmlns="http://soap.sforce.com/2006/04/metadata">

    <soapenv:Header>
        <met:SessionHeader>
            <met:sessionId>{session_id}</met:sessionId>
        </met:SessionHeader>
    </soapenv:Header>

    <soapenv:Body>
        <met:checkRetrieveStatus>
            <id>{async_id}</id>
        </met:checkRetrieveStatus>
    </soapenv:Body>
</soapenv:Envelope>
"""
    logger.trace("Generated MDAPI checkRetrieveStatus SOAP envelope:\n%s", envelope)  # type: ignore[attr-defined]
    return envelope


def _parse_retrieve_initial_response(xml_string: str) -> Dict[str, Optional[str]]:
    """
    Parse the initial retrieveResponse SOAP XML.

    Returns:
        Dict with keys: done, id, state (values are strings or None).
    """

    logger.trace("Parsing MDAPI retrieve initial response XML")  # type: ignore[attr-defined]
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        logger.error("Failed to parse MDAPI retrieve initial response: %s", exc)
        raise SOAPError(f"Failed to parse retrieveResponse XML: {exc}") from exc

    # Handle both default and prefixed Metadata namespaces
    result = None
    # Try <retrieveResponse>/<result>
    for path in [
        ".//{http://soap.sforce.com/2006/04/metadata}retrieveResponse/{http://soap.sforce.com/2006/04/metadata}result",
        ".//{http://soap.sforce.com/2006/04/metadata}result",
    ]:
        result = root.find(path)
        if result is not None:
            break

    if result is None:
        logger.error("No <result> element found in retrieveResponse XML")
        raise SOAPError("No <result> element found in retrieveResponse XML")

    def _get_child_text(tag_suffix: str) -> Optional[str]:
        for child in result:
            if child.tag.endswith(tag_suffix):
                return child.text
        return None

    done = _get_child_text("done")
    async_id = _get_child_text("id")
    state = _get_child_text("state")

    logger.debug(
        "Metadata Retrieve %s with AsyncRequestFFX %s",
        state,
        async_id,
    )
    return {"done": done, "id": async_id, "state": state}


def _parse_check_retrieve_status_response(xml_string: str) -> Dict[str, Any]:
    """
    Parse a checkRetrieveStatusResponse SOAP XML.

    Returns:
        Dict with keys:
            done (str), status (str), success (str),
            id (str), zipFile (str|None), messages (list[str]) if present.
    """

    logger.trace("Parsing MDAPI checkRetrieveStatus response XML")  # type: ignore[attr-defined]
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        logger.error("Failed to parse MDAPI checkRetrieveStatus response: %s", exc)
        raise SOAPError(
            f"Failed to parse checkRetrieveStatusResponse XML: {exc}"
        ) from exc

    # Locate the <result> element
    result = None
    for path in [
        ".//{http://soap.sforce.com/2006/04/metadata}checkRetrieveStatusResponse/{http://soap.sforce.com/2006/04/metadata}result",
        ".//{http://soap.sforce.com/2006/04/metadata}result",
    ]:
        result = root.find(path)
        if result is not None:
            break

    if result is None:
        logger.error("No <result> element found in checkRetrieveStatusResponse XML")
        raise SOAPError("No <result> element found in checkRetrieveStatusResponse XML")

    def _get_child_text(tag_suffix: str) -> Optional[str]:
        for child in result:
            if child.tag.endswith(tag_suffix):
                return child.text
        return None

    done = _get_child_text("done")
    status = _get_child_text("status")
    success = _get_child_text("success")
    async_id = _get_child_text("id")
    zip_file = _get_child_text("zipFile")

    # Collect any message elements if present
    messages: List[str] = []
    for child in result:
        if child.tag.endswith("messages"):
            # Each messages element itself may have children, e.g., <problem>...
            for sub in child:
                if sub.text:
                    messages.append(sub.text)

    payload: Dict[str, Any] = {
        "done": done,
        "status": status,
        "success": success,
        "id": async_id,
        "zipFile": zip_file,
        "messages": messages,
    }

    logger.trace("Parsed MDAPI checkRetrieveStatus result: %s", payload)  # type: ignore[attr-defined]
    return payload


def unpack_mdapi_zip(
    zip_stream: BytesIO,
    decode_utf8: bool = True,
    output_dir: Optional[str] = None,
) -> dict[str, str | bytes]:
    """
    Unpack a Salesforce MDAPI ZIP file.

    This is a convenience helper for consumers of mdapi_retrieve.

    Args:
        zip_stream: BytesIO containing the ZIP file.
        decode_utf8: Whether to decode file contents to UTF-8 strings.
        output_dir: Optional path to extract contents to disk.

    Returns:
        dict[str, str | bytes]: Mapping of file paths to file content (in-memory).
    """
    import zipfile

    files: dict[str, str | bytes] = {}

    with zipfile.ZipFile(zip_stream) as zf:
        for name in zf.namelist():
            data = zf.read(name)
            if decode_utf8:
                try:
                    files[name] = data.decode("utf-8")
                except UnicodeDecodeError:
                    # fallback: keep as bytes if decoding fails
                    logger.warning(
                        "Failed to decode '%s' as UTF-8; keeping as bytes", name
                    )
                    files[name] = data
            else:
                files[name] = data
            if output_dir:
                zf.extract(name, output_dir)

    logger.trace(  # type: ignore[attr-defined]
        "Unpacked MDAPI zip with %d files%s",
        len(files),
        f" into {output_dir}" if output_dir else "",
    )
    return files


def mdapi_retrieve_raw(
    sf: Any,
    package: PackageInput,
    mdapi_version: str | None = None,
    poll_interval_seconds: float = 3.0,
    max_poll_seconds: float = 600.0,
):
    """
    Retrieve metadata via Salesforce Metadata API (MDAPI).

    This is the public-facing orchestration function. It:

    - Normalizes package (list -> dict)
    - Builds a MDAPI-compliant package.xml manifest
    - Wraps manifest in a SOAP retrieve envelope using sf.access_token
    - POSTs to /services/Soap/m/{version}
    - Polls checkRetrieveStatus until done == "true"
    - On success, returns the response from Salesforce as a dictionary
    - On failure, raises SOAPError with appropriate context

    Args:
        sf: An authenticated SFAuth-like object with:
            - access_token (property)
            - _http_client (HTTPClient instance) or equivalent accessor
        package: Either:
            - dict[str, list[str]] mapping metadata types to members, or
            - list[str] of metadata types (treated as wildcard '*')
        mdapi_version: Metadata API endpoint version (e.g., "v65.0").
        poll_interval_seconds: Delay between polling attempts.
        max_poll_seconds: Max total time to poll before aborting.

    Returns:
        Original Salesforce response JSON
        Dictionay containing:
            - 'zip_bytes': BytesIO object of the retrieved ZIP
            - 'file_names': list of file names inside the ZIP
            - 'package_xml': content of unpackaged/package.xml as string

    Raises:
        SOAPError: On HTTP failure, malformed responses, non-success MDAPI status,
                   or timeout waiting for completion.
    """
    if not hasattr(sf, "access_token"):
        raise SOAPError(
            "sf object must expose an access_token property for MDAPI retrieve"
        )

    # Default mdapi_version to the sf.api_version (without leading 'v') if not provided.
    if mdapi_version is None:
        api_ver = getattr(sf, "api_version", None)
        if not api_ver:
            raise SOAPError(
                "mdapi_version was not provided and sf.api_version is not available"
            )
        mdapi_version = str(api_ver).lstrip("v")

    access_token: Optional[str] = sf.access_token
    if not access_token:
        raise SOAPError("No access token available for MDAPI retrieve")

    # Obtain HTTP client from sf; prefer existing internal wiring
    http_client: Optional[HTTPClient] = getattr(sf, "_http_client", None)
    if http_client is None:
        raise SOAPError(
            "sf object must provide an _http_client (HTTPClient) for MDAPI retrieve"
        )

    # Normalize package input
    if isinstance(package, list):
        contents = _list_to_dict(package)
    else:
        # Treat mapping-like inputs (including plain dict) as a metadataType -> members map
        try:
            package_items = package.items()  # type: ignore[union-attr]
        except AttributeError as exc:
            raise SOAPError(
                "package must be dict[str, list[str]] or list[str] for MDAPI retrieve"
            ) from exc

        normalized: PackageDict = {}
        for key, values in package_items:
            mt = str(key).strip()
            if not mt:
                continue

            # Normalize values into a list of member strings:
            # - If it's already iterable (excluding strings/bytes), flatten.
            # - Otherwise, treat as a single scalar member.
            if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
                member_str = str(values).strip()
                members = [member_str] if member_str else []
            else:
                members = [str(v).strip() for v in values if str(v).strip()]

            if members:
                normalized[mt] = members

        contents = normalized
        logger.trace("Normalized dict MDAPI package input: %s", contents)  # type: ignore[attr-defined]

    if not contents:
        raise SOAPError("MDAPI retrieve package is empty after normalization")

    # Build manifest XML
    manifest_xml = _dict_to_manifest(contents, mdapi_version)

    # Build retrieve envelope
    retrieve_envelope = _build_retrieve_envelope(
        manifest_xml=manifest_xml,
        session_id=access_token,
        mdapi_version=mdapi_version,
    )

    # Prepare endpoint and headers
    # Normalize version for endpoint: "v65.0" or "65.0" -> "65.0"
    version_for_endpoint = str(mdapi_version).strip()
    if version_for_endpoint.lower().startswith("v"):
        version_for_endpoint = version_for_endpoint[1:]

    endpoint = f"/services/Soap/m/{version_for_endpoint}"

    headers = sf._http_client.get_common_headers()

    headers["Content-Type"] = "text/xml; charset=UTF-8"
    headers["SOAPAction"] = "retrieve"

    # Initial retrieve request
    status, data = http_client.send_request(
        method="POST",
        endpoint=endpoint,
        headers=headers,
        body=retrieve_envelope,
    )

    if status is None or data is None:
        raise SOAPError(
            f"MDAPI retrieve request failed with no response (status={status})"
        )

    logger.trace("MDAPI retrieve initial response XML:\n%s", data)  # type: ignore[attr-defined]

    if status != 200:
        raise SOAPError(f"MDAPI retrieve request failed: HTTP {status} - {data[:512]}")

    initial = _parse_retrieve_initial_response(data)
    async_id = initial.get("id")
    if not async_id:
        raise SOAPError(
            "MDAPI retrieve initial response did not contain an AsyncResult id"
        )

    # Polling loop
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed >= max_poll_seconds:
            raise SOAPError(
                f"MDAPI retrieve polling exceeded {max_poll_seconds} seconds for id {async_id}"
            )

        # Build and send checkRetrieveStatus request
        status_envelope = _build_check_retrieve_status_envelope(
            session_id=access_token,
            async_id=async_id,
        )

        poll_status, poll_body = http_client.send_request(
            method="POST",
            endpoint=endpoint,
            headers=headers,
            body=status_envelope,
        )

        if poll_status is None or poll_body is None:
            raise SOAPError(
                f"MDAPI checkRetrieveStatus failed with no response for id {async_id}"
            )

        logger.trace("MDAPI checkRetrieveStatus response XML:\n%s", poll_body)  # type: ignore[attr-defined]

        if poll_status != 200:
            raise SOAPError(
                f"MDAPI checkRetrieveStatus failed: HTTP {poll_status} - {poll_body[:512]}"
            )

        result = _parse_check_retrieve_status_response(poll_body)

        done = str(result.get("done") or "").lower() == "true"
        if not done:
            # Not finished yet; sleep and continue polling
            time.sleep(poll_interval_seconds)
            continue

        # At this point, done == true; inspect success/status/zipFile
        success_flag = str(result.get("success") or "").lower() == "true"
        status_text = result.get("status") or ""
        zip_b64 = result.get("zipFile")
        messages: List[str] = list(result.get("messages") or [])

        if not success_flag or status_text not in ("Succeeded", "SucceededPartial"):
            msg = (
                f"MDAPI retrieve completed with non-success status={status_text}, "
                f"success={success_flag}, id={async_id}, messages={messages}"
            )
            logger.error(msg)
            raise SOAPError(msg)

        if not zip_b64:
            msg = f"MDAPI retrieve reported success but no <zipFile> found for id {async_id}"
            logger.error(msg)
            raise SOAPError(msg)

        try:
            zip_bytes = base64.b64decode(zip_b64)
        except Exception as exc:
            msg = f"Failed to decode MDAPI zipFile for id {async_id}: {exc}"
            logger.error(msg)
            raise SOAPError(msg) from exc

        logger.debug(  # type: ignore[attr-defined]
            "MDAPI retrieve succeeded for id %s with %d zip bytes",
            async_id,
            len(zip_bytes),
        )

        return result


def mdapi_retrieve(
    sf: Any,
    package: PackageInput,
    mdapi_version: str | None = None,
    poll_interval_seconds: float = 3.0,
    max_poll_seconds: float = 600.0,
    raw_response: bool = False,
    raw_bytes: bool = False,
):
    """
    Retrieve metadata via Salesforce Metadata API (MDAPI).
    """
    result_json = mdapi_retrieve_raw(
        sf=sf,
        package=package,
        mdapi_version=mdapi_version,
        poll_interval_seconds=poll_interval_seconds,
        max_poll_seconds=max_poll_seconds,
    )
    if raw_response:
        return result_json
    
    zip_b64 = result_json["zipFile"]
    zip_bytes = BytesIO(base64.b64decode(zip_b64))
    zip_bytes.seek(0)
    return unpack_mdapi_zip(zip_bytes, decode_utf8=(not raw_bytes))
