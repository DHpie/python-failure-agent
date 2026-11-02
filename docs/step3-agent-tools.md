# 第3步：Agent自己请求工具，程序执行并回传

## 1. 与第二步的唯一主线差异

第二步在模型调用前就执行了两个函数，再把所有证据放进HumanMessage。

第三步开始时只有任务“分析RUN-001”。模型收到系统指令、用户消息和工具说明，自行生成工具调用请求。LangChain查找并执行工具，把结果作为ToolMessage放回消息历史，再次调用模型。

```text
HumanMessage：分析RUN-001
  → AIMessage：请求get_execution_detail(execution_id="RUN-001")
  → ToolMessage：执行详情
  → AIMessage：请求get_api_rules(operation_id="calculateOrder")
  → ToolMessage：规则证据
  → AIMessage：最终文字分析，没有tool_calls
  → 循环结束
```

这是一条合理轨迹，不是所有真实模型都必然采用的固定顺序。模型可能跳过规则查询、请求错误参数或提前结束，后续需要评测和业务校验。

没有跨接口测试编排，没有发送新的测试请求，没有写业务数据。这里只在分析过程中读取证据。

## 2. 先离线观察，不需要配置密钥

```powershell
cd 'C:\Users\Dante\Documents\简历\python-failure-agent'
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe agent_demo.py --offline --execution-id RUN-001
```

`--offline`使用ScriptedChatModel：模拟模型响应是预设的；create_agent、工具调用分派、真实JSON读取、ToolMessage回传、Middleware都实际运行。它让你稳定看到每一步，但不能证明LLM具备工具选择能力。

控制台逐条展示消息；最后保存 `outputs/step3-trace.json`，再次运行覆盖。该文件包含模式、系统指令、消息、调用ID、工具结果和结束状态，不包含API Key。

轨迹保存的是输入输出和可观察动作，不是模型内部思维过程。真实数据接入后需要脱敏；当前使用构造样本。

再运行：

```powershell
.\.venv\Scripts\python.exe agent_demo.py --offline --execution-id RUN-002
.\.venv\Scripts\python.exe agent_demo.py --offline --execution-id RUN-404
```

- RUN-002的脚本仅查询执行详情，再说明连接超时，未查询业务规则。
- RUN-404也会先调用工具，收到found=false。与第二步“在模型调用前查不到就退出”不同，本次由模型看到缺失结果后结束。离线脚本最后提示检查数据，真实模型应明确说明记录不存在。
- 离线脚本只为上述样本设计；其他ID的结果不能视为已支持的分析案例。

## 3. 工具如何从普通函数变成模型接口

`tools.py`保留原始读取函数。`agent_tools.py`使用窄包装：

```python
@tool
def get_execution_detail(execution_id: str) -> dict:
    """读取执行ID对应的请求、预期、实际响应或传输错误。分析前先调用此工具。"""
    return evidence_tools.get_execution_detail(execution_id, data_dir=data_dir)
```

装饰器根据函数名、说明和类型生成工具Schema；模型获得的是“可调用什么、何时调用、参数是什么”。本地文件不会因此自动发送给模型，工具执行返回的数据才会成为消息。

data_dir捕获在闭包中，不出现在模型可见的参数中。未来改用数据库或Chroma，也可以只更换内部实现。

## 4. Agent构造与每轮模型输入

```python
agent = create_agent(
    model=model,
    tools=make_tools(data_dir),
    system_prompt=SYSTEM_PROMPT,
    middleware=[model_limit, tool_limit, handle_evidence_errors],
)
```

`create_agent`创建基于图的运行时，负责绑定工具和循环。我们不手写while循环，也未使用response_format，所以最终仍是自然语言。

每轮模型调用的概念输入：

```text
第1轮：system + human + 两个工具定义
第2轮：system + human + ai(tool_calls) + tool(执行详情) + 工具定义
第3轮：system + 上述历史 + ai(tool_calls) + tool(规则) + 工具定义
```

工具定义是请求的独立部分，并不是普通HumanMessage中的一段文字。system_prompt在模型节点调用时注入，因此stream返回的messages通常不包含SystemMessage；轨迹文件将system_prompt单独保存。测试检查了模拟模型真正收到system消息。

## 5. 工具请求与工具结果如何配对

模型返回的AIMessage可能没有正文，但包含：

```json
{
  "tool_calls": [{
    "name": "get_execution_detail",
    "args": {"execution_id": "RUN-001"},
    "id": "call-execution"
  }]
}
```

程序执行后返回：

```json
{
  "type": "tool",
  "name": "get_execution_detail",
  "tool_call_id": "call-execution",
  "content": "包含执行详情的JSON文本"
}
```

工具请求在AIMessage里，工具结果在ToolMessage里，两个ID对应。下一次模型调用读取这些消息，才知道查询结果。不是模型直接打开了本地文件。

## 6. 如何打印消息，为什么不是token流

