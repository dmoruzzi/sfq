import pytest

from sfq.utils import dicts_to_html_table


def test_typecastable_keys():
    # int key
    data_int = [{1: "one"}]
    with open(
        "./tests/html/test_typecastable_keys_int.html", "r", encoding="utf-8"
    ) as f:
        expected = f.read()
    with open(
        "./tests/html/test_typecastable_keys_int_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data_int) == expected
    assert dicts_to_html_table(data_int, styled=True) == expected_styled

    # float key
    data_float = [{2.5: "two point five"}]
    with open(
        "./tests/html/test_typecastable_keys_float.html", "r", encoding="utf-8"
    ) as f:
        expected = f.read()
    with open(
        "./tests/html/test_typecastable_keys_float_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data_float) == expected
    assert dicts_to_html_table(data_float, styled=True) == expected_styled

    # bool key
    data_bool = [{True: "truthy"}, {False: "falsey"}]
    with open(
        "./tests/html/test_typecastable_keys_bool.html", "r", encoding="utf-8"
    ) as f:
        expected = f.read()
    with open(
        "./tests/html/test_typecastable_keys_bool_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data_bool) == expected
    assert dicts_to_html_table(data_bool, styled=True) == expected_styled


def test_empty_list():
    with open("./tests/html/test_empty_list.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open("./tests/html/test_empty_list_styled.html", "r", encoding="utf-8") as f:
        expected_styled = f.read()
    assert dicts_to_html_table([]) == expected
    assert dicts_to_html_table([], styled=True) == expected_styled


def test_single_flat_dict():
    data = [{"a": "b", "c": "d"}]

    with open("./tests/html/test_single_flat_dict.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open(
        "./tests/html/test_single_flat_dict_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_multiple_dicts():
    data = [{"x": "y"}, {"z": "w"}]

    with open("./tests/html/test_multiple_dicts.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open(
        "./tests/html/test_multiple_dicts_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_none_value():
    data = [{"foo": None}]

    with open("./tests/html/test_none_value.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open("./tests/html/test_none_value_styled.html", "r", encoding="utf-8") as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_int_float_bool():
    data = [{"i": 1, "f": 2.5, "b": True}]

    with open("./tests/html/test_int_float_bool.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open(
        "./tests/html/test_int_float_bool_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_list_value():
    data = [{"hello": ["bob", "sally"]}]
    with open("./tests/html/test_list_value.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open("./tests/html/test_list_value_styled.html", "r", encoding="utf-8") as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_nested_dict():
    data = [{"outer": {"inner": "value"}}]
    data = [{"outer": {"inner": "value"}}]
    with open("./tests/html/test_nested_dict.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open("./tests/html/test_nested_dict_styled.html", "r", encoding="utf-8") as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_complex_nested():
    data = [{"a": [1, {"b": [2, 3]}, None]}]
    data = [{"a": [1, {"b": [2, 3]}, None]}]
    with open("./tests/html/test_complex_nested.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open(
        "./tests/html/test_complex_nested_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_invalid_input_type():
    # Not printing for error cases
    with pytest.raises(ValueError):
        dicts_to_html_table("not a list")
    with pytest.raises(ValueError):
        dicts_to_html_table(["not a dict"])
    # Only non-typecastable keys should raise ValueError
    with pytest.raises(ValueError):
        dicts_to_html_table([{(1, 2): "value"}])
    with pytest.raises(ValueError):
        dicts_to_html_table([{object(): "value"}])
    # Also test styled param does not affect error
    with pytest.raises(ValueError):
        dicts_to_html_table("not a list", styled=True)
    with pytest.raises(ValueError):
        dicts_to_html_table(["not a dict"], styled=True)
    with pytest.raises(ValueError):
        dicts_to_html_table([{(1, 2): "value"}], styled=True)
    with pytest.raises(ValueError):
        dicts_to_html_table([{object(): "value"}], styled=True)


def test_other_types():
    class Custom:
        def __str__(self):
            return "custom_str"

    data = [{"custom": Custom()}]
    with open("./tests/html/test_other_types.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open("./tests/html/test_other_types_styled.html", "r", encoding="utf-8") as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled


def test_sample_report():
    data = [
        {"name": "Sample Report", "date": "2023-01-01", "status": "Completed"},
        {"name": "Sample Report 2", "date": "2023-01-02", "status": "In Progress"},
        {"name": "Sample Report 3", "date": "2023-01-03", "status": "Not Started"},
    ]
    expected = "<table><tbody><tr><td>name</td><td>Sample Report</td></tr><tr><td>date</td><td>2023-01-01</td></tr><tr><td>status</td><td>Completed</td></tr></tbody></table>"
    with open("./tests/html/test_sample_report.html", "r", encoding="utf-8") as f:
        expected = f.read()
    with open(
        "./tests/html/test_sample_report_styled.html", "r", encoding="utf-8"
    ) as f:
        expected_styled = f.read()
    assert dicts_to_html_table(data) == expected
    assert dicts_to_html_table(data, styled=True) == expected_styled
