"""仅用于离线教学和测试；预设响应不是LLM推理。"""

from typing import Any

from pydantic import Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    responses: list[AIMessage]
    calls: int = 0
    received: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-offline-not-a-real-llm"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs: Any):
        # 假模型不向服务发送工具Schema；返回预设的tool_calls。
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.received.append(list(messages))
        if self.calls >= len(self.responses):
            raise RuntimeError("离线响应已耗尽；请补充脚本或检查结束条件")
        response = self.responses[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def request_tool(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def example_model(execution_id: str) -> ScriptedChatModel:
    responses = [request_tool("get_execution_detail", {"execution_id": execution_id}, "call-execution")]
    if execution_id == "RUN-001":
        responses += [
            request_tool("get_api_rules", {"operation_id": "calculateOrder"}, "call-rules"),
            AIMessage(content="事实：RUN-001预期400，实际200且payable=-20。依据RULE-001/002，优惠不应超过金额。候选原因：上限校验可能失效。风险：可能计算出负数应付金额。缺少服务端日志和实现信息，不能确认代码根因。建议检查优惠上限校验。"),
        ]
    elif execution_id == "RUN-002":
        responses += [AIMessage(content="RUN-002连接超时，没有HTTP响应；无需查询优惠业务规则。现有证据不能确认服务端根因，建议检查服务地址、网络和服务运行状态。")]
    elif execution_id == "RUN-404":
        responses += [AIMessage(content="工具返回RUN-404不存在，没有执行证据，无法分析原因。请核对执行ID。")]
    else:
        responses += [AIMessage(content="本离线脚本仅演示RUN-001、RUN-002及缺失记录；请核对工具返回的数据，其他ID需使用真实模型或补充脚本。")]
    return ScriptedChatModel(responses=responses)
