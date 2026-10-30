# 第1步逐段讲解

## 1. 为什么先用普通函数

以后Agent请求一个工具时，真正读取记录的依然是这些Python函数。先写成可直接测试的函数，可以把数据读取正确性和模型决策正确性分别验证。当前不用 `@tool`，不安装LangChain或模型SDK，也不配置API Key。

## 2. 数据分别表示什么

`executions.json` 的键是执行ID。同一用例后续可以执行多次，每次有不同 execution_id；case_id识别用例，operation_id识别接口。

| 字段 | 作用 |
|---|---|
| execution_id | 本次执行及证据标识 |
| case_id | 被执行的测试用例 |
| operation_id | 找到对应接口规则 |
| request | 实际发送的请求配置 |
| expected | 已确认的预期和断言 |
| actual | 收到的HTTP响应；未收到则为null |
| transport_error | 连接等传输错误，没有则为null |
| failure_kind | 已由原测试执行器记录的失败类别，不是根因 |

RUN-001的失败事实是“预期400，实际200，并出现负数应付金额”。规则说明优惠不应超过订单金额。两者可支持后续提出“校验可能失效”，但还不能证明服务端具体哪一行代码出错。

RUN-002连接超时，没有HTTP响应。不要把连接超时与HTTP 504混为一谈：504是收到的服务端/网关响应。

`rules.json` 按 operation_id精确查表。每条规则有 evidence_id 和原文，后续分析可以引用。getOrder提供另一接口的规则，用于验证不会串入订单计算规则；healthCheck的空数组用于区分“接口已登记但没有规则”和“接口不在库中”。

## 3. tools.py：从路径到结果

### 默认路径

```python
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
```

`__file__` 是当前tools.py路径；parent是它所在目录。这样从其他目录启动脚本，也能找到项目数据。

### 文件读取

`_load_object`打开指定JSON文件，显式使用UTF-8，再用json.load变成Python字典。顶层不是字典时抛ValueError。文件错误不在这里吞掉，调用者可以看到真正故障。

`data_dir=None` 表示使用默认数据目录；测试可以传入临时目录。`*`后面的参数必须写成 `data_dir=...`，避免误把它当成工具的业务参数。路径只能由程序/测试指定，未来不暴露给模型。

### 输入检查

`_validate_id`拒绝非字符串和全空白ID。有效字符串仍然精确查找，例如前面多了空格的 ` RUN-001` 不会自动匹配。这让调用错误更容易发现。

### 执行记录查询

`get_execution_detail`：校验ID → 加载executions.json → 按键查询 → 返回固定形状的字典。

找到时包含原始record和证据ID；找不到时found=false，record和evidence_id为None。Python的None序列化为JSON的null。

函数不计算风险、不判断产品缺陷、不调用另一工具。

### 接口规则查询

`get_api_rules`：校验ID → 加载rules.json → 检查键是否存在 → 返回该接口规则。

`found`表示接口是否在规则库中，不表示一定有规则。因此 healthCheck会返回found=true、rules=[]；未知接口返回found=false、rules=[]。两个工具都返回可直接转成JSON的值，方便以后传给模型。

## 4. demo.py：谁决定调用工具

argparse读取命令行参数。先调用get_execution_detail，再由 `--include-rules` 和 `found` 决定是否读取规则。查询规则所需operation_id来自记录，不需要用户再手动填写。

这里的if只是教学演示。未来Agent替换这个选择过程，工具本身继续保留。最后 `json.dumps(..., ensure_ascii=False, indent=2)` 让中文与嵌套数据容易阅读。

## 5. pytest测试分别验证什么

| 测试组 | 关键断言及意义 |
|---|---|
| 正常读取 | 保留输入和预期/实际差异，不能改写事实 |
| 超时读取 | actual为None，不虚构HTTP响应 |
| 记录不存在 | 返回缺失状态，不产生假的证据 |
| 规则归属 | calculateOrder只能返回RULE-001/002 |
| 空规则与未知接口 | 保留业务语义差异 |
| 非法ID参数化 | 两个工具分别拒绝空值、空白、None和数值 |
| 精确匹配 | 不默默修改ID或大小写 |
| 返回值独立性 | 修改本次结果不污染下次读取 |
| 切换工作目录 | 默认数据路径不依赖当前目录 |
| 注入临时目录 | 测试可使用独立数据，不修改样本 |
| 文件异常 | 缺文件、坏JSON、错误顶层类型不能被隐藏 |
| JSON序列化 | 返回值可安全转换成JSON数据 |

`pytest.mark.parametrize`相当于JUnit参数化测试。`tmp_path`相当于临时测试目录；`monkeypatch.chdir`临时切换目录，测试结束自动恢复。

这些是确定性的工具单测，不是LLM Eval。当前没有模型，不需要评估幻觉、模型选工具或原因归纳。

执行完整测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

看每条测试名字：

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

只看超时样本测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -v -k timeout
```

## 6. 建议的阅读和练习顺序

1. 手动读RUN-001和RULE-001/002，自己比较预期与实际。
2. 执行demo，确认控制台输出与文件一致。
3. 阅读两个工具函数，再阅读文件加载辅助函数。
4. 运行pytest -v，对照上表理解各测试的目标。
5. 在rules.json增加一条有独立证据ID的规则，重新运行demo；记得同步调整对规则列表的测试预期。
6. 为新的接口添加规则及测试，确认查询不会混入其他接口。

这一阶段的完成标志：你能不依赖模型，解释一个执行ID如何关联到接口规则，并说明缺失数据和系统故障有什么不同。
