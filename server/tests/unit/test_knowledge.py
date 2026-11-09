"""护理知识库静态内容的完整性测试。"""

from __future__ import annotations

from shedguard_server.domain.knowledge import TOPICS, TOPICS_BY_SLUG

EXPECTED_SLUGS = (
    "overview",
    "environment",
    "feeding",
    "shedding-basics",
    "stuck-shed",
    "hydration",
)


class TestKnowledgeTopics:
    """话题清单与结构的完整性。"""

    def test_six_topics_in_expected_order(self) -> None:
        assert tuple(t.slug for t in TOPICS) == EXPECTED_SLUGS

    def test_slugs_are_unique(self) -> None:
        slugs = [t.slug for t in TOPICS]
        assert len(slugs) == len(set(slugs))

    def test_index_covers_all(self) -> None:
        assert set(TOPICS_BY_SLUG) == set(EXPECTED_SLUGS)

    def test_each_topic_has_content(self) -> None:
        for topic in TOPICS:
            assert topic.title, topic.slug
            assert topic.summary, topic.slug
            assert len(topic.sections) >= 2, topic.slug
            for heading, bullets in topic.sections:
                assert heading, f"{topic.slug}: 空标题"
                assert len(bullets) >= 2, f"{topic.slug}/{heading}: 要点太少"
                for bullet in bullets:
                    assert len(bullet) >= 4, f"{topic.slug}/{heading}: 空要点"

    def test_unknown_slug_is_absent(self) -> None:
        assert "nonsense" not in TOPICS_BY_SLUG

    def test_stuck_shed_mentions_vet(self) -> None:
        topic = TOPICS_BY_SLUG["stuck-shed"]
        text = "\n".join(b for _, bullets in topic.sections for b in bullets)
        assert "医生" in text

    def test_shedding_basics_mentions_interval(self) -> None:
        topic = TOPICS_BY_SLUG["shedding-basics"]
        text = "\n".join(b for _, bullets in topic.sections for b in bullets)
        assert "周" in text