`run_agent`使用 `agent.stream(..., stream_mode="values")` 获取各节点完成后的完整状态。程序只打印比上次新增的消息，避免重复。

这属于节点级进度，模型调用完成后才看到AIMessage；不是逐token输出。每次运行创建独立Agent状态，不配置checkpointer，不延续前一次消息。

模型可能一次请求多个工具；框架可以分派这些调用，结果消息按各自tool_call_id关联。不能让有依赖的工具靠同一批并行请求猜测尚未取得的数据，Prompt要求先读取执行详情。

## 7. 正常结束、受控中止和质量通过是三回事

### 正常结束

无结构化输出模式下，模型返回没有tool_calls的AIMessage，框架结束循环。`completed_unverified`只表示运行完成，不表示证据、结论或引用已经通过审核。

即使模型没有读证据就直接回答，框架也可能正常结束。本阶段专门有测试展示这个边界；不要把Prompt要求误认为已实现的强制质量门禁。

### 调用限制

默认模型最多5次、工具最多3次。使用ModelCallLimitMiddleware和ToolCallLimitMiddleware，exit_behavior="error"，超限抛异常，轨迹标记aborted，不输出假的成功结论。

```powershell
# 离线RUN-001需要3次模型调用，故该命令会中止，退出码1
.\.venv\Scripts\python.exe agent_demo.py --offline --execution-id RUN-001 --max-model-calls 2

# 该样本需要2次工具调用，限为1时会阻止第二次工具执行
.\.venv\Scripts\python.exe agent_demo.py --offline --execution-id RUN-001 --max-tool-calls 1
```

调用上限是程序规则，不依赖模型自觉。LangGraph的recursion_limit=30额外约束图执行步数，它不是模型调用次数，也不是秒数。

沿用第二步的单次请求超时，不等于整个任务的硬超时；本阶段尚未实现整体取消/硬截止。

### 错误反馈

- 记录不存在：工具正常返回found=false，ToolMessage的技术执行状态仍可以是success。
- JSON坏了或文件不存在：自定义wrap_tool_call Middleware转换为status=error的工具消息，模型能说明信息缺口。
- 未注册工具或缺必要参数：框架工具节点拒绝并返回错误消息，测试验证此行为。
- 模型网络错误、额度错误、调用超限：中止任务，保留已观察到的消息；不悄悄编造分析。

错误被返回给模型不保证模型会合理处理。上限和后续Eval是补充机制。

## 8. 接入真实模型

沿用第二步.env，服务必须支持标准Tool Calling。第二步普通对话可用，并不能保证该模型/兼容服务的工具调用也可用。

```powershell
.\.venv\Scripts\python.exe agent_demo.py --execution-id RUN-001
```

真实模式不预读文件，不预设工具决定；由模型根据工具说明决定。一次分析可能调用模型多次，Token费用也随之增加。原先max_retries=0仍然有效，不自动重试网络请求。

人工观察：是否先读取了用户指定记录？是否从实际记录获得operation_id？业务场景是否合理使用规则？超时是否避免编造HTTP响应？最终结论是否引用已取得的证据并保留不确定性？

本次交付不使用真实密钥进行联网分析，因此真实模型选择合理性与API兼容性待你配置后验证。

## 9. 测试如何证明循环真实运行

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_demo.py -v
.\.venv\Scripts\python.exe -m pytest -q
```

测试没有Mock掉create_agent或工具节点；只替换聊天模型。ScriptedChatModel继承BaseChatModel，返回带tool_calls的AIMessage，记录每次实际收到的消息。

| 测试 | 验证内容 |
|---|---|
| 工具Schema | 模型只看见业务ID，不可指定本地目录 |
| 完整循环 | human→ai→tool→ai→tool→ai；真实读取本地JSON |
| 结果回传 | 第二/三轮模拟模型输入中包含前轮工具结果 |
| 超时分支 | 可只读执行详情后结束 |
| 记录缺失 | found=false确实来自工具执行 |
| 提前结束 | 没有tool_calls即结束，但并未证明质量 |
| 证据文件错误 | Middleware将异常变成ToolMessage |
| 未知工具/参数错误 | 无法执行的调用返回错误 |
| 模型/工具上限 | 分别触发准确的超限异常 |
| 模型失败 | 中止，不伪造最终分析 |

这些是框架与程序行为测试。脚本固定选择规则工具，不能据此宣称真实LLM会选对。自然语言结论准确性、证据支持程度、结构化输出、正式Eval仍是后续步骤。

## 10. 阅读顺序

先运行离线RUN-001，打开轨迹数清六条消息；再读agent_tools.py、run_agent、两个调用限制和handle_evidence_errors；最后看scripted_model.py，理解它只替代模型，为什么测试仍有意义。随后运行真实模式对比轨迹，不必要求模型与脚本完全一致。

参考：[Agent](https://docs.langchain.com/oss/python/langchain/agents)、[内置Middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)。依赖版本固定在requirements.txt。
