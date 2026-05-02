"""Frontend abstraction — decouples core from any specific UI channel."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Frontend(Protocol):
    """Bidirectional frontend interface.

    Inbound: the frontend calls on_message(chat_id, open_id, chat_type, text)
    Outbound: core calls frontend.send_text(chat_id, text)
    """

    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message to a chat."""
        ...

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        """Stream a single token (for frontends that support streaming).

        Default: no-op. Feishu doesn't need this.
        """
        ...

    async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
        """Notify that an agent is calling a tool."""
        ...
