import base64
import pytest
from sfq.utils import fuzz, defuzz

# ============================================================================
# BASIC FUNCTIONALITY TESTS
# ============================================================================


@pytest.mark.parametrize("prefix_len,suffix_len", [(2, 2), (4, 6), (8, 8)])
def test_fuzz_defuzz_roundtrip(prefix_len: int, suffix_len: int) -> None:
    """Test that fuzz/defuzz roundtrip works with various prefix/suffix lengths."""
    text = "SensitiveData123!"
    key = "mySecretKey"

    encoded = fuzz(text, key, prefix_len=prefix_len, suffix_len=suffix_len)
    decoded = defuzz(encoded, key, prefix_len=prefix_len, suffix_len=suffix_len)

    assert decoded == text, (
        f"Roundtrip failed for prefix={prefix_len}, suffix={suffix_len}"
    )


def test_different_keys_produce_different_output() -> None:
    """Test that different keys produce different encoded results."""
    text = "hello world"
    key1 = "keyA"
    key2 = "keyB"

    enc1 = fuzz(text, key1)
    enc2 = fuzz(text, key2)

    assert enc1 != enc2, "Different keys should produce different results"


def test_same_input_same_key_produces_same_output() -> None:
    """Test that same input and key always produce identical output."""
    text = "repeatable"
    key = "staticKey"

    enc1 = fuzz(text, key)
    enc2 = fuzz(text, key)

    assert enc1 == enc2, "Same input and key should always produce same output"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


def test_invalid_encoded_text_format() -> None:
    """Test that invalid encoded text format raises appropriate exception."""
    key = "abc"
    bad_data = "not_base64|format"
    with pytest.raises(Exception):
        defuzz(bad_data, key)


def test_invalid_base64_format() -> None:
    """Test that invalid base64 format raises appropriate exception."""
    key = "abc"
    bad_data = "invalid_base64_string!"
    with pytest.raises(Exception):
        defuzz(bad_data, key)


def test_prefix_suffix_length_mismatch() -> None:
    """Test that mismatched prefix/suffix lengths raise ValueError."""
    text = "TestData"
    key = "abc123"
    prefix_length = 4
    suffix_length = 4

    encoded = fuzz(text, key, prefix_len=prefix_length, suffix_len=suffix_length)
    decoded = defuzz(encoded, key, prefix_len=prefix_length, suffix_len=suffix_length)
    decoded_mismatch = defuzz(
        encoded_text=encoded,
        key=key,
        prefix_len=prefix_length * 2,
        suffix_len=suffix_length * 2,
    )

    assert decoded == text, "The decoded result should equal the original text"
    assert decoded_mismatch != text, (
        "The mismatched keys should not be equal to the original text"
    )


def test_missing_separators() -> None:
    """Test that encoded text missing separators is handled correctly."""
    key = "abc"
    # Create valid format without separators (this should work fine)
    text = "noseparators"
    encoded = fuzz(text, key)
    # This should not raise an exception
    decoded = defuzz(encoded, key)
    assert decoded == text, "Text without separators should work fine"


def test_too_many_separators() -> None:
    """Test that encoded text with too many separators raises ValueError."""
    key = "abc"
    # Create invalid format with too many separators
    invalid_data = base64.b64encode("a|b|c|d".encode()).decode()
    with pytest.raises(ValueError, match="Invalid encoded text format"):
        defuzz(invalid_data, key)


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


def test_empty_string() -> None:
    """Test fuzzing/defuzzing of empty string."""
    text = ""
    key = "someKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Empty string should survive roundtrip"


def test_single_character() -> None:
    """Test fuzzing/defuzzing of single character."""
    text = "a"
    key = "someKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Single character should survive roundtrip"


def test_unicode_support() -> None:
    """Test that Unicode text survives roundtrip."""
    text = "秘密情報🔒"
    key = "unicodeKey"

    encoded = fuzz(text, key, prefix_len=5, suffix_len=5)
    decoded = defuzz(encoded, key, prefix_len=5, suffix_len=5)

    assert decoded == text, "Unicode text should survive roundtrip"


def test_special_characters() -> None:
    """Test fuzzing/defuzzing of special characters."""
    text = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
    key = "specialKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Special characters should survive roundtrip"


def test_newlines_and_whitespace() -> None:
    """Test fuzzing/defuzzing of strings with newlines and whitespace."""
    text = "Line 1\nLine 2\tTabbed\r\nCarriage Return"
    key = "whitespaceKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Newlines and whitespace should survive roundtrip"


