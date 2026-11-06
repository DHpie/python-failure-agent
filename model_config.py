"""只在准备真实调用时读取配置、构造聊天模型。"""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

ENV_FILE = Path(__file__).resolve().parent / ".env"


@dataclass(frozen=True)
class ModelSettings:
    base_url: str
    model: str
    api_key: str
    timeout: float

    @classmethod
    def from_env(cls) -> "ModelSettings":
        # 已设置的进程环境变量优先，不在import时读取密钥。
        load_dotenv(ENV_FILE, override=False)
        names = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
        values = {name: os.environ.get(name, "").strip() for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError("缺少配置：" + ", ".join(missing))
        url = urlsplit(values["LLM_BASE_URL"])
        if url.scheme not in {"https", "http"} or not url.hostname:
            raise ValueError("LLM_BASE_URL必须是HTTP(S)地址")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("LLM_BASE_URL不能包含凭证、查询参数或片段")
        if url.hostname.endswith(".example") or values["LLM_MODEL"] == "your-model-id" or values["LLM_API_KEY"] == "your-api-key":
            raise ValueError("请将.env.example中的占位配置替换为真实配置")
        try:
            timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
        except ValueError:
            raise ValueError("LLM_TIMEOUT_SECONDS必须是1到300之间的数字") from None
        if not 1 <= timeout <= 300:
            raise ValueError("LLM_TIMEOUT_SECONDS必须是1到300之间的数字")
        return cls(values["LLM_BASE_URL"], values["LLM_MODEL"], values["LLM_API_KEY"], timeout)


def build_model(settings: ModelSettings) -> ChatOpenAI:
    # 此处只创建客户端；invoke才发送请求。暂不绑定工具、不要求JSON输出。
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout,
        max_retries=2,
        use_responses_api=False,
    )
