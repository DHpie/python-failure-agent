import json

import pytest

from tools import get_api_rules, get_execution_detail


def test_assertion_failure_keeps_expected_and_actual_separate():
    result = get_execution_detail("RUN-001")
    assert result["found"] is True
    assert result["evidence_id"] == "RUN-001"
    record = result["record"]
    assert record["operation_id"] == "calculateOrder"
    assert record["request"]["body"] == {"amount": 100, "discount": 120}
    assert record["expected"]["status"] == 400
    assert record["actual"] == {"status": 200, "body": {"payable": -20}}
    assert record["transport_error"] is None


def test_timeout_does_not_invent_http_response():
    record = get_execution_detail("RUN-002")["record"]
    assert record["failure_kind"] == "TRANSPORT_ERROR"
    assert record["actual"] is None
    assert record["transport_error"]["type"] == "CONNECT_TIMEOUT"


def test_missing_execution_does_not_supply_fake_evidence():
    result = get_execution_detail("RUN-404")
    assert result == {
        "found": False, "execution_id": "RUN-404", "evidence_id": None,
        "record": None, "message": "执行记录不存在",
    }


def test_rule_lookup_returns_only_requested_operation():
    result = get_api_rules("calculateOrder")
    assert result["found"] is True
    assert [rule["evidence_id"] for rule in result["rules"]] == ["RULE-001", "RULE-002"]
    assert all("订单金额" in rule["text"] or "INVALID_DISCOUNT" in rule["text"]
               for rule in result["rules"])


def test_registered_empty_rules_differ_from_unknown_operation():
    empty = get_api_rules("healthCheck")
    unknown = get_api_rules("unknownOperation")
    assert empty["found"] is True
    assert unknown["found"] is False
    assert empty["rules"] == unknown["rules"] == []
    assert empty["message"] != unknown["message"]


@pytest.mark.parametrize("tool", [get_execution_detail, get_api_rules])
@pytest.mark.parametrize("bad_id", ["", "   ", None, 123])
def test_invalid_id_is_a_caller_error(tool, bad_id):
    with pytest.raises(ValueError, match="非空字符串"):
        tool(bad_id)


def test_lookup_is_exact_and_does_not_silently_rewrite_id():
    assert get_execution_detail(" RUN-001")["found"] is False
    assert get_api_rules("CalculateOrder")["found"] is False


def test_returned_data_mutation_does_not_change_next_query():
    first = get_execution_detail("RUN-001")
    first["record"]["actual"]["status"] = 999
    assert get_execution_detail("RUN-001")["record"]["actual"]["status"] == 200
    rules = get_api_rules("calculateOrder")
    rules["rules"].clear()
    assert len(get_api_rules("calculateOrder")["rules"]) == 2


def test_default_paths_work_outside_project_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert get_execution_detail("RUN-001")["found"] is True
    assert get_api_rules("calculateOrder")["found"] is True


def test_explicit_data_directory_supports_isolated_fixtures(tmp_path):
    content = {"TEST-RUN": {"execution_id": "TEST-RUN", "operation_id": "testApi"}}
    (tmp_path / "executions.json").write_text(json.dumps(content), encoding="utf-8")
    assert get_execution_detail("TEST-RUN", data_dir=tmp_path)["record"] == content["TEST-RUN"]
    assert get_execution_detail("RUN-001", data_dir=tmp_path)["found"] is False


@pytest.mark.parametrize("tool,filename", [
    (get_execution_detail, "executions.json"), (get_api_rules, "rules.json")
])
def test_missing_file_is_not_disguised_as_missing_record(tool, filename, tmp_path):
    with pytest.raises(FileNotFoundError):
        tool("some-id", data_dir=tmp_path)


@pytest.mark.parametrize("content,expected_error", [
    ("{broken", json.JSONDecodeError), ("[]", ValueError)
])
@pytest.mark.parametrize("tool,filename", [
    (get_execution_detail, "executions.json"), (get_api_rules, "rules.json")
])
def test_bad_data_file_is_not_hidden(tool, filename, content, expected_error, tmp_path):
    (tmp_path / filename).write_text(content, encoding="utf-8")
    with pytest.raises(expected_error):
        tool("some-id", data_dir=tmp_path)


def test_tools_return_json_serializable_values():
    for result in [get_execution_detail("RUN-001"), get_api_rules("calculateOrder")]:
        assert json.loads(json.dumps(result, ensure_ascii=False)) == result
