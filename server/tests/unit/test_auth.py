"""令牌生成与摘要的单元测试。"""

from __future__ import annotations

import re

from shedguard_server.infra.auth import hash_token, new_token


class TestNewToken:
    def test_returns_url_safe_string(self) -> None:
        token = new_token()
        assert re.fullmatch(r"[A-Za-z0-9_-]+", token)

    def test_tokens_are_unique(self) -> None:
        assert len({new_token() for _ in range(50)}) == 50


class TestHashToken:
    def test_is_stable_hex_digest(self) -> None:
        digest = hash_token("abc")
        assert digest == hash_token("abc")
        assert re.fullmatch(r"[0-9a-f]{64}", digest)

    def test_different_tokens_differ(self) -> None:
        assert hash_token("abc") != hash_token("abd")

    def test_blank_token_has_empty_hash(self) -> None:
        assert hash_token("") == ""
        assert hash_token("   ") == ""
