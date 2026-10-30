# 第2步：配置模型、组装消息、调用一次

## 学习目标与边界

第一步只展示证据；这一步将证据传给聊天模型，请它给出自然语言分析。查询顺序由Python程序决定；没有Agent、工具绑定、ToolMessage、循环、记忆或强制JSON输出。每次运行创建新的消息列表，不自动继承上次运行。

```text
命令行execution_id
  → build_messages：读取执行记录与接口规则
  → [SystemMessage, HumanMessage]
  → build_model：读取配置、创建ChatOpenAI客户端
  → model.invoke(messages)：发送请求
  → AIMessage：模型回复及可用的用量信息
```

RUN-002同样会读取规则，即使分析超时未必需要。这是故意保留的固定流程；后续Agent才按需选择工具。RUN-404在本地就终止，不读模型配置、不发送请求。

## 文件职责与建议阅读顺序

1. `model_demo.py`的SYSTEM_PROMPT和build_messages：看模型实际会收到什么。
2. `.env.example`和`model_config.py`：理解模型连接参数。
3. `invoke_once`和main：看何时发送请求、如何打印响应。
4. `tests/test_model_demo.py`：看哪些行为能离线验证。

原来的tools.py、数据和demo.py保持原有行为。

## 1. 安装与预览消息（无密钥、无网络调用）

```powershell
cd 'C:\Users\Dante\Documents\简历\python-failure-agent'
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe model_demo.py --execution-id RUN-001 --dry-run
```

输出两个消息对象，type分别为system和human。LangChain的HumanMessage会映射成API中的user角色；模型回复是AIMessage，对应assistant角色。

### SystemMessage

描述角色、分析任务及边界：区分事实与推测、引用证据、信息不足时说明。它不是权限控制或可靠的注入防护；后续仍需用程序验证引用和行为。

### HumanMessage

包含当前任务和证据JSON：execution与api_rules。json.dumps将字典变为文本，因为模型收到的是消息内容，不会自动读取本地文件。

```python
return [
    SystemMessage(content=SYSTEM_PROMPT),
    HumanMessage(content="请分析以下执行证据：\n" + json.dumps(evidence, ensure_ascii=False, indent=2)),
]
```

这里的两个工具只是被Python直接调用。我们把返回值放入HumanMessage，尚未给模型注册可调用工具，因此没有ToolMessage。

先对照RUN-001确认：amount=100、discount=120；预期400；实际200和payable=-20；规则ID为RULE-001和RULE-002。

## 2. 配置你已有的模型服务

本示例使用LangChain的ChatOpenAI适配器调用兼容Chat Completions的HTTP接口。它不意味着必须使用某个特定厂商；但“兼容”程度和支持参数需以你的服务文档为准。若服务只提供另一种协议，需要换对应适配器，不能只修改URL。

```powershell
Copy-Item .env.example .env
```

手动打开.env填写：

```dotenv
LLM_BASE_URL=https://你的服务提供的API基础地址/v1
LLM_MODEL=服务商实际提供的模型ID
LLM_API_KEY=你的真实密钥
LLM_TIMEOUT_SECONDS=60
LANGSMITH_TRACING=false
```

| 配置 | 意义与注意事项 |
|---|---|
| LLM_BASE_URL | API基础地址，按服务文档填写，通常不要追加/chat/completions |
| LLM_MODEL | API模型ID，不一定等于网页展示名 |
| LLM_API_KEY | 认证密钥，只存在.env或进程环境变量，不进入消息 |
| LLM_TIMEOUT_SECONDS | 客户端请求超时配置，当前允许1～300秒；不是整个任务的硬截止时间 |
| LANGSMITH_TRACING | 本阶段保持false，不将消息额外上传到LangSmith |

代码显式从项目目录加载.env，进程环境变量优先。不要把.env或密钥截图提交到仓库。配置类会拒绝缺失项、模板占位值和不合法超时。

`build_model`将上述参数传给ChatOpenAI：

```python
ChatOpenAI(
    model=settings.model,
    api_key=settings.api_key,
    base_url=settings.base_url,
    timeout=settings.timeout,
    max_retries=0,
    use_responses_api=False,
)
```

创建客户端不等于发送请求。max_retries=0用于教学：本阶段不自动重试；use_responses_api=False明确选择Chat Completions调用路径。暂不设置temperature，避免部分模型不支持该参数；这也意味着不能假定结果完全一致。

## 3. 真正的请求发生在invoke

```python
response = model.invoke(messages)
```

这是一处同步阻塞调用。适配器将消息转换为服务请求，SDK负责认证和网络传输，再将响应转换成AIMessage。业务代码无需手动拼Authorization Header。

读取：

```python
response.content          # 文本或内容块
response.usage_metadata   # 服务返回的Token统计，可能为空
```

当前只打印回复，没有自动解析JSON、检查结论或验证引用。缺少用量不是0 Token；回复为空也不能自动认定分析成功。不要把模型输出直接当成已确认根因。

## 4. 执行真实调用

```powershell
.\.venv\Scripts\python.exe model_demo.py --execution-id RUN-001
.\.venv\Scripts\python.exe model_demo.py --execution-id RUN-002
```

每条命令尝试发起一次模型调用，可能产生服务费用。示例会发送本地执行记录和规则，所以目前只使用构造的脱敏数据。

RUN-001合理的回复应指出：优惠超过金额、预期400但实际200、出现负数应付金额；上限校验可能异常，但缺少实现或日志，不能确认代码根因。

RUN-002应说明连接未建立、没有实际HTTP响应；不能根据业务规则直接判断优惠计算逻辑错误。

这些是人工核对要点，不是固定标准答案，也不是本阶段自动测试已经证明的模型能力。

## 5. 离线测试验证什么

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/test_model_demo.py -v
```

测试通过Mock替换模型，替代.env读取，不使用真实密钥、不发送网络请求：

- 消息角色和证据内容正确。
- 超时样本没有被补成一个HTTP响应。
- 不存在的记录不触发模型调用。
- invoke恰好调用一次，AIMessage原样返回。
- 模型超时向上传递，不生成假的成功分析。
- 缺配置、错误超时会被拒绝。
- 客户端构造参数正确。

Mock提供的回复是测试人为指定的，不能用来证明真实模型分析准确。此阶段也没有验证真实服务的认证、网络和协议兼容性。真正的连通性只能由填写配置后的调用验证。

## 6. 常见问题与排查

命令退出码：0表示预览或调用流程完成，2表示输入/配置错误，1表示其他错误。0不意味着分析内容已通过质量评测。

| 现象 | 排查方向 |
|---|---|
| 缺少配置 | 确认文件名为.env，且已填写三个必要字段 |
| AuthenticationError | 检查密钥、所属服务和授权 |
| NotFoundError / BadRequestError | 检查基础地址、模型ID、协议和参数支持 |
| APIConnectionError / APITimeoutError | 检查网络、代理、服务可用性和超时配置 |
| RateLimitError | 检查额度和频率限制；本阶段无自动重试 |

命令不回显SDK完整异常正文，避免错误信息夹带凭证。调试时先核对配置，不要把密钥粘贴到日志或聊天。

## 7. 与下一步的关系

当前：Python固定查询两份证据 → 发一组消息 → 收一个AIMessage。

以后：注册工具 → 模型请求工具 → 程序执行并回传 → 模型继续或结束。先看懂当前消息的来源、内容和返回值，再加入这个循环。

参考：[聊天模型集成](https://docs.langchain.com/oss/python/integrations/chat/openai)、[消息](https://docs.langchain.com/oss/python/langchain/messages)。
