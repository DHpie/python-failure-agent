import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

from agent_demo import run_agent
from agent_tools import make_tools
from scripted_model import ScriptedChatModel, example_model, request_tool


def test_tool_schemas_expose_business_id_only():
    execution, rules = make_tools()
    assert execution.name == "get_execution_detail"
    assert set(execution.args) == {"execution_id"}
    assert set(rules.args) == {"operation_id"}


def test_full_loop_executes_tools_and_returns_their_results_to_model():
    model = example_model("RUN-001")
    observed = []
    result = run_agent(model, "RUN-001", on_message=observed.append)
    assert [message.type for message in result["messages"]] == ["human", "ai", "tool", "ai", "tool", "ai"]
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages[0].tool_call_id == "call-execution"
    assert json.loads(tool_messages[0].content)["record"]["actual"]["status"] == 200
    assert json.loads(tool_messages[1].content)["rules"][0]["evidence_id"] == "RULE-001"
    assert tool_messages[0] in model.received[1]
    assert tool_messages[1] in model.received[2]
    assert model.received[0][0].type == "system"
    assert model.calls == 3
    assert len(observed) == 6
    assert not result["messages"][-1].tool_calls


def test_timeout_path_can_finish_without_querying_business_rules():
    model = example_model("RUN-002")
    messages = run_agent(model, "RUN-002")["messages"]
    tools = [m for m in messages if m.type == "tool"]
    assert [m.name for m in tools] == ["get_execution_detail"]
    assert json.loads(tools[0].content)["record"]["actual"] is None
    assert model.calls == 2


def test_missing_record_is_a_real_tool_result_not_prechecked_by_program():
    model = example_model("RUN-404")
    messages = run_agent(model, "RUN-404")["messages"]
    result = json.loads(next(m.content for m in messages if m.type == "tool"))
    assert result["found"] is False and result["evidence_id"] is None
    assert model.calls == 2


def test_no_tool_calls_ends_normally_but_does_not_prove_quality():
    model = ScriptedChatModel(responses=[AIMessage(content="我没有读取证据。")])
    messages = run_agent(model, "RUN-001")["messages"]
    assert model.calls == 1
    assert len(messages) == 2  # 教学：结束不等于遵守了先读证据的要求。


def test_missing_evidence_file_becomes_error_tool_message(tmp_path):
    model = ScriptedChatModel(responses=[
        request_tool("get_execution_detail", {"execution_id": "RUN-001"}, "bad-file"),
        AIMessage(content="证据读取失败，无法判断。"),
    ])
    messages = run_agent(model, "RUN-001", data_dir=tmp_path)["messages"]
    error = next(m for m in messages if m.type == "tool")
    assert error.status == "error"
    assert json.loads(error.content)["error"] == "EVIDENCE_READ_ERROR"
    assert error in model.received[1]


def test_unknown_tool_is_rejected_and_error_returned_to_model():
    model = ScriptedChatModel(responses=[request_tool("delete_data", {}, "unknown"), AIMessage(content="工具不可用。")])
    messages = run_agent(model, "RUN-001")["messages"]
    error = next(m for m in messages if m.type == "tool")
    assert error.status == "error"
    assert "delete_data" in error.content


def test_invalid_tool_arguments_return_validation_error():
    model = ScriptedChatModel(responses=[request_tool("get_execution_detail", {}, "bad-args"), AIMessage(content="参数有误。")])
    messages = run_agent(model, "RUN-001")["messages"]
    error = next(m for m in messages if m.type == "tool")
    assert error.status == "error"


def test_model_call_budget_aborts_loop():
    model = ScriptedChatModel(responses=[request_tool("get_execution_detail", {"execution_id": "RUN-001"}, f"call-{i}") for i in range(5)])
    with pytest.raises(ModelCallLimitExceededError):
        run_agent(model, "RUN-001", max_model_calls=2, max_tool_calls=5)
    assert model.calls == 2


def test_tool_budget_blocks_second_tool_execution():
    model = example_model("RUN-001")
    with pytest.raises(ToolCallLimitExceededError):
        run_agent(model, "RUN-001", max_tool_calls=1)
    assert model.calls == 2


def test_model_failure_is_propagated_not_replaced_by_analysis():
    model = ScriptedChatModel(responses=[])
    with pytest.raises(RuntimeError, match="耗尽"):
        run_agent(model, "RUN-001")
