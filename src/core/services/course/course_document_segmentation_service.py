from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?؟])\s+")
_TERMINAL_PUNCTUATION = (".", "!", "?", "؟", "؛")


@dataclass(frozen=True)
class CourseSegment:
    source_document_id: str
    segment_document_id: str
    text: str
    section_id: str | None
    chunk_id: str | None
    order: int
    section_title: str | None
    generated: bool


@dataclass(frozen=True)
class CourseSegmentationResult:
    segments: tuple[CourseSegment, ...]
    mode: str
    version: str
    source_document_count: int
    section_count: int
    chunk_count: int


@dataclass(frozen=True)
class CourseSegmentationConfig:
    enabled: bool
    minimum_document_characters: int
    target_chunk_characters: int
    maximum_chunk_characters: int
    minimum_chunk_characters: int
    heading_maximum_characters: int


@inject
class CourseDocumentSegmentationService:
    VERSION = "course-segmentation-v1"

    def __init__(self, config_reader: ConfigReader):
        self._config = self._load_config(config_reader)

    @property
    def config(self) -> CourseSegmentationConfig:
        return self._config

    def segment(
        self,
        documents: tuple[dict[str, Any], ...],
    ) -> CourseSegmentationResult:
        if not documents:
            raise ValueError("COURSE segmentation requires at least one document")

        explicit_scope = self._has_explicit_scope(documents)
        if explicit_scope or not self._config.enabled:
            segments = tuple(
                CourseSegment(
                    source_document_id=document["document_id"],
                    segment_document_id=document["document_id"],
                    text=document["text"],
                    section_id=(document.get("metadata") or {}).get("section_id"),
                    chunk_id=(document.get("metadata") or {}).get("chunk_id"),
                    order=index,
                    section_title=None,
                    generated=False,
                )
                for index, document in enumerate(documents, start=1)
            )
            return CourseSegmentationResult(
                segments=segments,
                mode="explicit" if explicit_scope else "disabled",
                version=self.VERSION,
                source_document_count=len(documents),
                section_count=len({item.section_id for item in segments if item.section_id is not None}),
                chunk_count=len({item.chunk_id for item in segments if item.chunk_id is not None}),
            )

        automatic_required = any(
            len(document["text"]) >= self._config.minimum_document_characters
            for document in documents
        )
        if not automatic_required:
            segments = tuple(
                CourseSegment(
                    source_document_id=document["document_id"],
                    segment_document_id=document["document_id"],
                    text=document["text"],
                    section_id=None,
                    chunk_id=None,
                    order=index,
                    section_title=None,
                    generated=False,
                )
                for index, document in enumerate(documents, start=1)
            )
            return CourseSegmentationResult(
                segments=segments,
                mode="not_required",
                version=self.VERSION,
                source_document_count=len(documents),
                section_count=0,
                chunk_count=0,
            )

        generated: list[CourseSegment] = []
        order = 1
        for document in documents:
            if len(document["text"]) < self._config.minimum_document_characters:
                section_id = f"{document['document_id']}::section-001"
                chunk_id = f"{document['document_id']}::chunk-001"
                generated.append(
                    CourseSegment(
                        source_document_id=document["document_id"],
                        segment_document_id=chunk_id,
                        text=document["text"].strip(),
                        section_id=section_id,
                        chunk_id=chunk_id,
                        order=order,
                        section_title=None,
                        generated=True,
                    )
                )
                order += 1
                continue

            section_blocks = self._split_sections(document["text"])
            for section_index, (title, paragraphs) in enumerate(section_blocks, start=1):
                section_id = f"{document['document_id']}::section-{section_index:03d}"
                chunks = self._chunk_paragraphs(paragraphs)
                for chunk_index, chunk_text in enumerate(chunks, start=1):
                    chunk_id = f"{document['document_id']}::chunk-{section_index:03d}-{chunk_index:03d}"
                    generated.append(
                        CourseSegment(
                            source_document_id=document["document_id"],
                            segment_document_id=chunk_id,
                            text=chunk_text,
                            section_id=section_id,
                            chunk_id=chunk_id,
                            order=order,
                            section_title=title,
                            generated=True,
                        )
                    )
                    order += 1

        return CourseSegmentationResult(
            segments=tuple(generated),
            mode="automatic",
            version=self.VERSION,
            source_document_count=len(documents),
            section_count=len({item.section_id for item in generated}),
            chunk_count=len(generated),
        )

    def _split_sections(
        self,
        text: str,
    ) -> tuple[tuple[str | None, tuple[str, ...]], ...]:
        raw_paragraphs = tuple(
            paragraph.strip()
            for paragraph in _PARAGRAPH_SPLIT_RE.split(text.strip())
            if paragraph.strip()
        )
        if not raw_paragraphs:
            return ((None, (text.strip(),)),)

        sections: list[tuple[str | None, list[str]]] = []
        current_title: str | None = None
        current_paragraphs: list[str] = []

        for paragraph in raw_paragraphs:
            if self._is_heading(paragraph):
                if current_paragraphs:
                    sections.append((current_title, current_paragraphs))
                    current_paragraphs = []
                current_title = paragraph.strip()
                continue
            current_paragraphs.append(paragraph)

        if current_paragraphs:
            sections.append((current_title, current_paragraphs))
        elif current_title is not None:
            sections.append((current_title, [current_title]))

        if not sections:
            return ((None, raw_paragraphs),)

        return tuple(
            (title, tuple(paragraphs))
            for title, paragraphs in sections
        )

    def _chunk_paragraphs(self, paragraphs: tuple[str, ...]) -> tuple[str, ...]:
        units: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= self._config.maximum_chunk_characters:
                units.append(paragraph)
                continue
            units.extend(self._split_oversized_paragraph(paragraph))

        chunks: list[str] = []
        current: list[str] = []
        current_length = 0

        for unit in units:
            projected = current_length + (2 if current else 0) + len(unit)
            if current and projected > self._config.maximum_chunk_characters:
                chunks.append("\n\n".join(current).strip())
                current = []
                current_length = 0

            current.append(unit)
            current_length += (2 if current_length else 0) + len(unit)

            if current_length >= self._config.target_chunk_characters:
                chunks.append("\n\n".join(current).strip())
                current = []
                current_length = 0

        if current:
            tail = "\n\n".join(current).strip()
            if (
                chunks
                and len(tail) < self._config.minimum_chunk_characters
                and len(chunks[-1]) + 2 + len(tail)
                <= self._config.maximum_chunk_characters
            ):
                chunks[-1] = f"{chunks[-1]}\n\n{tail}"
            else:
                chunks.append(tail)

        return tuple(chunk for chunk in chunks if chunk)

    def _split_oversized_paragraph(self, paragraph: str) -> tuple[str, ...]:
        sentences = tuple(
            sentence.strip()
            for sentence in _SENTENCE_SPLIT_RE.split(paragraph.strip())
            if sentence.strip()
        )
        if len(sentences) <= 1:
            return tuple(
                paragraph[index:index + self._config.maximum_chunk_characters].strip()
                for index in range(0, len(paragraph), self._config.maximum_chunk_characters)
                if paragraph[index:index + self._config.maximum_chunk_characters].strip()
            )

        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            projected = f"{current} {sentence}".strip()
            if current and len(projected) > self._config.maximum_chunk_characters:
                chunks.append(current)
                current = sentence
            else:
                current = projected
        if current:
            chunks.append(current)
        return tuple(chunks)

    def _is_heading(self, paragraph: str) -> bool:
        value = " ".join(paragraph.split())
        if not value or "\n" in paragraph:
            return False
        if len(value) > self._config.heading_maximum_characters:
            return False
        if value.endswith(_TERMINAL_PUNCTUATION):
            return False

        word_count = len(value.split())
        if word_count == 0 or word_count > 12:
            return False

        if ":" in value and not value.endswith(":"):
            return False

        return True

    @staticmethod
    def _has_explicit_scope(documents: tuple[dict[str, Any], ...]) -> bool:
        section_present = [
            (document.get("metadata") or {}).get("section_id") is not None
            for document in documents
        ]
        chunk_present = [
            (document.get("metadata") or {}).get("chunk_id") is not None
            for document in documents
        ]
        return any(section_present) or any(chunk_present)

    @classmethod
    def _load_config(cls, config_reader: ConfigReader) -> CourseSegmentationConfig:
        enabled = cls._required_bool(
            config_reader,
            "course_segmentation.enabled",
        )
        minimum_document_characters = cls._required_int(
            config_reader,
            "course_segmentation.minimum_document_characters",
        )
        target_chunk_characters = cls._required_int(
            config_reader,
            "course_segmentation.target_chunk_characters",
        )
        maximum_chunk_characters = cls._required_int(
            config_reader,
            "course_segmentation.maximum_chunk_characters",
        )
        minimum_chunk_characters = cls._required_int(
            config_reader,
            "course_segmentation.minimum_chunk_characters",
        )
        heading_maximum_characters = cls._required_int(
            config_reader,
            "course_segmentation.heading_maximum_characters",
        )

        if minimum_chunk_characters > target_chunk_characters:
            raise ValueError(
                "course_segmentation.minimum_chunk_characters must be <= target_chunk_characters"
            )
        if target_chunk_characters > maximum_chunk_characters:
            raise ValueError(
                "course_segmentation.target_chunk_characters must be <= maximum_chunk_characters"
            )

        return CourseSegmentationConfig(
            enabled=enabled,
            minimum_document_characters=minimum_document_characters,
            target_chunk_characters=target_chunk_characters,
            maximum_chunk_characters=maximum_chunk_characters,
            minimum_chunk_characters=minimum_chunk_characters,
            heading_maximum_characters=heading_maximum_characters,
        )

    @staticmethod
    def _required_bool(config_reader: ConfigReader, key: str) -> bool:
        value = config_reader.require(key)
        if not isinstance(value, bool):
            raise ValueError(f"Configuration '{key}' must be a boolean")
        return value

    @staticmethod
    def _required_int(config_reader: ConfigReader, key: str) -> int:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Configuration '{key}' must be an integer > 0")
        return value
