# MDAPI Guide

sfq supports retrieving metadata from Salesforce using the Metadata API (MDAPI). This is useful for extracting components like custom objects, Apex classes, and more.

## Overview

The `mdapi_retrieve` method retrieves metadata components as a ZIP file containing the component definitions.

## Basic Usage

### Retrieve by Type

Retrieve all components of specific types:

```python
from sfq import SFAuth

sf = SFAuth(
    instance_url="https://your-org.my.salesforce.com",
    client_id="PlatformCLI",
    client_secret="",
    refresh_token="your-refresh-token"
)

# Retrieve all CustomObjects and ApexClasses
zip_buffer = sf.mdapi_retrieve(["CustomObject", "ApexClass"])
```

### Retrieve Specific Metadata Files

Retrieve specific components by name:

```python
package = {
    "CustomObject": ["MyCustomObject__c"],
    "ApexClass": ["MyClass", "AnotherClass"],
    "ApexTrigger": ["AccountTrigger"]
}

data = sf.mdapi_retrieve(package)
```

## Notes

1. **API Limits**: Each retrieve counts against Metadata API limits
2. **Async Operation**: Retrieves are asynchronous from Salesforce; sfq handles polling automatically
3. **Response Format**: Results are returned as a dict of file_name with the key and the content as the value.