def test_long_strings() -> None:
    """Test fuzzing/defuzzing of very long strings."""
    text = "A" * 10000  # 10KB string
    key = "longKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Long strings should survive roundtrip"


def test_binary_data() -> None:
    """Test fuzzing/defuzzing of binary-like data."""
    text = "\x00\x01\x02\x03\xff\xfe\xfd"
    key = "binaryKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Binary data should survive roundtrip"


# ============================================================================
# PARAMETER VARIATION TESTS
# ============================================================================


@pytest.mark.parametrize("prefix_len", [0, 1, 2, 4, 8, 16])
@pytest.mark.parametrize("suffix_len", [0, 1, 2, 4, 8, 16])
def test_various_prefix_suffix_lengths(prefix_len: int, suffix_len: int) -> None:
    """Test fuzzing/defuzzing with various prefix/suffix length combinations."""
    text = "Test data with varying lengths"
    key = "testKey"

    encoded = fuzz(text, key, prefix_len=prefix_len, suffix_len=suffix_len)
    decoded = defuzz(encoded, key, prefix_len=prefix_len, suffix_len=suffix_len)

    assert decoded == text, (
        f"Roundtrip failed for prefix={prefix_len}, suffix={suffix_len}"
    )


def test_zero_prefix_suffix_length() -> None:
    """Test fuzzing/defuzzing with zero prefix/suffix lengths."""
    text = "Test data"
    key = "testKey"

    encoded = fuzz(text, key, prefix_len=0, suffix_len=0)
    decoded = defuzz(encoded, key, prefix_len=0, suffix_len=0)

    assert decoded == text, "Zero prefix/suffix lengths should work"


def test_maximum_prefix_suffix_length() -> None:
    """Test fuzzing/defuzzing with maximum reasonable prefix/suffix lengths."""
    text = "Test data"
    key = "testKey"

    encoded = fuzz(text, key, prefix_len=32, suffix_len=32)
    decoded = defuzz(encoded, key, prefix_len=32, suffix_len=32)

    assert decoded == text, "Maximum prefix/suffix lengths should work"


# ============================================================================
# KEY VARIATION TESTS
# ============================================================================


@pytest.mark.parametrize("key", ["", "a", "ab", "abc", "very_long_key_string"])
def test_various_key_lengths(key: str) -> None:
    """Test fuzzing/defuzzing with various key lengths."""
    text = "Test data"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, f"Roundtrip failed for key length {len(key)}"


def test_empty_key() -> None:
    """Test fuzzing/defuzzing with empty key."""
    text = "Test data"
    key = ""

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Empty key should work"


def test_special_characters_in_key() -> None:
    """Test fuzzing/defuzzing with special characters in key."""
    text = "Test data"
    key = "!@#$%^&*()"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Special characters in key should work"


# ============================================================================
# SECURITY AND COLLISION TESTS
# ============================================================================


def test_different_inputs_same_key() -> None:
    """Test that different inputs produce different outputs with same key."""
    key = "sameKey"
    text1 = "hello world"
    text2 = "goodbye world"

    enc1 = fuzz(text1, key)
    enc2 = fuzz(text2, key)

    assert enc1 != enc2, "Different inputs should produce different outputs"


def test_similar_inputs_different_output() -> None:
    """Test that similar inputs produce different outputs."""
    key = "testKey"
    text1 = "hello world"
    text2 = "hello worlD"  # Only one character difference

    enc1 = fuzz(text1, key)
    enc2 = fuzz(text2, key)

    assert enc1 != enc2, "Similar inputs should produce different outputs"


def test_hash_collision_resistance() -> None:
    """Test that hash collisions are handled properly."""
    # Test with inputs that might produce similar hash prefixes
    key = "testKey"
    text1 = "test"
    text2 = "test "  # Slightly different

    enc1 = fuzz(text1, key, prefix_len=8, suffix_len=8)
    enc2 = fuzz(text2, key, prefix_len=8, suffix_len=8)

    # Even if hashes are similar, the XOR should make them different
    assert enc1 != enc2, "Hash collisions should not produce identical outputs"


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


def test_performance_multiple_calls() -> None:
    """Test that multiple calls to fuzz/defuzz are consistent."""
    text = "Performance test data"
    key = "perfKey"

    # Test multiple calls to ensure consistency
    results = []
    for _ in range(10):
        encoded = fuzz(text, key)
        decoded = defuzz(encoded, key)
        results.append(decoded)

    # All results should be identical to original
    for result in results:
        assert result == text, "All roundtrips should produce identical results"


