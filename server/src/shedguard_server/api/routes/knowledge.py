"""护理知识库接口：静态内容，不走数据库。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from shedguard_server.domain.knowledge import TOPICS, TOPICS_BY_SLUG
from shedguard_server.errors import NotFoundError

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def _serialize_topic(topic: Any) -> dict[str, Any]:
    return {
        "slug": topic.slug,
        "title": topic.title,
        "summary": topic.summary,
    }


def _serialize_topic_full(topic: Any) -> dict[str, Any]:
    return {
        "slug": topic.slug,
        "title": topic.title,
        "summary": topic.summary,
        "sections": [
            {"heading": heading, "bullets": list(bullets)}
            for heading, bullets in topic.sections
        ],
    }


@router.get("/topics")
def list_topics() -> dict[str, Any]:
    return {"items": [_serialize_topic(t) for t in TOPICS]}


@router.get("/topics/{slug}")
def get_topic(slug: str) -> dict[str, Any]:
    topic = TOPICS_BY_SLUG.get(slug)
    if topic is None:
        raise NotFoundError(f"知识话题不存在: {slug}")
    return _serialize_topic_full(topic)
