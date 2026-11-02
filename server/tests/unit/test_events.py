"""蜕皮事件的领域校验：outcome 枚举、备注长度、日期格式。"""

from datetime import date

import pytest

from shedguard_server.domain.events import parse_event_date, validate_notes, validate_outcome
from shedguard_server.errors import InvalidRequestError


@pytest.mark.parametrize("outcome", ["completed", "partial", "stuck", "unknown"])
def test_accepts_known_outcomes(outcome: str) -> None:
    assert validate_outcome(outcome) == outcome


@pytest.mark.parametrize("outcome", ["", "COMPLETED", "done", "  completed  "])
def test_rejects_unknown_outcomes(outcome: str) -> None:
    with pytest.raises(InvalidRequestError):
        validate_outcome(outcome)


def test_notes_none_stays_none() -> None:
    assert validate_notes(None) is None


def test_notes_blank_becomes_none() -> None:
    assert validate_notes("   ") is None


def test_notes_are_trimmed() -> None:
    assert validate_notes("  尾部残留  ") == "尾部残留"


def test_notes_length_limit() -> None:
    with pytest.raises(InvalidRequestError, match="2000"):
        validate_notes("x" * 2001)


def test_notes_at_limit_accepted() -> None:
    text = "x" * 2000
    assert validate_notes(text) == text


def test_parse_event_date_accepts_iso_date() -> None:
    assert parse_event_date("2026-11-05") == date(2026, 11, 5)


@pytest.mark.parametrize("raw", ["2026-13-01", "20261105", "2026-11-05T00:00:00", ""])
def test_parse_event_date_rejects_garbage(raw: str) -> None:
    with pytest.raises(InvalidRequestError):
        parse_event_date(raw)