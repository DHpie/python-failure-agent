"""用窄包装将普通函数注册为模型可见工具，隐藏data_dir参数。"""

from pathlib import Path

from langchain.tools import tool
import tools as evidence_tools


def make_tools(data_dir: Path | None = None) -> list:
    @tool
    def get_execution_detail(execution_id: str) -> dict:
        """读取执行ID对应的请求、预期、实际响应或传输错误。分析前先调用此工具。"""
        return evidence_tools.get_execution_detail(execution_id, data_dir=data_dir)

    @tool
    def get_api_rules(operation_id: str) -> dict:
        """按接口ID精确查询业务规则与证据ID。核实业务断言时使用；不用于解释网络超时。"""
        return evidence_tools.get_api_rules(operation_id, data_dir=data_dir)

    return [get_execution_detail, get_api_rules]
