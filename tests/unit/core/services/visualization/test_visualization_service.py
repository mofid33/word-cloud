from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from src.core.services.visualization.providers.visualization_renderer import (
    RenderedVisualization,
)
from src.core.services.visualization.visualization_service import (
    VisualizationFormatError,
    VisualizationNotFoundError,
    VisualizationService,
    VisualizationTopicNotFoundError,
    VisualizationUnavailableError,
)


@dataclass
class _Keyword:
    text: str
    canonical_text: str
    rank: int
    final_score: float


@dataclass
class _TopicKeywordLink:
    keyword: _Keyword
    rank: int
    relevance_score: float


@dataclass
class _Topic:
    id: str
    metadata_json: dict
    keyword_links: list[_TopicKeywordLink]


class _Analysis:
    def __init__(
        self,
        *,
        status: str,
        keywords: list[_Keyword],
        topics: list[_Topic] | None = None,
    ):
        self.status = status
        self.keywords = keywords
        self.topics = list(topics or [])

    @property
    def documents(self):
        raise AssertionError("Visualization must never access raw documents")


class _Repository:
    def __init__(self, analysis):
        self.analysis = analysis
        self.requested_id = None

    async def get_visualization_source_by_id_async(self, analysis_id: str):
        self.requested_id = analysis_id
        return self.analysis


    async def get_topic_visualization_source_by_id_async(self, analysis_id: str):
        self.requested_id = analysis_id
        return self.analysis


class _Renderer:
    def __init__(self):
        self.last_keywords = None
        self.last_format = None

    def render_png(self, keywords):
        self.last_keywords = keywords
        self.last_format = "png"
        return RenderedVisualization(b"png", "image/png")

    def render_svg(self, keywords):
        self.last_keywords = keywords
        self.last_format = "svg"
        return RenderedVisualization(b"svg", "image/svg+xml")


class _Settings:
    maximum_words = 2
    maximum_concurrent_renders = 2


class VisualizationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_result_uses_final_score_rank_and_limit(self) -> None:
        analysis = _Analysis(
            status="completed",
            keywords=[
                _Keyword("سوم", "سوم", 3, 0.3),
                _Keyword("اول", "اول", 1, 0.9),
                _Keyword("دوم", "دوم", 2, 0.6),
            ],
        )
        repository = _Repository(analysis)
        renderer = _Renderer()
        service = VisualizationService(repository, renderer, _Settings())

        result = await service.render_async("analysis-1", "PNG")

        self.assertEqual(result.media_type, "image/png")
        self.assertEqual(renderer.last_format, "png")
        self.assertEqual(
            [(item.text, item.rank, item.weight) for item in renderer.last_keywords],
            [("اول", 1, 0.9), ("دوم", 2, 0.6)],
        )
        self.assertEqual(repository.requested_id, "analysis-1")

    async def test_topic_result_uses_persisted_relevance_rank_and_logical_topic_id(self) -> None:
        first = _Keyword("امنیت روانی", "امنیت روانی", 1, 0.95)
        second = _Keyword("حمایت اجتماعی", "حمایت اجتماعی", 2, 0.80)
        third = _Keyword("خدمات رفاهی", "خدمات رفاهی", 3, 0.70)
        analysis = _Analysis(
            status="completed",
            keywords=[],
            topics=[
                _Topic(
                    id="database-topic-id",
                    metadata_json={"logical_topic_id": "topic-welfare"},
                    keyword_links=[
                        _TopicKeywordLink(third, 3, 0.55),
                        _TopicKeywordLink(first, 1, 0.98),
                        _TopicKeywordLink(second, 2, 0.81),
                    ],
                )
            ],
        )
        repository = _Repository(analysis)
        renderer = _Renderer()
        service = VisualizationService(repository, renderer, _Settings())

        result = await service.render_topic_async(
            "analysis-topic",
            "topic-welfare",
            "svg",
        )

        self.assertEqual(result.media_type, "image/svg+xml")
        self.assertEqual(renderer.last_format, "svg")
        self.assertEqual(
            [(item.text, item.rank, item.weight) for item in renderer.last_keywords],
            [("امنیت روانی", 1, 0.98), ("حمایت اجتماعی", 2, 0.81)],
        )
        self.assertEqual(repository.requested_id, "analysis-topic")

    async def test_unknown_topic_is_not_found(self) -> None:
        analysis = _Analysis(
            status="completed",
            keywords=[],
            topics=[],
        )
        service = VisualizationService(_Repository(analysis), _Renderer(), _Settings())

        with self.assertRaises(VisualizationTopicNotFoundError):
            await service.render_topic_async("analysis", "missing-topic", "png")

    async def test_topic_without_positive_relevance_is_unavailable(self) -> None:
        keyword = _Keyword("موضوع", "موضوع", 1, 0.9)
        analysis = _Analysis(
            status="completed",
            keywords=[],
            topics=[
                _Topic(
                    id="topic-db",
                    metadata_json={"logical_topic_id": "topic-empty"},
                    keyword_links=[_TopicKeywordLink(keyword, 1, 0.0)],
                )
            ],
        )
        service = VisualizationService(_Repository(analysis), _Renderer(), _Settings())

        with self.assertRaises(VisualizationUnavailableError) as context:
            await service.render_topic_async("analysis", "topic-empty", "png")
        self.assertEqual(
            context.exception.code,
            "analysis_topic_visualization_empty",
        )

    async def test_renderer_is_offloaded_from_event_loop(self) -> None:
        analysis = _Analysis(
            status="completed",
            keywords=[_Keyword("پردازش زبان فارسی", "پردازش زبان فارسی", 1, 1.0)],
        )
        renderer = _Renderer()
        service = VisualizationService(_Repository(analysis), renderer, _Settings())

        rendered = RenderedVisualization(b"threaded", "image/png")
        with patch(
            "src.core.services.visualization.visualization_service.to_thread",
            new=AsyncMock(return_value=rendered),
        ) as to_thread_mock:
            result = await service.render_async("analysis-thread", "png")

        self.assertIs(result, rendered)
        to_thread_mock.assert_awaited_once()
        args = to_thread_mock.await_args.args
        self.assertEqual(args[0], renderer.render_png)
        self.assertEqual(tuple(item.text for item in args[1]), ("پردازش زبان فارسی",))

    async def test_order_is_deterministic_for_equal_rank_input(self) -> None:
        analysis = _Analysis(
            status="completed",
            keywords=[
                _Keyword("ب", "ب", 1, 0.8),
                _Keyword("الف", "الف", 1, 0.8),
            ],
        )
        renderer = _Renderer()
        service = VisualizationService(_Repository(analysis), renderer, _Settings())

        await service.render_async("analysis-2", "svg")

        self.assertEqual([item.text for item in renderer.last_keywords], ["الف", "ب"])

    async def test_non_positive_or_non_finite_scores_are_not_visualized(self) -> None:
        analysis = _Analysis(
            status="completed",
            keywords=[
                _Keyword("zero", "zero", 1, 0.0),
                _Keyword("nan", "nan", 2, float("nan")),
            ],
        )
        service = VisualizationService(_Repository(analysis), _Renderer(), _Settings())

        with self.assertRaisesRegex(
            VisualizationUnavailableError,
            "no visualizable keywords",
        ):
            await service.render_async("analysis-3", "png")

    async def test_unknown_analysis(self) -> None:
        service = VisualizationService(_Repository(None), _Renderer(), _Settings())
        with self.assertRaises(VisualizationNotFoundError):
            await service.render_async("missing", "png")

    async def test_pending_processing_and_failed_are_unavailable(self) -> None:
        for state, expected_code in (
            ("pending", "analysis_visualization_not_ready"),
            ("processing", "analysis_visualization_not_ready"),
            ("failed", "analysis_failed"),
        ):
            with self.subTest(state=state):
                service = VisualizationService(
                    _Repository(_Analysis(status=state, keywords=[])),
                    _Renderer(),
                    _Settings(),
                )
                with self.assertRaises(VisualizationUnavailableError) as context:
                    await service.render_async("analysis", "png")
                self.assertEqual(context.exception.code, expected_code)

    async def test_invalid_format_is_rejected_before_repository_access(self) -> None:
        repository = _Repository(None)
        service = VisualizationService(repository, _Renderer(), _Settings())
        with self.assertRaises(VisualizationFormatError):
            await service.render_async("analysis", "pdf")
        self.assertIsNone(repository.requested_id)

    async def test_raw_document_marker_is_never_read(self) -> None:
        analysis = _Analysis(
            status="completed",
            keywords=[_Keyword("خروجی امن", "خروجی امن", 1, 1.0)],
        )
        service = VisualizationService(_Repository(analysis), _Renderer(), _Settings())
        await service.render_async("soldier", "svg")


if __name__ == "__main__":
    unittest.main()
