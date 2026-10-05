import unittest

from src.core.services.course.course_document_segmentation_service import (
    CourseDocumentSegmentationService,
)


class _Config:
    def __init__(self):
        self.values = {
            "course_segmentation.enabled": True,
            "course_segmentation.minimum_document_characters": 100,
            "course_segmentation.target_chunk_characters": 80,
            "course_segmentation.maximum_chunk_characters": 140,
            "course_segmentation.minimum_chunk_characters": 20,
            "course_segmentation.heading_maximum_characters": 60,
        }

    def require(self, key):
        return self.values[key]


class CourseAutomaticSegmentationTests(unittest.TestCase):
    def setUp(self):
        self.service = CourseDocumentSegmentationService(_Config())

    def test_long_course_document_is_split_into_sections_and_chunks(self):
        text = (
            "مقدمه\n\n"
            "هوش مصنوعی در سامانه‌های جدید برای تحلیل داده استفاده می‌شود. "
            "کیفیت داده و ارزیابی مدل بر نتیجه اثر دارند.\n\n"
            "پردازش زبان طبیعی\n\n"
            "پردازش زبان طبیعی برای تحلیل متن فارسی استفاده می‌شود. "
            "نرمال‌سازی متن و استخراج عبارت کلیدی از مراحل مهم هستند.\n\n"
            "حریم خصوصی\n\n"
            "حریم خصوصی و جلوگیری از نگهداری غیرضروری متن خام اهمیت دارد."
        )
        result = self.service.segment(
            (
                {
                    "document_id": "doc-1",
                    "text": text,
                    "metadata": {},
                },
            )
        )

        self.assertEqual(result.mode, "automatic")
        self.assertGreaterEqual(result.section_count, 3)
        self.assertGreaterEqual(result.chunk_count, 3)
        self.assertTrue(all(item.section_id for item in result.segments))
        self.assertTrue(all(item.chunk_id for item in result.segments))
        self.assertFalse(any(item.text.strip() == "مقدمه" for item in result.segments))

    def test_explicit_section_metadata_is_preserved_without_fabricating_chunks(self):
        result = self.service.segment(
            (
                {
                    "document_id": "doc-1",
                    "text": "متن بخش اول",
                    "metadata": {"section_id": "s1"},
                },
                {
                    "document_id": "doc-2",
                    "text": "متن بخش دوم",
                    "metadata": {"section_id": "s2"},
                },
            )
        )

        self.assertEqual(result.mode, "explicit")
        self.assertEqual([item.section_id for item in result.segments], ["s1", "s2"])
        self.assertTrue(all(item.chunk_id is None for item in result.segments))

    def test_short_document_keeps_legacy_no_boundary_behavior(self):
        result = self.service.segment(
            (
                {
                    "document_id": "doc-1",
                    "text": "یک متن کوتاه برای تحلیل.",
                    "metadata": {},
                },
            )
        )
        self.assertEqual(result.mode, "not_required")
        self.assertEqual(result.section_count, 0)
        self.assertEqual(result.chunk_count, 0)
        self.assertIsNone(result.segments[0].section_id)
        self.assertIsNone(result.segments[0].chunk_id)


if __name__ == "__main__":
    unittest.main()
