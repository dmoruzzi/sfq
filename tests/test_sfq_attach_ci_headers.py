#!/usr/bin/env python3
"""
Test to verify that the SFQ_ATTACH_CI fix works correctly.
"""

import os
import sys
sys.path.insert(0, 'src')

from sfq.ci_headers import CIHeaders

def test_sfq_attach_ci_false():
    """Test that when SFQ_ATTACH_CI is false, no headers are returned."""
    # Set SFQ_ATTACH_CI to false
    os.environ['SFQ_ATTACH_CI'] = "false"
    
    # Set SFQ_HEADERS to some value
    os.environ['SFQ_HEADERS'] = "custom_key:custom_value|test_header:test_value"
    
    # Test get_ci_headers
    ci_headers = CIHeaders.get_ci_headers()
    print(f"CI Headers: {ci_headers}")
    assert ci_headers == {}, f"Expected empty dict, got {ci_headers}"
    
    # Test get_addinfo_headers
    addinfo_headers = CIHeaders.get_addinfo_headers()
    print(f"AddInfo Headers: {addinfo_headers}")
    assert addinfo_headers == {}, f"Expected empty dict, got {addinfo_headers}"
    
    print("Test passed: SFQ_ATTACH_CI=false correctly prevents header attachment")

def test_sfq_attach_ci_true():
    """Test that when SFQ_ATTACH_CI is true, headers are returned."""
    # Set SFQ_ATTACH_CI to true
    os.environ['SFQ_ATTACH_CI'] = "true"
    
    # Set SFQ_HEADERS to some value
    os.environ['SFQ_HEADERS'] = "custom_key:custom_value|test_header:test_value"
    
    # Test get_addinfo_headers
    addinfo_headers = CIHeaders.get_addinfo_headers()
    print(f"AddInfo Headers: {addinfo_headers}")
    
    expected_headers = {
        'x-sfdc-addinfo-custom_key': 'custom_value',
        'x-sfdc-addinfo-test_header': 'test_value'
    }
    assert addinfo_headers == expected_headers, f"Expected {expected_headers}, got {addinfo_headers}"
    
    print("Test passed: SFQ_ATTACH_CI=true correctly allows header attachment")

def test_sfq_attach_ci_unset():
    """Test that when SFQ_ATTACH_CI is unset, headers are returned."""
    # Remove SFQ_ATTACH_CI
    os.environ.pop('SFQ_ATTACH_CI', None)
    
    # Set SFQ_HEADERS to some value
    os.environ['SFQ_HEADERS'] = "custom_key:custom_value|test_header:test_value"
    
    # Test get_addinfo_headers
    addinfo_headers = CIHeaders.get_addinfo_headers()
    print(f"AddInfo Headers: {addinfo_headers}")
    
    expected_headers = {
        'x-sfdc-addinfo-custom_key': 'custom_value',
        'x-sfdc-addinfo-test_header': 'test_value'
    }
    assert addinfo_headers == expected_headers, f"Expected {expected_headers}, got {addinfo_headers}"
    
    print("Test passed: SFQ_ATTACH_CI unset correctly allows header attachment")

if __name__ == "__main__":
    print("Testing SFQ_ATTACH_CI fix...")
    
    try:
        test_sfq_attach_ci_false()
        test_sfq_attach_ci_true()
        test_sfq_attach_ci_unset()
        print("\nAll tests passed!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)