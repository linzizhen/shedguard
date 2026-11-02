"""请求标识生成：ULID 风格的 26 位 Crockford Base32 字符串。"""

import time

from shedguard_server.ids import new_request_id

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def test_length_and_alphabet() -> None:
    value = new_request_id()

    assert len(value) == 26
    assert set(value) <= set(ALPHABET)


def test_two_calls_differ() -> None:
    assert new_request_id() != new_request_id()


def test_sorted_by_time() -> None:
    first = new_request_id()
    time.sleep(0.002)
    second = new_request_id()

    assert first < second