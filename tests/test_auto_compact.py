from __future__ import annotations

import infrastructure.context.auto_compact as auto_compact


def test_count_tokens_falls_back_when_tiktoken_encoding_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(auto_compact.tiktoken, "get_encoding", lambda _name: (_ for _ in ()).throw(ValueError("missing")))
    monkeypatch.setattr(auto_compact, "_ENCODER", None)

    count = auto_compact._count_tokens("abcdefgh")

    assert count == 2
    assert auto_compact._ENCODER is False