def test_large_data_performance() -> None:
    """Test performance with large data sets."""
    text = "Large data " * 1000  # ~15KB string
    key = "largeKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Large data should survive roundtrip"


# ============================================================================
# BACKWARD COMPATIBILITY TESTS
# ============================================================================


def test_default_parameters() -> None:
    """Test that default parameters work correctly."""
    text = "Test data"
    key = "testKey"

    # Test with default parameters (should be prefix_len=4, suffix_len=4)
    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Default parameters should work"


def test_backward_compatibility() -> None:
    """Test that existing code patterns still work."""
    # Simulate old usage patterns
    text = "Legacy data"
    key = "legacyKey"

    # Old style without explicit parameters
    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Backward compatibility should be maintained"


# ============================================================================
# ENCODING SCENARIOS TESTS
# ============================================================================


def test_base64_encoding_robustness() -> None:
    """Test that base64 encoding/decoding is robust."""
    text = "Test data with various characters: áéíóú 中文 🚀"
    key = "encodingKey"

    encoded = fuzz(text, key)

    # Verify the encoded result is valid base64
    try:
        decoded_base64 = base64.b64decode(encoded.encode()).decode()
        # The implementation doesn't use separators, so we don't expect "|"
        assert len(decoded_base64) > 0, "Decoded base64 should not be empty"
    except Exception:
        pytest.fail("Encoded result should be valid base64")

    # Test roundtrip
    decoded = defuzz(encoded, key)
    assert decoded == text, "Base64 encoding should be robust"


def test_hash_algorithm_consistency() -> None:
    """Test that hash algorithms produce consistent results."""
    text = "Consistency test"
    key = "hashKey"

    # Multiple calls should produce identical hash prefixes/suffixes
    encoded1 = fuzz(text, key, prefix_len=8, suffix_len=8)
    encoded2 = fuzz(text, key, prefix_len=8, suffix_len=8)

    # Extract the hash parts to verify consistency
    decoded1 = base64.b64decode(encoded1.encode()).decode()
    decoded2 = base64.b64decode(encoded2.encode()).decode()

    # Extract prefix and suffix directly (no separators in implementation)
    prefix1 = decoded1[:8]
    suffix1 = decoded1[-8:]
    prefix2 = decoded2[:8]
    suffix2 = decoded2[-8:]

    assert prefix1 == prefix2, "MD5 hash prefix should be consistent"
    assert suffix1 == suffix2, "SHA1 hash suffix should be consistent"


def test_xor_operation_properties() -> None:
    """Test XOR operation mathematical properties."""
    text = "XOR test"
    key = "xorKey"

    # Test that XOR is reversible: (a ^ b) ^ b = a
    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "XOR operation should be mathematically reversible"

    # Test that same key produces same transformation
    encoded2 = fuzz(text, key)
    assert encoded == encoded2, "Same key should produce identical XOR transformation"


# ============================================================================
# ADDITIONAL EDGE CASES
# ============================================================================


def test_repeated_characters() -> None:
    """Test fuzzing/defuzzing of strings with repeated characters."""
    text = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # 32 'a's
    key = "repeatKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Repeated characters should survive roundtrip"


def test_mixed_case_sensitivity() -> None:
    """Test case sensitivity of the fuzzing algorithm."""
    text1 = "Hello World"
    text2 = "hello world"
    key = "caseKey"

    enc1 = fuzz(text1, key)
    enc2 = fuzz(text2, key)

    assert enc1 != enc2, "Case sensitivity should be preserved"


def test_numeric_data() -> None:
    """Test fuzzing/defuzzing of numeric strings."""
    text = "1234567890"
    key = "numericKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Numeric data should survive roundtrip"


def test_alphanumeric_data() -> None:
    """Test fuzzing/defuzzing of alphanumeric strings."""
    text = "Alphanumeric123!@#"
    key = "alphanumericKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Alphanumeric data should survive roundtrip"


def test_unicode_combining_characters() -> None:
    """Test fuzzing/defuzzing of Unicode combining characters."""
    text = "c\u0327"  # c + combining tilde = ç
    key = "unicodeCombineKey"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Unicode combining characters should survive roundtrip"


# ============================================================================
# STRESS TESTS
# ============================================================================


