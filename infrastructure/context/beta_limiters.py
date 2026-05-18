from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from autogen.beta.annotations import Context
from autogen.beta.events import BaseEvent, ModelRequest, ModelResponse, ToolResultsEvent
from autogen.beta.middleware.base import BaseMiddleware, LLMCall, MiddlewareFactory

from config.config import ContextConfig


@dataclass(frozen=True)
class _EventSegment:
    events: tuple[BaseEvent, ...]
    event_count: int
    char_count: int


def _segment_events(events: Sequence[BaseEvent]) -> list[_EventSegment]:
    segments: list[_EventSegment] = []
    index = 0
    while index < len(events):
        event = events[index]
        segment_events: list[BaseEvent] = [event]
        index += 1
        if isinstance(event, ModelResponse) and event.tool_calls.calls:
            while index < len(events) and isinstance(events[index], ToolResultsEvent):
                segment_events.append(events[index])
                index += 1
        segments.append(
            _EventSegment(
                events=tuple(segment_events),
                event_count=len(segment_events),
                char_count=sum(len(str(item)) for item in segment_events),
            )
        )
    return segments


def _flatten_segments(segments: Sequence[_EventSegment]) -> list[BaseEvent]:
    flattened: list[BaseEvent] = []
    for segment in segments:
        flattened.extend(segment.events)
    return flattened


def trim_beta_history_by_events(
    events: Sequence[BaseEvent],
    max_events: int,
) -> list[BaseEvent]:
    if max_events < 1:
        raise ValueError("max_events must be greater than 0")
    if len(events) <= max_events:
        return list(events)

    prefix: list[BaseEvent] = []
    tail_events = events
    if events and isinstance(events[0], ModelRequest):
        prefix = [events[0]]
        tail_events = events[1:]

    segments = _segment_events(tail_events)
    if not segments:
        return prefix

    remaining_budget = max(max_events - len(prefix), 0)
    kept: list[_EventSegment] = []
    used = 0

    for segment in reversed(segments):
        if not kept:
            kept.append(segment)
            used += segment.event_count
            continue
        if used + segment.event_count <= remaining_budget:
            kept.append(segment)
            used += segment.event_count
        else:
            break

    kept.reverse()
    return [*prefix, *_flatten_segments(kept)]


def trim_beta_history_by_chars(
    events: Sequence[BaseEvent],
    max_chars: int,
) -> list[BaseEvent]:
    if max_chars < 1:
        raise ValueError("max_chars must be greater than 0")

    event_lengths = [len(str(event)) for event in events]
    if sum(event_lengths) <= max_chars:
        return list(events)

    prefix: list[BaseEvent] = []
    prefix_chars = 0
    tail_events = events
    if events and isinstance(events[0], ModelRequest):
        prefix = [events[0]]
        prefix_chars = len(str(events[0]))
        tail_events = events[1:]

    segments = _segment_events(tail_events)
    if not segments:
        return prefix

    remaining_budget = max(max_chars - prefix_chars, 0)
    kept: list[_EventSegment] = []
    used = 0

    for segment in reversed(segments):
        if not kept:
            kept.append(segment)
            used += segment.char_count
            continue
        if used + segment.char_count <= remaining_budget:
            kept.append(segment)
            used += segment.char_count
        else:
            break

    kept.reverse()
    return [*prefix, *_flatten_segments(kept)]


class PairSafeHistoryLimiter(MiddlewareFactory):
    def __init__(self, max_events: int) -> None:
        if max_events < 1:
            raise ValueError("max_events must be greater than 0")
        self._max_events = max_events

    def __call__(self, event: BaseEvent, context: Context) -> BaseMiddleware:
        return _PairSafeHistoryLimiter(event, context, self._max_events)


class _PairSafeHistoryLimiter(BaseMiddleware):
    def __init__(self, event: BaseEvent, context: Context, max_events: int) -> None:
        super().__init__(event, context)
        self._max_events = max_events

    async def on_llm_call(
        self,
        call_next: LLMCall,
        events: Sequence[BaseEvent],
        context: Context,
    ) -> ModelResponse:
        return await call_next(trim_beta_history_by_events(events, self._max_events), context)


class PairSafeTokenLimiter(MiddlewareFactory):
    def __init__(self, max_tokens: int, chars_per_token: int = 4) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be greater than 0")
        if chars_per_token < 1:
            raise ValueError("chars_per_token must be greater than 0")
        self._max_chars = max_tokens // chars_per_token

    def __call__(self, event: BaseEvent, context: Context) -> BaseMiddleware:
        return _PairSafeTokenLimiter(event, context, self._max_chars)


class _PairSafeTokenLimiter(BaseMiddleware):
    def __init__(self, event: BaseEvent, context: Context, max_chars: int) -> None:
        super().__init__(event, context)
        self._max_chars = max_chars

    async def on_llm_call(
        self,
        call_next: LLMCall,
        events: Sequence[BaseEvent],
        context: Context,
    ) -> ModelResponse:
        return await call_next(trim_beta_history_by_chars(events, self._max_chars), context)


def build_beta_context_middleware(context_config: ContextConfig | None) -> list[MiddlewareFactory]:
    if not context_config or not context_config.enabled:
        return []
    middleware: list[MiddlewareFactory] = [PairSafeHistoryLimiter(context_config.max_messages)]
    if context_config.max_tokens > 0:
        middleware.append(PairSafeTokenLimiter(context_config.max_tokens))
    return middleware
