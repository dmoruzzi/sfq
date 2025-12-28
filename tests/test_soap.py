"""
Unit tests for the SOAP client module.
"""

import xml.etree.ElementTree as ET
from unittest.mock import Mock

import pytest

from sfq.soap import SOAPClient


class TestSOAPClient:
    """Test cases for SOAPClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_http_client = Mock()
        self.soap_client = SOAPClient(self.mock_http_client, "v65.0")

    def test_init(self):
        """Test SOAPClient initialization."""
        assert self.soap_client.http_client == self.mock_http_client
        assert self.soap_client.api_version == "v65.0"

    def test_generate_soap_envelope_enterprise(self):
        """Test SOAP envelope generation for Enterprise API."""
        header = "<soapenv:Header><SessionHeader><sessionId>test_token</sessionId></SessionHeader></soapenv:Header>"
        body = "<soapenv:Body><create><sObjects>test</sObjects></create></soapenv:Body>"

        envelope = self.soap_client.generate_soap_envelope(header, body, "enterprise")

        assert '<?xml version="1.0" encoding="UTF-8"?>' in envelope
        assert 'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"' in envelope
        assert 'xmlns="urn:enterprise.soap.sforce.com"' in envelope
        assert 'xmlns:sf="urn:sobject.enterprise.soap.sforce.com"' in envelope
        assert header in envelope
        assert body in envelope
        assert envelope.endswith("</soapenv:Envelope>")

    def test_generate_soap_envelope_tooling(self):
        """Test SOAP envelope generation for Tooling API."""
        header = "<soapenv:Header><SessionHeader><sessionId>test_token</sessionId></SessionHeader></soapenv:Header>"
        body = "<soapenv:Body><create><sObjects>test</sObjects></create></soapenv:Body>"

        envelope = self.soap_client.generate_soap_envelope(header, body, "tooling")

        assert '<?xml version="1.0" encoding="UTF-8"?>' in envelope
        assert 'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"' in envelope
        assert 'xmlns="urn:tooling.soap.sforce.com"' in envelope
        assert 'xmlns:mns="urn:metadata.tooling.soap.sforce.com"' in envelope
        assert 'xmlns:sf="urn:sobject.tooling.soap.sforce.com"' in envelope
        assert header in envelope
        assert body in envelope
        assert envelope.endswith("</soapenv:Envelope>")

    def test_generate_soap_envelope_invalid_type(self):
        """Test SOAP envelope generation with invalid API type."""
        header = "<soapenv:Header></soapenv:Header>"
        body = "<soapenv:Body></soapenv:Body>"

        with pytest.raises(ValueError, match="Unsupported API type: invalid"):
            self.soap_client.generate_soap_envelope(header, body, "invalid")

    def test_generate_soap_header(self):
        """Test SOAP header generation."""
        session_id = "test_session_token_123"

        header = self.soap_client.generate_soap_header(session_id)

        expected = "<soapenv:Header><SessionHeader><sessionId>test_session_token_123</sessionId></SessionHeader></soapenv:Header>"
        assert header == expected

    def test_generate_soap_body_single_record(self):
        """Test SOAP body generation with single record."""
        sobject = "Account"
        method = "create"
        data = {"Name": "Test Account", "Type": "Customer"}

        body = self.soap_client.generate_soap_body(sobject, method, data)

        expected = (
            "<soapenv:Body><create>"
            '<sObjects xsi:type="Account">'
            "<Name>Test Account</Name>"
            "<Type>Customer</Type>"
            "</sObjects>"
            "</create></soapenv:Body>"
        )
        assert body == expected

    def test_generate_soap_body_multiple_records(self):
        """Test SOAP body generation with multiple records."""
        sobject = "Contact"
        method = "create"
        data = [
            {"FirstName": "John", "LastName": "Doe"},
            {"FirstName": "Jane", "LastName": "Smith"},
        ]

        body = self.soap_client.generate_soap_body(sobject, method, data)

        expected = (
            "<soapenv:Body><create>"
            '<sObjects xsi:type="Contact">'
            "<FirstName>John</FirstName>"
            "<LastName>Doe</LastName>"
            "</sObjects>"
            '<sObjects xsi:type="Contact">'
            "<FirstName>Jane</FirstName>"
            "<LastName>Smith</LastName>"
            "</sObjects>"
            "</create></soapenv:Body>"
        )
        assert body == expected

    def test_extract_soap_result_fields_single_result(self):
        """Test extracting fields from SOAP response with single result."""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Body>
                <createResponse>
                    <result>
                        <id>001XX000003DHP0</id>
                        <success>true</success>
                    </result>
                </createResponse>
            </soapenv:Body>
        </soapenv:Envelope>"""

        result = self.soap_client.extract_soap_result_fields(xml_response)

        expected = {"id": "001XX000003DHP0", "success": "true"}
        assert result == expected

    def test_extract_soap_result_fields_multiple_results(self):
        """Test extracting fields from SOAP response with multiple results."""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Body>
                <createResponse>
                    <result>
                        <id>001XX000003DHP0</id>
                        <success>true</success>
                    </result>
                    <result>
                        <id>001XX000003DHP1</id>
                        <success>false</success>
                    </result>
                </createResponse>
            </soapenv:Body>
        </soapenv:Envelope>"""

        result = self.soap_client.extract_soap_result_fields(xml_response)

        expected = [
            {"id": "001XX000003DHP0", "success": "true"},
            {"id": "001XX000003DHP1", "success": "false"},
        ]
        assert result == expected

    def test_extract_soap_result_fields_with_namespaces(self):
        """Test extracting fields from SOAP response with XML namespaces."""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" 
                         xmlns:sf="urn:sobject.enterprise.soap.sforce.com">
            <soapenv:Body>
                <sf:createResponse>
                    <sf:result>
                        <sf:id>001XX000003DHP0</sf:id>
                        <sf:success>true</sf:success>
                    </sf:result>
                </sf:createResponse>
            </soapenv:Body>
        </soapenv:Envelope>"""

        result = self.soap_client.extract_soap_result_fields(xml_response)

        expected = {"id": "001XX000003DHP0", "success": "true"}
        assert result == expected

    def test_extract_soap_result_fields_with_nested_elements(self):
        """Test extracting fields from SOAP response with nested elements."""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Body>
                <createResponse>
                    <result>
                        <id>001XX000003DHP1</id>
                        <success>false</success>
                        <errors>
                            <message>Required field missing</message>
                        </errors>
                    </result>
                </createResponse>
            </soapenv:Body>
        </soapenv:Envelope>"""

        result = self.soap_client.extract_soap_result_fields(xml_response)

        # The current implementation only extracts direct child text content
        # Nested elements like <errors> are included but only their text content
        expected = {
            "id": "001XX000003DHP1",
            "success": "false",
            "errors": "\n                            ",
        }
        assert result == expected

    def test_extract_soap_result_fields_no_results(self):
        """Test extracting fields from SOAP response with no results."""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Body>
                <createResponse>
                </createResponse>
            </soapenv:Body>
        </soapenv:Envelope>"""

        result = self.soap_client.extract_soap_result_fields(xml_response)

        assert result is None

    def test_extract_soap_result_fields_invalid_xml(self):
        """Test extracting fields from invalid XML."""
        invalid_xml = "<invalid>xml<without>proper</closing>"

        result = self.soap_client.extract_soap_result_fields(invalid_xml)

        assert result is None

    def test_xml_to_dict_simple(self):
        """Test XML to dictionary conversion with simple structure."""
        xml_string = """<root>
            <name>Test</name>
            <value>123</value>
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {"name": "Test", "value": "123"}
        assert result == expected

    def test_xml_to_dict_nested(self):
        """Test XML to dictionary conversion with nested structure."""
        xml_string = """<root>
            <person>
                <name>John Doe</name>
                <age>30</age>
                <address>
                    <street>123 Main St</street>
                    <city>Anytown</city>
                </address>
            </person>
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {
            "person": {
                "name": "John Doe",
                "age": "30",
                "address": {"street": "123 Main St", "city": "Anytown"},
            }
        }
        assert result == expected

    def test_xml_to_dict_multiple_same_tags(self):
        """Test XML to dictionary conversion with multiple elements of same tag."""
        xml_string = """<root>
            <item>First</item>
            <item>Second</item>
            <item>Third</item>
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {"item": ["First", "Second", "Third"]}
        assert result == expected

    def test_xml_to_dict_empty_elements(self):
        """Test XML to dictionary conversion with empty elements."""
        xml_string = """<root>
            <empty></empty>
            <null/>
            <text>content</text>
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {"empty": "", "null": "", "text": "content"}
        assert result == expected

    def test_xml_to_dict_invalid_xml(self):
        """Test XML to dictionary conversion with invalid XML."""
        invalid_xml = "<invalid>xml<without>proper</closing>"

        result = self.soap_client.xml_to_dict(invalid_xml)

        assert result is None

    def test_xml_element_to_dict_text_only(self):
        """Test XML element to dict conversion with text-only element."""
        element = ET.fromstring("<test>simple text</test>")

        result = self.soap_client._xml_element_to_dict(element)

        assert result == "simple text"

    def test_xml_element_to_dict_empty_element(self):
        """Test XML element to dict conversion with empty element."""
        element = ET.fromstring("<test></test>")

        result = self.soap_client._xml_element_to_dict(element)

        assert result == ""

    def test_xml_to_dict_with_attributes(self):
        """Test XML to dictionary conversion with attributes (attributes are ignored)."""
        xml_string = """<root id="123" type="test">
            <name>Test</name>
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        # Current implementation ignores attributes, only processes child elements and text
        expected = {"name": "Test"}
        assert result == expected

    def test_xml_to_dict_mixed_content(self):
        """Test XML to dictionary conversion with mixed text and element content."""
        xml_string = """<root>
            Some text
            <child>Child content</child>
            More text
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {"child": "Child content"}
        assert result == expected

    def test_xml_to_dict_cdata_section(self):
        """Test XML to dictionary conversion with CDATA sections."""
        xml_string = """<root>
            <description><![CDATA[This is <b>bold</b> text]]></description>
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {"description": "This is <b>bold</b> text"}
        assert result == expected

    def test_xml_to_dict_whitespace_handling(self):
        """Test XML to dictionary conversion with various whitespace scenarios."""
        xml_string = """<root>
            <trimmed>  content with spaces  </trimmed>
            <empty_with_spaces>   </empty_with_spaces>
            <newlines>
                content
                with
                newlines
            </newlines>
        </root>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {
            "trimmed": "  content with spaces  ",
            "empty_with_spaces": "   ",
            "newlines": "\n                content\n                with\n                newlines\n            ",
        }
        assert result == expected

    def test_xml_to_dict_deeply_nested(self):
        """Test XML to dictionary conversion with deeply nested structure."""
        xml_string = """<level1>
            <level2>
                <level3>
                    <level4>
                        <level5>Deep content</level5>
                    </level4>
                </level3>
            </level2>
        </level1>"""

        result = self.soap_client.xml_to_dict(xml_string)

        expected = {"level2": {"level3": {"level4": {"level5": "Deep content"}}}}
        assert result == expected