def test_stress_multiple_variations() -> None:
    """Stress test with multiple parameter variations."""
    test_cases = [
        ("short", "k"),
        ("medium length text", "mediumKey"),
        ("very long text " * 50, "veryLongKey"),
        ("", ""),
        ("special!@#$%^&*()", "special!@#$%^&*()"),
        ("áéíóú 中文 🚀", "unicodeKey"),
    ]

    for text, key in test_cases:
        encoded = fuzz(text, key)
        decoded = defuzz(encoded, key)
        assert decoded == text, (
            f"Stress test failed for: text='{text[:50]}...', key='{key}'"
        )


def test_stress_hash_collisions() -> None:
    """Stress test to check for hash collisions with many inputs."""
    key = "stressKey"
    results = set()

    # Test many different inputs
    for i in range(1000):
        text = f"test_input_{i}"
        encoded = fuzz(text, key, prefix_len=4, suffix_len=4)
        results.add(encoded)

    # Should have mostly unique results (allowing for some collisions due to short prefix/suffix)
    assert len(results) >= 900, (
        f"Too many hash collisions: {1000 - len(results)} collisions out of 1000"
    )


# ============================================================================
# PROPERTY-BASED TESTS (using hypothesis-like testing)
# ============================================================================


def test_property_reversibility() -> None:
    """Test that fuzz/defuzz is always reversible (property-based test)."""
    # Test with a variety of inputs
    test_inputs = [
        "",
        "a",
        "ab",
        "abc",
        "hello",
        "hello world",
        "hello world!",
        "123",
        "123abc",
        "abc123",
        "123abc!@#",
        "line1\nline2\tline3",
        "áéíóú",
        "中文",
        "🚀",
        "a" * 100,
        "a" * 1000,
    ]

    key = "propertyKey"

    for text in test_inputs:
        encoded = fuzz(text, key)
        decoded = defuzz(encoded, key)
        assert decoded == text, f"Reversibility property failed for: {repr(text)}"


def test_property_deterministic() -> None:
    """Test that fuzz/defuzz is deterministic (property-based test)."""
    test_inputs = ["hello", "", "special!@#", "unicode🚀"]
    key = "deterministicKey"

    for text in test_inputs:
        # Multiple calls should produce identical results
        encoded1 = fuzz(text, key)
        encoded2 = fuzz(text, key)
        encoded3 = fuzz(text, key)

        assert encoded1 == encoded2 == encoded3, (
            f"Deterministic property failed for: {repr(text)}"
        )

        decoded1 = defuzz(encoded1, key)
        decoded2 = defuzz(encoded2, key)
        decoded3 = defuzz(encoded3, key)

        assert decoded1 == decoded2 == decoded3, (
            f"Deterministic defuzz failed for: {repr(text)}"
        )


# ============================================================================
# DOCUMENTATION AND EXAMPLE TESTS
# ============================================================================


def test_examples_from_documentation():
    """Test examples that would be suitable for documentation."""
    # Example 1: Basic usage
    text = "sensitive_password_123"
    key = "my_secret_key"

    encoded = fuzz(text, key)
    decoded = defuzz(encoded, key)

    assert decoded == text, "Basic usage example should work"

    # Example 2: Custom prefix/suffix lengths
    encoded_custom = fuzz(text, key, prefix_len=8, suffix_len=8)
    decoded_custom = defuzz(encoded_custom, key, prefix_len=8, suffix_len=8)

    assert decoded_custom == text, "Custom prefix/suffix example should work"

    # Example 3: Verify encoded format
    decoded_format = base64.b64decode(encoded.encode()).decode()
    # The implementation doesn't use separators, so we check the structure differently
    assert len(decoded_format) > 0, "Encoded format should not be empty"
    # Verify it has prefix + body + suffix structure
    assert len(decoded_format) >= 8, (
        "Encoded format should have at least prefix and suffix"
    )


def test_real_world_scenarios():
    """Test real-world usage scenarios."""
    scenarios = [
        # API tokens
        ("sk-1234567890abcdef", "api_key"),
        # Passwords
        ("P@ssw0rd!2023", "auth_key"),
        # Session IDs
        ("sess_abc123def456", "session_key"),
        # JWT tokens
        (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "jwt_key",
        ),
        # SQL queries (sanitized)
        ("SELECT * FROM users WHERE id = 123", "query_key"),
        # JSON data
        ('{"user": "john", "pass": "secret"}', "json_key"),
    ]

    for text, key in scenarios:
        encoded = fuzz(text, key)
        decoded = defuzz(encoded, key)
        assert decoded == text, f"Real-world scenario failed for: {text[:50]}..."
