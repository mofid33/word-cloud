from __future__ import annotations

import os
import unittest

from src.core.services.analysis.analysis_processor_service import AnalysisProcessorService
from src.core.services.course.course_analysis_service import CourseAnalysisService
from src.core.services.media.media_analysis_service import MediaAnalysisService
from src.core.services.soldier_concern.soldier_concern_analysis_service import (
    SoldierConcernAnalysisService,
)
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve


class ProfileDiscoveryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_di_state()
        bootstrap_di()

    def test_phase10_services_resolve_through_discovery(self) -> None:
        course = resolve(CourseAnalysisService)
        soldier = resolve(SoldierConcernAnalysisService)
        media = resolve(MediaAnalysisService)
        processor = resolve(AnalysisProcessorService)

        self.assertIsInstance(course, CourseAnalysisService)
        self.assertIsInstance(soldier, SoldierConcernAnalysisService)
        self.assertIsInstance(media, MediaAnalysisService)
        self.assertIs(processor._course.__class__, CourseAnalysisService)
        self.assertIs(processor._soldier.__class__, SoldierConcernAnalysisService)
        self.assertIs(processor._media.__class__, MediaAnalysisService)


@unittest.skipUnless(
    os.getenv("RUN_PHASE8_MODEL_INTEGRATION") == "1",
    "set RUN_PHASE8_MODEL_INTEGRATION=1 with configured models available",
)
class RealModelProfileIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_di_state()
        bootstrap_di()

    async def test_phase6_to_phase10_course_real_model_pipeline(self) -> None:
        service = resolve(CourseAnalysisService)
        result = await service.analyze_async([
            {
                "document_id": "c1",
                "text": "هوش مصنوعی و یادگیری ماشین در تحلیل داده کاربرد دارند",
                "metadata": {"section_id": "s1", "chunk_id": "ch1"},
            }
        ])
        self.assertEqual(result.profile, "COURSE")
        self.assertTrue(result.keywords)
        self.assertTrue(result.topics)
        self.assertEqual(
            [item["document_id"] for item in result.profile_result["topic_timeline"]],
            ["c1"],
        )

    async def test_phase6_to_phase10_soldier_real_model_pipeline(self) -> None:
        service = resolve(SoldierConcernAnalysisService)
        result = await service.analyze_async([
            {"document_id": "s1", "text": "کیفیت اینترنت پایین است", "metadata": {}},
            {"document_id": "s2", "text": "کیفیت اینترنت برای ما مهم است", "metadata": {}},
        ])
        self.assertEqual(result.profile, "SOLDIER_CONCERN")
        self.assertTrue(result.keywords)
        self.assertTrue(result.topics)
        self.assertTrue(
            all(
                document_id.startswith("sha256:")
                for topic in result.topics
                for document_id in topic.document_ids
            )
        )

    async def test_phase6_to_phase10_media_real_model_pipeline(self) -> None:
        service = resolve(MediaAnalysisService)
        result = await service.analyze_async([
            {
                "document_id": "p-old-1",
                "text": "اقتصاد دیجیتال و رسانه",
                "metadata": {
                    "role": "published_content",
                    "published_at": "2026-09-16T10:00:00+00:00",
                },
            },
            {
                "document_id": "p-old-2",
                "text": "اقتصاد دیجیتال و محتوای رسانه",
                "metadata": {
                    "role": "published_content",
                    "published_at": "2026-09-18T10:00:00+00:00",
                },
            },
            {
                "document_id": "p-new-1",
                "text": "هوش مصنوعی در اقتصاد دیجیتال",
                "metadata": {
                    "role": "published_content",
                    "published_at": "2026-09-24T10:00:00+00:00",
                },
            },
            {
                "document_id": "p-new-2",
                "text": "هوش مصنوعی در رسانه دیجیتال",
                "metadata": {
                    "role": "published_content",
                    "published_at": "2026-09-28T10:00:00+00:00",
                },
            },
            {
                "document_id": "a-old-1",
                "text": "مخاطبان درباره هزینه خدمات گفتگو می‌کنند",
                "metadata": {
                    "role": "audience_feedback",
                    "published_at": "2026-09-16T12:00:00+00:00",
                },
            },
            {
                "document_id": "a-old-2",
                "text": "مخاطبان درباره هزینه خدمات نظر می‌دهند",
                "metadata": {
                    "role": "audience_feedback",
                    "published_at": "2026-09-18T12:00:00+00:00",
                },
            },
            {
                "document_id": "a-new-1",
                "text": "مخاطبان درباره کیفیت اینترنت گفتگو می‌کنند",
                "metadata": {
                    "role": "audience_feedback",
                    "published_at": "2026-09-24T12:00:00+00:00",
                },
            },
            {
                "document_id": "a-new-2",
                "text": "کیفیت اینترنت برای مخاطبان مهم است",
                "metadata": {
                    "role": "audience_feedback",
                    "published_at": "2026-09-28T12:00:00+00:00",
                },
            },
        ])
        self.assertEqual(result.profile, "MEDIA")
        self.assertTrue(result.profile_result["role_separation"])
        self.assertTrue(result.topics)
        topic_ids = {topic.topic_id for topic in result.topics}
        for role in ("published_content", "audience_feedback"):
            role_payload = result.profile_result["roles"][role]
            self.assertTrue(role_payload["topics"])
            self.assertTrue(role_payload["trend"]["available"])
            self.assertTrue(role_payload["trend"]["trends"])
            self.assertTrue(
                all(
                    item["topic_id"] in topic_ids
                    for item in role_payload["trend"]["trends"]
                )
            )



if __name__ == "__main__":
    unittest.main()
