from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, TypedDict, cast

from openai import DEFAULT_MAX_RETRIES, not_given, omit
from openai._types import Omit
from openai.types import ChatModel
from typing_extensions import Unpack

from autogen.beta.config.openai.openai_client import CreateOptions, OpenAIClient


class DeepSeekOpenAIConfigOverrides(TypedDict, total=False):
    model: ChatModel | str
    api_key: str | None
    base_url: str | None
    temperature: float | None | Omit
    streaming: bool
    timeout: Any
    max_retries: int
    default_headers: dict[str, str] | None
    default_query: dict[str, object] | None


@dataclass(slots=True)
class DeepSeekOpenAIConfig:
    """Minimal AG2 ModelConfig for DeepSeek chat-completions compatibility.

    AG2 0.11.5 does not expose ``extra_body`` on ``OpenAIConfig``, but DeepSeek's
    chat-completions API needs ``thinking.type=disabled`` to avoid returning
    ``reasoning_content`` that must be replayed in subsequent requests.
    """

    model: ChatModel | str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None | Omit = omit
    streaming: bool = False
    timeout: Any = not_given
    max_retries: int = DEFAULT_MAX_RETRIES
    default_headers: dict[str, str] | None = None
    default_query: dict[str, object] | None = None

    def copy(
        self,
        /,
        **overrides: Unpack[DeepSeekOpenAIConfigOverrides],
    ) -> "DeepSeekOpenAIConfig":
        return replace(self, **overrides)

    def create(self) -> OpenAIClient:
        options: dict[str, Any] = cast(
            dict[str, Any],
            CreateOptions(
                model=self.model,
                stream=self.streaming,
                temperature=self.temperature,
                stream_options={"include_usage": True} if self.streaming else omit,
            ),
        )
        options["extra_body"] = {
            "thinking": {
                "type": "disabled",
            }
        }

        return OpenAIClient(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
            default_headers=self.default_headers,
            default_query=self.default_query,
            create_options=cast(CreateOptions, options),
        )
