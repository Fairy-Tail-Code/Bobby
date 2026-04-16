"""Channel adapter abstraction for HITL communication.

Each channel (email, DingTalk, Feishu, etc.) implements ``send`` + ``poll_reply``
so that ``ChannelUserProxyAgent`` stays transport-agnostic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    """Generic send/receive interface for human-in-the-loop messaging."""

    @abstractmethod
    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        """Send a message to the human operator.

        Args:
            recipient: Platform-specific user identifier
                       (email address / DingTalk userId / Feishu open_id).
            subject:   Short summary of what the agent is asking.
            body:      Full message content from the agent.
            request_id: Unique ID embedded in the message for reply matching.
        """

    @abstractmethod
    async def poll_reply(self, request_id: str) -> str | None:
        """Check whether a reply has arrived for *request_id*.

        Returns the reply text if found, or ``None`` to signal "not yet".
        The caller handles the polling loop and timeout.
        """

    async def start(self) -> None:  # noqa: B027
        """Initialize long-lived resources (connections, streams).

        Default no-op — channels that need no setup can skip overriding.
        """

    async def stop(self) -> None:  # noqa: B027
        """Tear down resources opened in ``start``.

        Default no-op — channels that need no cleanup can skip overriding.
        """
