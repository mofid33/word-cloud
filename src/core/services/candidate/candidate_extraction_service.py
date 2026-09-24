from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.services.persian_text.persian_text_processor import (
    PersianTextProcessingResult,
    PersianToken,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


_MEANINGFUL_NUMERIC_COMPOUND_RE = re.compile(
    r"^[0-9۰-۹]+(?:[./,:٫٬-][0-9۰-۹]+)+$"
)
_PURE_NUMERIC_RE = re.compile(r"^[0-9۰-۹]+$")
_FUNCTION_POS = frozenset({"ADP", "CCONJ", "PRON"})


@dataclass(frozen=True)
class CandidateOccurrence:
    document_id: str
    text: str
    canonical_text: str
    ngram_size: int
    segment_index: int
    token_start: int
    token_end: int
    section_id: str | None
    chunk_id: str | None
    is_protected: bool
    contains_stopword: bool
    stopword_count: int
    pos_tags: tuple[str | None, ...]


@dataclass(frozen=True)
class CandidateDocument:
    document_id: str
    processing_result: PersianTextProcessingResult
    section_id: str | None = None
    chunk_id: str | None = None


@dataclass(frozen=True)
class CandidateExtractionConfig:
    minimum_ngram: int
    maximum_ngram: int
    maximum_phrase_characters: int
    filter_pure_numeric: bool
    preserve_four_digit_year: bool
    filter_stopword_unigrams: bool
    filter_edge_stopwords: bool
    reject_function_pos_unigrams: bool


@inject
class CandidateExtractionService:
    def __init__(self, config_reader: ConfigReader):
        self._config = self._load_config(config_reader)

    @property
    def config(self) -> CandidateExtractionConfig:
        return self._config

    def extract(
        self,
        document_id: str,
        processing_result: PersianTextProcessingResult,
        *,
        section_id: str | None = None,
        chunk_id: str | None = None,
    ) -> tuple[CandidateOccurrence, ...]:
        normalized_document_id = self._required_identifier(document_id, "document_id")
        normalized_section_id = self._optional_identifier(section_id, "section_id")
        normalized_chunk_id = self._optional_identifier(chunk_id, "chunk_id")
        tokens = processing_result.candidate_tokens
        if not tokens:
            return ()

        occurrences: list[CandidateOccurrence] = []
        for start in range(len(tokens)):
            for ngram_size in range(
                self._config.minimum_ngram,
                self._config.maximum_ngram + 1,
            ):
                end = start + ngram_size
                if end > len(tokens):
                    break
                span = tokens[start:end]
                if not self._same_segment(span):
                    break
                if not self._is_valid_span(span):
                    continue
                occurrences.append(
                    self._build_occurrence(
                        normalized_document_id,
                        span,
                        start=start,
                        section_id=normalized_section_id,
                        chunk_id=normalized_chunk_id,
                    )
                )

        return tuple(
            sorted(
                occurrences,
                key=lambda item: (
                    item.segment_index,
                    item.token_start,
                    item.ngram_size,
                    item.canonical_text,
                    item.text,
                ),
            )
        )

    def extract_documents(
        self,
        documents: tuple[CandidateDocument, ...],
    ) -> tuple[CandidateOccurrence, ...]:
        occurrences: list[CandidateOccurrence] = []
        for document in documents:
            occurrences.extend(
                self.extract(
                    document.document_id,
                    document.processing_result,
                    section_id=document.section_id,
                    chunk_id=document.chunk_id,
                )
            )
        return tuple(
            sorted(
                occurrences,
                key=lambda item: (
                    item.document_id,
                    item.segment_index,
                    item.token_start,
                    item.ngram_size,
                    item.canonical_text,
                    item.text,
                ),
            )
        )

    def _is_valid_span(self, span: tuple[PersianToken, ...]) -> bool:
        text = " ".join(token.text for token in span)
        if not text or len(text) > self._config.maximum_phrase_characters:
            return False

        fully_protected = all(token.is_protected for token in span)
        if fully_protected:
            return True

        if len(span) == 1:
            token = span[0]
            if self._config.filter_stopword_unigrams and token.is_stopword:
                return False
            if (
                self._config.reject_function_pos_unigrams
                and token.pos in _FUNCTION_POS
            ):
                return False
            if (
                self._config.filter_pure_numeric
                and self._is_pure_numeric_noise(token.text)
            ):
                return False
            return self._contains_meaningful_character(token.text)

        if self._config.filter_edge_stopwords:
            if span[0].is_stopword or span[-1].is_stopword:
                return False

        if not any(not token.is_stopword for token in span):
            return False

        return all(self._contains_meaningful_character(token.text) for token in span)

    def _build_occurrence(
        self,
        document_id: str,
        span: tuple[PersianToken, ...],
        *,
        start: int,
        section_id: str | None,
        chunk_id: str | None,
    ) -> CandidateOccurrence:
        text = " ".join(token.text for token in span)
        canonical_text = " ".join(
            token.text if token.is_protected else token.lemma
            for token in span
        )
        return CandidateOccurrence(
            document_id=document_id,
            text=text,
            canonical_text=canonical_text,
            ngram_size=len(span),
            segment_index=span[0].segment_index,
            token_start=start,
            token_end=start + len(span),
            section_id=section_id,
            chunk_id=chunk_id,
            is_protected=all(token.is_protected for token in span),
            contains_stopword=any(token.is_stopword for token in span),
            stopword_count=sum(1 for token in span if token.is_stopword),
            pos_tags=tuple(token.pos for token in span),
        )

    def _is_pure_numeric_noise(self, text: str) -> bool:
        if _MEANINGFUL_NUMERIC_COMPOUND_RE.fullmatch(text):
            return False
        if not _PURE_NUMERIC_RE.fullmatch(text):
            return False
        if self._config.preserve_four_digit_year:
            ascii_digits = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
            if len(ascii_digits) == 4:
                year = int(ascii_digits)
                if 1000 <= year <= 2999:
                    return False
        return True

    @staticmethod
    def _same_segment(span: tuple[PersianToken, ...]) -> bool:
        if not span:
            return False
        segment_index = span[0].segment_index
        return all(token.segment_index == segment_index for token in span)

    @staticmethod
    def _contains_meaningful_character(text: str) -> bool:
        return any(character.isalnum() for character in text)

    @staticmethod
    def _required_identifier(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_identifier(value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string when provided")
        return value.strip()

    @classmethod
    def _load_config(cls, config_reader: ConfigReader) -> CandidateExtractionConfig:
        minimum_ngram = cls._required_int(
            config_reader,
            "candidate_extraction.minimum_ngram",
            minimum=1,
        )
        maximum_ngram = cls._required_int(
            config_reader,
            "candidate_extraction.maximum_ngram",
            minimum=1,
        )
        if minimum_ngram != 1 or maximum_ngram != 3:
            raise ValueError(
                "candidate_extraction n-gram range must be exactly 1..3"
            )

        return CandidateExtractionConfig(
            minimum_ngram=minimum_ngram,
            maximum_ngram=maximum_ngram,
            maximum_phrase_characters=cls._required_int(
                config_reader,
                "candidate_extraction.maximum_phrase_characters",
                minimum=1,
            ),
            filter_pure_numeric=cls._required_bool(
                config_reader,
                "candidate_extraction.filter_pure_numeric",
            ),
            preserve_four_digit_year=cls._required_bool(
                config_reader,
                "candidate_extraction.preserve_four_digit_year",
            ),
            filter_stopword_unigrams=cls._required_bool(
                config_reader,
                "candidate_extraction.filter_stopword_unigrams",
            ),
            filter_edge_stopwords=cls._required_bool(
                config_reader,
                "candidate_extraction.filter_edge_stopwords",
            ),
            reject_function_pos_unigrams=cls._required_bool(
                config_reader,
                "candidate_extraction.reject_function_pos_unigrams",
            ),
        )

    @staticmethod
    def _required_bool(config_reader: ConfigReader, key: str) -> bool:
        value = config_reader.require(key)
        if not isinstance(value, bool):
            raise ValueError(f"Configuration '{key}' must be a boolean")
        return value

    @staticmethod
    def _required_int(
        config_reader: ConfigReader,
        key: str,
        *,
        minimum: int,
    ) -> int:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(
                f"Configuration '{key}' must be an integer >= {minimum}"
            )
        return value
