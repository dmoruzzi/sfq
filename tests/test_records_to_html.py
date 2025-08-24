import os

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


def test_html_table_conversion(sf_instance):
    """
    Test the HTML table conversion utility.
    """
    records = sf_instance.query("SELECT Id,NamespacePrefix FROM Organization LIMIT 1")

    plain_html_table = sf_instance.records_to_html_table(records, styled=False)
    styled_html_table = sf_instance.records_to_html_table(records, styled=True)

    assert isinstance(plain_html_table, str)
    assert "<table>" in plain_html_table
    assert "<tr>" in plain_html_table
    assert "<td>" in plain_html_table
    org_id = sf_instance.org_id
    assert f"<table><thead><tr><th>Id</th><th>NamespacePrefix</th></tr></thead><tbody><tr><td>{org_id}</td><td></td></tr></tbody></table>" == plain_html_table
    assert f'<table style="border-collapse:collapse;font-size:12px;line-height:1.2;margin:0;padding:0;width:auto;"><thead><tr><th style="border:1px solid #ccc;padding:2px 6px;background:#f8f8f8;font-weight:bold;">Id</th><th style="border:1px solid #ccc;padding:2px 6px;background:#f8f8f8;font-weight:bold;">NamespacePrefix</th></tr></thead><tbody><tr><td style="border:1px solid #ccc;padding:2px 6px;vertical-align:top;">{org_id}</td><td style="border:1px solid #ccc;padding:2px 6px;vertical-align:top;"></td></tr></tbody></table>' == styled_html_table

def test_html_table_with_nested_fields(sf_instance):
    results = sf_instance.query("SELECT Id,Name,CreatedBy.Name,CreatedBy.Profile.Name FROM User WHERE CreatedBy.Name <> null LIMIT 1")
    html = sf_instance.records_to_html_table(results)
    assert isinstance(html, str)
    assert "<table>" in html
    assert "<tr>" in html
    assert "<td>" in html
    assert "CreatedBy.Name" in html
    assert "CreatedBy.Profile.Name" in html
    assert "Id" in html

def test_html_table_with_mapped_headers(sf_instance):
    header_map = {
        "Id": "Id",
        "Name": "Name",
        "CreatedBy.Name": "Created By",
        "CreatedBy.Profile.Name": "Created By Profile"
    }
    results = sf_instance.query("SELECT Id,Name,CreatedBy.Name,CreatedBy.Profile.Name FROM User WHERE CreatedBy.Name <> null LIMIT 1")
    html = sf_instance.records_to_html_table(results, headers=header_map)
    assert isinstance(html, str)
    assert "<table>" in html
    assert "<tr>" in html
    assert "<td>" in html
    assert "Created By" in html
    assert "Created By Profile" in html
    assert "Id" in html
    assert "CreatedBy.Name" not in html
    assert "CreatedBy.Profile.Name" not in html

def test_html_table_with_no_records(sf_instance):
    html = sf_instance.records_to_html_table([])
    assert isinstance(html, str)
    assert "<table>" in html
    assert "<tr>" not in html
    assert "<td>" not in html
    assert "</table>" in html

def test_html_table_with_single_record(sf_instance):
    records = sf_instance.query("SELECT Id,NamespacePrefix FROM Organization LIMIT 1")
    html = sf_instance.records_to_html_table(records)
    assert isinstance(html, str)
    assert "<table>" in html
    assert "<tr>" in html
    assert "<td>" in html
    org_id = sf_instance.org_id
    assert f"<table><thead><tr><th>Id</th><th>NamespacePrefix</th></tr></thead><tbody><tr><td>{org_id}</td><td></td></tr></tbody></table>" == html

    styled_html = sf_instance.records_to_html_table(records, styled=True)
    assert isinstance(styled_html, str)
    assert "<table" in styled_html
    assert 'style="border-collapse:collapse;font-size:12px;line-height:1.2;margin:0;padding:0;width:auto;"' in styled_html
    assert "<tr" in styled_html
    assert "<td" in styled_html
    assert "</td>" in styled_html
    assert "</tr>" in styled_html
    assert "</table>" in styled_html

def test_html_with_nested_fields(sf_instance):
    results = sf_instance.query("SELECT Id,Name,CreatedBy.Name,CreatedBy.Profile.Name FROM User WHERE CreatedBy.Name <> null LIMIT 1")
    html = sf_instance.records_to_html_table(results)
    assert isinstance(html, str)
    assert "<table>" in html
    assert "<tr" in html
    assert "<td" in html
    assert "</tr>" in html
    assert "</td>" in html
    assert "CreatedBy.Name" in html
    assert "CreatedBy.Profile.Name" in html
    assert "Id" in html


def test_html_table_with_none_values(sf_instance):
    records = [
        {"Id": None, "Name": "Test"},
        {"Id": "123", "Name": None},
    ]
    html = sf_instance.records_to_html_table(records)
    assert "<td></td>" in html  # None should be rendered as empty
    assert "Test" in html
    assert "123" in html

def test_html_table_with_empty_dict(sf_instance):
    records = [{}]
    html = sf_instance.records_to_html_table(records)
    assert "<table>" in html
    assert "<tr>" not in html or "<td>" not in html

def test_html_table_with_mixed_types(sf_instance):
    records = [
        {"Id": 1, "Active": True, "Score": 99.5},
        {"Id": 2, "Active": False, "Score": None},
    ]
    html = sf_instance.records_to_html_table(records)
    assert "1" in html
    assert "True" in html or "False" in html
    assert "99.5" in html

def test_html_table_with_header_remapping_missing_keys(sf_instance):
    records = [
        {"Id": "abc", "Name": "Test", "Extra": "Value"}
    ]
    headers = {"Id": "Identifier", "Name": "Label"}  # 'Extra' not mapped
    html = sf_instance.records_to_html_table(records, headers=headers)
    assert "Identifier" in html
    assert "Label" in html
    assert "Extra" in html  # Should fall back to original key
