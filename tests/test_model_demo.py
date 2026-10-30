import json
from unittest.mock import Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from model_config import ModelSettings, build_model
from model_demo import build_messages, invoke_once


def test_messages_include_real_evidence_in_separate_roles():
    messages = build_messages("RUN-001")
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    data = json.loads(messages[1].content.split("\n", 1)[1])
    assert data["execution"]["record"]["actual"]["body"] == {"payable": -20}
    assert [rule["evidence_id"] for rule in data["api_rules"]["rules"]] == ["RULE-001", "RULE-002"]


def test_timeout_evidence_does_not_get_an_http_response():
    data = json.loads(build_messages("RUN-002")[1].content.split("\n", 1)[1])
    assert data["execution"]["record"]["actual"] is None
    assert "CONNECT_TIMEOUT" in json.dumps(data)


def test_unknown_record_stops_before_model_call():
    model = Mock(spec=BaseChatModel)
    with pytest.raises(ValueError, match="不发送模型请求"):
        invoke_once(model, build_messages("RUN-404"))
    model.invoke.assert_not_called()


def test_model_called_once_with_messages_and_response_preserved():
    model = Mock(spec=BaseChatModel)
    expected = AIMessage(content="优惠校验可能失效，证据RUN-001和RULE-001。")
    model.invoke.return_value = expected
    messages = build_messages("RUN-001")
    assert invoke_once(model, messages) is expected
    model.invoke.assert_called_once_with(messages)


def test_model_error_is_not_replaced_with_fake_analysis():
    model = Mock(spec=BaseChatModel)
    model.invoke.side_effect = TimeoutError("模拟超时")
    with pytest.raises(TimeoutError):
        invoke_once(model, build_messages("RUN-001"))
    assert model.invoke.call_count == 1


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.setattr("model_config.load_dotenv", lambda *args, **kwargs: None)
    for name in ["LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "LLM_TIMEOUT_SECONDS"]:
        monkeypatch.delenv(name, raising=False)


def test_missing_config_fails_before_request(clean_env):
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        ModelSettings.from_env()


@pytest.mark.parametrize("timeout", ["nan", "inf", "0", "301", "abc"])
def test_invalid_timeout_is_rejected(clean_env, monkeypatch, timeout):
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "dummy-not-real")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", timeout)
    with pytest.raises(ValueError, match="LLM_TIMEOUT_SECONDS"):
        ModelSettings.from_env()


def test_model_constructor_receives_configuration_without_request(clean_env, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "dummy-not-real")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.invalid/v1")
    settings = ModelSettings.from_env()
    constructor = Mock()
    monkeypatch.setattr("model_config.ChatOpenAI", constructor)
    assert build_model(settings) is constructor.return_value
    constructor.assert_called_once_with(model="test-model", api_key="dummy-not-real",
        base_url="https://provider.invalid/v1", timeout=60.0, max_retries=0,
        use_responses_api=False)
