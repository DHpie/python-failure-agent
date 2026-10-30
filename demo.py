"""手动调用工具的教学入口；固定步骤，不是 Agent。"""

import argparse
import json
import sys

from tools import get_api_rules, get_execution_detail


def main() -> None:
    # Windows重定向/工具捕获时也输出UTF-8，避免中文乱码。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="离线查看执行记录和关联规则（无模型）")
    parser.add_argument("--execution-id", default="RUN-001")
    parser.add_argument("--include-rules", action="store_true", help="人工指定是否查询规则")
    args = parser.parse_args()

    execution = get_execution_detail(args.execution_id)
    output = {"execution": execution}
    if args.include_rules and execution["found"]:
        operation_id = execution["record"]["operation_id"]
        output["api_rules"] = get_api_rules(operation_id)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
