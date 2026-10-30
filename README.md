# 失败分析 Agent：第1步，离线数据与工具

当前版本只有**读取证据**的能力，没有模型、Agent、自动诊断或被测接口调用。两个工具就是普通 Python 函数。你可以先看见输入和返回值，再理解后续模型如何调用它们。

运行代码仅依赖 Python 标准库；测试额外依赖 pytest。建议 Python 3.11 或更高。所有记录都是人工构造的教学样本，不含真实业务数据或密钥。

## 文件结构

```text
python-failure-agent/
├── tools.py                   # 两个只读函数及数据加载辅助函数
├── demo.py                    # 人工选择执行ID、是否查询规则的入口
├── data/
│   ├── executions.json        # 两条失败执行记录
│   └── rules.json             # 按 operation_id 组织的接口规则
├── tests/test_tools.py        # 查询、异常、路径和结果独立性测试
├── docs/walkthrough.md        # 逐段代码与测试讲解
├── requirements-dev.txt       # 只声明测试依赖
├── pytest.ini                 # 测试目录、模块搜索路径
└── .gitignore                 # 排除本地虚拟环境和缓存
```

## 从准备到验证

Windows PowerShell，在项目目录运行。以下 `python` 必须指向实际安装的 Python，而不是 Windows 商店占位命令。

```powershell
cd 'C:\Users\Dante\Documents\简历\python-failure-agent'
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe demo.py --execution-id RUN-001 --include-rules
.\.venv\Scripts\python.exe -m pytest -q
```

不必激活虚拟环境，明确使用其中的解释器即可。此工作区已创建 `.venv`，可直接执行最后两条命令。当前机器的全局 `python` 是商店占位程序，我使用下列现有解释器创建了虚拟环境：

```powershell
& 'C:\Users\Dante\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
```

如果项目移到其他机器，请用该机器的 Python 重新创建虚拟环境，不复制 `.venv`。

## 三个手动示例

### 1. 业务断言失败：读取记录并查询规则

```powershell
.\.venv\Scripts\python.exe demo.py --execution-id RUN-001 --include-rules
```

输出有 `execution` 和 `api_rules`：请求 amount=100、discount=120；预期400，实际200且 payable=-20；规则证据为 RULE-001、RULE-002。

这一步只把事实摆出来，没有程序或模型自动认定根因。

### 2. 连接超时：只读取执行详情

```powershell
.\.venv\Scripts\python.exe demo.py --execution-id RUN-002
```

输出中 `actual` 为 null，`transport_error.type` 为 CONNECT_TIMEOUT。没有收到响应，所以不存在实际HTTP状态码，也不能据此确认产品逻辑有错。

### 3. 不存在的记录

```powershell
.\.venv\Scripts\python.exe demo.py --execution-id RUN-404 --include-rules
```

输出 `found=false`、`record=null`、`evidence_id=null`。不会继续查规则，因为没有可信的 operation_id。查询不存在是正常业务返回，命令不会仅因此退出失败。

## 工具直接调用

```python
from tools import get_execution_detail, get_api_rules

execution = get_execution_detail("RUN-001")
if execution["found"]:
    operation_id = execution["record"]["operation_id"]
    knowledge = get_api_rules(operation_id)
    print(knowledge)
```

数据流：`RUN-001 → executions.json → operation_id=calculateOrder → rules.json → RULE-001/RULE-002`。

这里传递 operation_id 是分析程序关联证据，不是跨接口测试变量传递；没有发送任何业务请求。

## 设计边界

- ID精确匹配、区分大小写，不默默修正输入。
- 业务查询不存在返回结构化信息；空ID抛 ValueError。
- 文件不存在、JSON损坏抛异常，不假装记录不存在。
- 每次从文件读取新的对象，调用方修改返回值不会污染后续查询。
- 当前只是本地教学数据，没有项目权限或租户隔离功能。
- 只校验文件顶层是对象，不进行完整的嵌套数据Schema校验；未来引入Pydantic再扩展。
- demo中的查询顺序由人和if语句决定，不是Agent。下一步才由模型请求工具。

详细解释见 [逐段讲解](docs/walkthrough.md)。
