"""离线只读工具：此阶段不依赖 LangChain，也不调用被测 API。"""

import json
from pathlib import Path
from typing import Any


# 从代码文件定位数据，因此不依赖运行命令时所在的目录。
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_object(filename: str, data_dir: Path | None) -> dict[str, Any]:
    """基础设施错误向上抛出；不伪装成“业务记录不存在”。"""
    directory = DEFAULT_DATA_DIR if data_dir is None else Path(data_dir)
    with (directory / filename).open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{filename} 的顶层必须是 JSON 对象")
    return data


def _validate_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def get_execution_detail(
    execution_id: str, *, data_dir: Path | None = None
) -> dict[str, Any]:
    """按执行ID读取请求、预期、实际响应或传输错误，不推测失败原因。"""
    _validate_id(execution_id, "execution_id")
    records = _load_object("executions.json", data_dir)
    record = records.get(execution_id)
    if record is None:
        return {
            "found": False,
            "execution_id": execution_id,
            "evidence_id": None,
            "record": None,
            "message": "执行记录不存在",
        }
    return {
        "found": True,
        "execution_id": execution_id,
        "evidence_id": execution_id,
        "record": record,
        "message": "已找到执行记录",
    }


def get_api_rules(
    operation_id: str, *, data_dir: Path | None = None
) -> dict[str, Any]:
    """按接口ID精确读取业务规则；这是查表，不是向量检索或RAG。"""
    _validate_id(operation_id, "operation_id")
    rules_by_operation = _load_object("rules.json", data_dir)
    found = operation_id in rules_by_operation
    rules = rules_by_operation.get(operation_id, [])
    if not found:
        message = "接口不在规则库中"
    elif not rules:
        message = "接口已登记，但尚未配置规则"
    else:
        message = "已找到接口规则"
    return {
        "found": found,
        "operation_id": operation_id,
        "rules": rules,
        "message": message,
    }
