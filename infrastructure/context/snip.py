"""Level 1: Snip Compact — message history trimming.

Thin wrapper around AG2's built-in ``MessageHistoryLimiter``.
It keeps only the most recent N messages, optionally preserving the first
user message so the original request is never lost.

Usage::

    from infrastructure.context.snip import create_snip_transform

    snip = create_snip_transform(max_messages=60)
    snip.add_to_agent(my_agent)
"""
from __future__ import annotations

# 导入 AG2 消息转换能力基类，用于对 Agent 对话消息进行处理
from autogen.agentchat.contrib.capabilities.transform_messages import TransformMessages
# 导入消息历史长度限制器，用于截断过长的聊天历史，避免上下文溢出
from autogen.agentchat.contrib.capabilities.transforms import MessageHistoryLimiter


def create_snip_transform(
    max_messages: int = 500,                # 最大保留的消息条数，超过则自动截断
    keep_first_message: bool = True,       # 是否保留第一条消息（通常是用户初始请求，非常重要）
    exclude_names: list[str] | None = None,# 不需要计数/截断的 Agent 名称列表
) -> TransformMessages:
    """Create a Level 1 snip transform using AG2's MessageHistoryLimiter.

    创建 AG2 一级消息截断转换功能，用于限制对话历史长度，防止 LLM 上下文超限。

    Args:
        max_messages: Maximum number of messages to retain. 保留的最大消息条数
        keep_first_message: Always keep the initial user request message. 始终保留第一条用户消息
        exclude_names: Agent names whose messages should be excluded before applying the limit.
            应用长度限制前，需要排除的 Agent 名称（这些 Agent 的消息不计入数量限制）
    """
    # 初始化消息历史限制器，配置截断规则
    limiter = MessageHistoryLimiter(
        max_messages=max_messages,
        keep_first_message=keep_first_message,
        exclude_names=exclude_names,
    )
    # 封装为 TransformMessages 并返回，可直接挂载到 AG2 Agent 上使用
    return TransformMessages(transforms=[limiter])


# todo 需要对每个agent的历史消息中去除其他agent的工具调用，节省token，目前的上下文完全共享，这显然是框架缺陷。