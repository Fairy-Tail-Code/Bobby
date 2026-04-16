"""
第四层：自动压缩 — 基于大模型的对话总结。

当累计对话超过token阈值时，使用 AG2 内置的 _reflection_with_llm 生成摘要，
用摘要替换早期消息，同时保留最近上下文。

本类符合 AG2 MessageTransform 规范 — 通过 TransformMessages 添加后，
会自动挂载到 process_all_messages_before_reply 流程中。
"""
from __future__ import annotations

import copy
import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 默认总结提示词
# ---------------------------------------------------------------------------
DEFAULT_SUMMARY_PROMPT = """\
Summarize the multi-agent conversation below. The conversation involves \
Planner, Generator, and Evaluator agents collaborating to build a full-stack \
application.

Your summary MUST include:

1. **User Request** — What the user asked to build (preserve original intent).
2. **Plan Summary** — What the Planner decided (architecture, tech stack, features).
3. **Implementation Progress** — Key files created/modified, code patterns, \
architectural decisions. Include file paths and critical code snippets.
4. **Errors & Fixes** — Any errors encountered and how they were resolved.
5. **Evaluation Status** — What the Evaluator found, scores given, issues raised.
6. **Current Task** — What is being worked on right now (be specific about \
which agent is active and what it's doing).
7. **Pending Work** — What still needs to be done.

Be thorough and specific. This summary will replace the original context, \
so include every detail needed to continue the work seamlessly.
"""

# 总结预留token空间，确保模型仍有足够token生成回复
_SUMMARY_OUTPUT_BUDGET = 4_000
# 始终保留最近 N 条消息原文不压缩
_KEEP_RECENT_MESSAGES = 6

# ---------------------------------------------------------------------------
# token统计工具
# ---------------------------------------------------------------------------

# GPT-3.5/4 通用编码
_ENCODER = tiktoken.get_encoding("cl100k_base")

def _count_tokens(text: str) -> int:
    """使用 cl100k_base 统计文本token数"""
    if not text:
        return 0
    return len(_ENCODER.encode(text))

def _estimate_message_tokens(msg: dict[str, Any]) -> int:
    """估算单条消息的token数（含格式开销）"""
    content = msg.get("content")
    if isinstance(content, str):
        return _count_tokens(content) + 4
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    total += _count_tokens(item.get("text", ""))
                else:
                    total += 10
            elif isinstance(item, str):
                total += _count_tokens(item)
        return total + 4
    return 4

def _estimate_total_tokens(messages: list[dict[str, Any]]) -> int:
    """计算整个消息列表的总token数"""
    return sum(_estimate_message_tokens(m) for m in messages)

# ---------------------------------------------------------------------------
# 自动压缩转换器
# ---------------------------------------------------------------------------

class AutoCompactTransform:
    """
    AG2 MessageTransform：基于 LLM 自动总结压缩历史消息。

    用法：
        from autogen.agentchat.contrib.capabilities import TransformMessages

        auto_compact = AutoCompactTransform(agent=my_agent, max_tokens=80000)
        TransformMessages(transforms=[auto_compact]).add_to_agent(my_agent)
    """

    def __init__(
        self,
        agent: Any,
        max_tokens: int = 80000,
        summary_prompt: str | None = None,
        keep_recent: int = _KEEP_RECENT_MESSAGES,
    ) -> None:
        self._agent = agent
        self._max_tokens = max_tokens
        self._summary_prompt = summary_prompt or DEFAULT_SUMMARY_PROMPT
        self._keep_recent = keep_recent
        self._cached_summary: str | None = None
        self._last_summarized_count: int = 0

    def apply_transform(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """执行消息转换：超token则压缩，否则直接返回"""
        total_tokens = _estimate_total_tokens(messages)
        threshold = self._max_tokens - _SUMMARY_OUTPUT_BUDGET

        if total_tokens < threshold:
            return messages

        logger.info(
            "AutoCompact 触发：%d token ≥ %d 阈值，开始总结...",
            total_tokens, threshold
        )
        return self._do_compact(messages)

    def get_logs(self, pre: list[dict[str, Any]], post: list[dict[str, Any]]) -> tuple[str, bool]:
        """返回压缩日志：token变化"""
        pre_tok = _estimate_total_tokens(pre)
        post_tok = _estimate_total_tokens(post)
        if post_tok < pre_tok:
            return f"AutoCompact: {pre_tok} → {post_tok} token (节省 {pre_tok - post_tok})", True
        return "AutoCompact: 未执行压缩", False

    def _do_compact(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """执行压缩：生成摘要 → 重构消息列表"""
        summary = self._generate_summary(messages)
        if not summary:
            logger.warning("AutoCompact：LLM 返回空摘要，跳过压缩")
            return messages
        return self._build_compressed(messages, summary)

    def _generate_summary(self, messages: list[dict[str, Any]]) -> str:
        """核心方法：调用 AG2 内置 _reflection_with_llm 生成对话总结"""
        try:
            return self._agent._reflection_with_llm(
                prompt=self._summary_prompt,
                messages=messages,
                llm_agent=self._agent
            ) or ""
        except Exception:
            logger.warning("AutoCompact：LLM 总结失败", exc_info=True)
            return ""

    def _build_compressed(
        self,
        messages: list[dict[str, Any]],
        summary: str
    ) -> list[dict[str, Any]]:
        """
        构建压缩后的消息列表：
        1. 保留 system 消息
        2. 插入总结
        3. 保留最近 N 条原文
        """
        result = []

        # 保留系统提示
        if messages and messages[0].get("role") == "system":
            result.append(copy.deepcopy(messages[0]))
            messages = messages[1:]

        # 插入压缩总结
        result.append({
            "role": "user",
            "content": "[Context Summary — earlier conversation has been compressed]\n\n" + summary
        })

        # 保留最近消息原文
        tail = messages[-self._keep_recent:] if len(messages) > self._keep_recent else messages
        result.extend(copy.deepcopy(tail))

        logger.info(
            "AutoCompact 完成：%d 条消息 → %d 条消息，约 %d token",
            len(messages) + 1, len(result), _estimate_total_tokens(result)
        )
        return result