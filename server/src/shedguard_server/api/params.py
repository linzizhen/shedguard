"""查询参数的公共解析。"""

from __future__ import annotations

from datetime import date

from shedguard_server.errors import InvalidRequestError


def parse_day(raw: str, name: str) -> date:
    """严格解析 ``YYYY-MM-DD``。

    ``date.fromisoformat`` 也接受 ``2026-1-1`` 这类非定宽写法，回显时会变成
    另一种字符串，所以这里额外要求解析结果与输入逐字相同。
    """
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidRequestError(f"{name} 必须是 YYYY-MM-DD: {raw!r}") from exc
    if parsed.isoformat() != raw:
        raise InvalidRequestError(f"{name} 必须是 YYYY-MM-DD: {raw!r}")
    return parsed
