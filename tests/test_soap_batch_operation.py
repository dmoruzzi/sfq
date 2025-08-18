import pytest
from sfq.crud import CRUDClient
from sfq.soap import SOAPClient

class DummyHTTPClient:
    def __init__(self):
        self.auth_manager = type('Auth', (), {'access_token': 'dummy_token'})()
    def get_common_headers(self):
        return {}
    def send_request(self, method, endpoint, headers, body):
        # Simulate a successful SOAP response for create/delete/update
        if '<create>' in body:
            return 200, '<result><id>001xx000003DGbEAAW</id><success>true</success></result>'
        elif '<delete>' in body:
            return 200, '<result><id>001xx000003DGbEAAW</id><success>true</success></result>'
        elif '<update>' in body:
            return 200, '<result><id>001xx000003DGbEAAW</id><success>true</success></result>'
        return 500, '<faultstring>Error</faultstring>'

@pytest.fixture
def crud_client():
    http_client = DummyHTTPClient()
    soap_client = SOAPClient(http_client)
    return CRUDClient(http_client, soap_client)

def test_soap_batch_create(crud_client):
    data = [{"Name": "Test Account"}]
    result = crud_client._soap_batch_operation("Account", data, "create")
    assert result is not None
    assert result[0]["success"] == "true"

def test_soap_batch_delete(crud_client):
    ids = ["001xx000003DGbEAAW"]
    result = crud_client._soap_batch_operation("Account", ids, "delete")
    assert result is not None
    assert result[0]["success"] == "true"

def test_soap_batch_update(crud_client):
    data = [{"Id": "001xx000003DGbEAAW", "Name": "Updated Account"}]
    result = crud_client._soap_batch_operation("Account", data, "update")
    assert result is not None
    assert result[0]["success"] == "true"
