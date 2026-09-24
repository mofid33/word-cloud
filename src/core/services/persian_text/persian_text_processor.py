from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from src.infrastructure.di.inject import inject
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)


_ZWNJ = "\u200c"
_ARABIC_TO_PERSIAN = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "ٱ": "ا",
        "ـ": "",
        "‐": "-",
        "‑": "-",
        "٠": "۰",
        "١": "۱",
        "٢": "۲",
        "٣": "۳",
        "٤": "۴",
        "٥": "۵",
        "٦": "۶",
        "٧": "۷",
        "٨": "۸",
        "٩": "۹",
    }
)
_DIACRITIC_CODEPOINTS = {
    "\u0610", "\u0611", "\u0612", "\u0613", "\u0614", "\u0615",
    "\u0616", "\u0617", "\u0618", "\u0619", "\u061a", "\u064b",
    "\u064c", "\u064d", "\u064e", "\u064f", "\u0650", "\u0651",
    "\u0652", "\u0653", "\u0654", "\u0655", "\u0656", "\u0657",
    "\u0658", "\u0659", "\u065a", "\u065b", "\u065c", "\u065d",
    "\u065e", "\u065f", "\u0670", "\u06d6", "\u06d7", "\u06d8",
    "\u06d9", "\u06da", "\u06db", "\u06dc", "\u06df", "\u06e0",
    "\u06e1", "\u06e2", "\u06e3", "\u06e4", "\u06e7", "\u06e8",
    "\u06ea", "\u06eb", "\u06ec", "\u06ed",
}
_MULTI_SPACE_RE = re.compile(r"\s+")
_MULTI_ZWNJ_RE = re.compile(rf"{_ZWNJ}+")
_ZWNJ_RIGHT_SPACE_RE = re.compile(rf"(?<=\w){_ZWNJ}\s+")
_ZWNJ_LEFT_SPACE_RE = re.compile(rf"\s+{_ZWNJ}(?=\w)")
_LATIN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[._+\-][A-Za-z0-9]+)*$")
_NUMBER_RE = re.compile(r"^[0-9۰-۹]+(?:[./,:٫٬-][0-9۰-۹]+)*$")

_ADPOSITIONS = frozenset({
    "از", "به", "با", "برای", "در", "بر", "تا", "بی", "بدون", "روی", "زیر",
})
_CONJUNCTIONS = frozenset({"و", "یا", "اما", "ولی", "که", "اگر", "تا"})
_PRONOUNS = frozenset({
    "من", "تو", "او", "ما", "شما", "آنها", "ایشان", "این", "آن", "خود",
})
_COMMON_VERBS = frozenset({
    "است", "هست", "بود", "شد", "شود", "شده", "کرد", "کند", "کرده",
    "داشت", "دارد", "دارند", "رفت", "رفتند", "رفتیم", "رفتید", "رفتم",
    "آمد", "آمدند", "آمدیم", "آمدید", "آمدم",
    "می‌شود", "می‌کند", "می‌کنند", "می‌توان", "می‌رود", "می‌روند",
})


@dataclass(frozen=True)
class PersianToken:
    text: str
    lemma: str
    pos: str | None
    segment_index: int
    is_stopword: bool
    is_protected: bool


@dataclass(frozen=True)
class PersianTextProcessingResult:
    normalized_text: str
    candidate_text: str
    embedding_text: str
    candidate_tokens: tuple[PersianToken, ...]
    embedding_tokens: tuple[str, ...]
    resource_version: str


@dataclass(frozen=True)
class _ScannedToken:
    text: str
    segment_index: int
    is_protected: bool = False


@inject
class PersianTextProcessor:
    def __init__(self, resource_provider: PersianNlpResourceProvider):
        self._resources = resource_provider.resources
        self._lemmatization_enabled = self._resources.lemmatization_enabled
        self._pos_enabled = self._resources.pos_processing_enabled
        self._protected_patterns = self._compile_term_patterns(
            self._resources.protected_terms
        )
        self._canonical_patterns = self._compile_mapping_patterns(
            self._resources.canonical_terms
        )
        self._synonym_patterns = self._compile_mapping_patterns(
            self._resources.synonyms
        )
        self._general_stopword_patterns = self._compile_term_patterns(
            self._resources.general_stopwords
        )
        self._domain_stopword_patterns = {
            domain: self._compile_term_patterns(terms)
            for domain, terms in self._resources.domain_stopwords.items()
        }

    def process(
        self,
        text: str,
        *,
        domain: str | None = None,
    ) -> PersianTextProcessingResult:
        normalized_text = self.normalize(text)
        if not normalized_text:
            return PersianTextProcessingResult(
                normalized_text="",
                candidate_text="",
                embedding_text="",
                candidate_tokens=(),
                embedding_tokens=(),
                resource_version=self._resources.version,
            )

        scanned = list(self._scan_tokens(normalized_text))
        protected = self._mark_protected(scanned)
        canonicalized = self._apply_mapping_patterns(
            protected,
            self._canonical_patterns,
        )
        canonicalized = self._apply_mapping_patterns(
            canonicalized,
            self._synonym_patterns,
        )
        canonicalized = self._mark_protected(canonicalized)

        stopword_indexes = self._collect_stopword_indexes(
            canonicalized,
            domain=domain,
        )

        candidate_tokens: list[PersianToken] = []
        embedding_tokens: list[str] = []
        for index, token in enumerate(canonicalized):
            lemma = (
                self._lemmatize(token.text)
                if self._lemmatization_enabled and not token.is_protected
                else token.text
            )
            pos = self._pos_tag(token.text) if self._pos_enabled else None
            is_stopword = index in stopword_indexes and not token.is_protected
            candidate_tokens.append(
                PersianToken(
                    text=token.text,
                    lemma=lemma,
                    pos=pos,
                    segment_index=token.segment_index,
                    is_stopword=is_stopword,
                    is_protected=token.is_protected,
                )
            )
            include_in_embedding = (
                not self._resources.embedding_remove_stopwords
                or not is_stopword
            )
            if include_in_embedding:
                embedding_tokens.append(
                    lemma if self._resources.embedding_use_lemmas else token.text
                )

        return PersianTextProcessingResult(
            normalized_text=normalized_text,
            candidate_text=" ".join(token.text for token in candidate_tokens),
            embedding_text=" ".join(embedding_tokens),
            candidate_tokens=tuple(candidate_tokens),
            embedding_tokens=tuple(embedding_tokens),
            resource_version=self._resources.version,
        )

    @classmethod
    def normalize(cls, text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text:
            return ""

        normalized = unicodedata.normalize("NFKC", text).translate(_ARABIC_TO_PERSIAN)
        output: list[str] = []
        for char in normalized:
            if char in _DIACRITIC_CODEPOINTS:
                continue
            if char == _ZWNJ:
                output.append(char)
                continue
            category = unicodedata.category(char)
            if category.startswith("C") or category.startswith("S"):
                output.append(" ")
                continue
            output.append(char)

        normalized = "".join(output)
        normalized = _MULTI_ZWNJ_RE.sub(_ZWNJ, normalized)
        normalized = _ZWNJ_RIGHT_SPACE_RE.sub(_ZWNJ, normalized)
        normalized = _ZWNJ_LEFT_SPACE_RE.sub(_ZWNJ, normalized)
        normalized = cls._sanitize_zwnj_boundaries(normalized)
        return _MULTI_SPACE_RE.sub(" ", normalized).strip()

    @classmethod
    def tokenize(cls, text: str) -> tuple[str, ...]:
        normalized = cls.normalize(text)
        return tuple(token.text for token in cls._scan_tokens(normalized))

    @staticmethod
    def _sanitize_zwnj_boundaries(text: str) -> str:
        chars = list(text)
        for index, char in enumerate(chars):
            if char != _ZWNJ:
                continue
            left = chars[index - 1] if index > 0 else ""
            right = chars[index + 1] if index + 1 < len(chars) else ""
            if (
                not PersianTextProcessor._is_word_char(left)
                or not PersianTextProcessor._is_word_char(right)
            ):
                chars[index] = " "
        return "".join(chars)

    @classmethod
    def _scan_tokens(cls, text: str) -> Iterable[_ScannedToken]:
        buffer: list[str] = []
        segment_index = 0

        def flush() -> _ScannedToken | None:
            if not buffer:
                return None
            value = "".join(buffer).strip(_ZWNJ)
            buffer.clear()
            if not value:
                return None
            return _ScannedToken(value, segment_index)

        for index, char in enumerate(text):
            if (
                cls._is_word_char(char)
                or char == _ZWNJ
                or cls._is_internal_connector(text, index)
            ):
                buffer.append(char)
                continue

            token = flush()
            if token is not None:
                yield token

            if char.isspace():
                continue
            if unicodedata.category(char).startswith("P"):
                segment_index += 1

        token = flush()
        if token is not None:
            yield token

    @staticmethod
    def _is_word_char(char: str) -> bool:
        if not char:
            return False
        return unicodedata.category(char)[0] in {"L", "N", "M"}

    @staticmethod
    def _is_decimal_digit(char: str) -> bool:
        return bool(char) and unicodedata.category(char) == "Nd"

    @staticmethod
    def _is_ascii_alphanumeric(char: str) -> bool:
        return bool(char) and char.isascii() and char.isalnum()

    @classmethod
    def _is_internal_connector(cls, text: str, index: int) -> bool:
        char = text[index]
        left = text[index - 1] if index > 0 else ""
        right = text[index + 1] if index + 1 < len(text) else ""
        if not cls._is_word_char(left) or not cls._is_word_char(right):
            return False

        if char in {"-", "_", "+"}:
            return True
        if char == ".":
            return (
                cls._is_decimal_digit(left) and cls._is_decimal_digit(right)
            ) or (
                cls._is_ascii_alphanumeric(left)
                and cls._is_ascii_alphanumeric(right)
            )
        if char in {"/", ":", ",", "٫", "٬"}:
            return cls._is_decimal_digit(left) and cls._is_decimal_digit(right)
        return False

    @classmethod
    def _normalize_resource_term(cls, term: str) -> tuple[str, ...]:
        return tuple(token.text for token in cls._scan_tokens(cls.normalize(term)))

    @classmethod
    def _compile_term_patterns(
        cls,
        terms: Iterable[str],
    ) -> tuple[tuple[str, ...], ...]:
        patterns = {
            pattern
            for term in terms
            if (pattern := cls._normalize_resource_term(term))
        }
        return tuple(sorted(patterns, key=lambda item: (-len(item), item)))

    @classmethod
    def _compile_mapping_patterns(
        cls,
        mapping: Mapping[str, str],
    ) -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
        patterns: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        for source, target in mapping.items():
            source_tokens = cls._normalize_resource_term(source)
            target_tokens = cls._normalize_resource_term(target)
            if source_tokens and target_tokens:
                patterns.append((source_tokens, target_tokens))
        return tuple(
            sorted(patterns, key=lambda item: (-len(item[0]), item[0], item[1]))
        )

    def _mark_protected(
        self,
        tokens: Sequence[_ScannedToken],
    ) -> list[_ScannedToken]:
        protected_indexes: set[int] = set()
        for pattern in self._protected_patterns:
            for start in self._find_pattern_matches(tokens, pattern):
                protected_indexes.update(range(start, start + len(pattern)))
        return [
            _ScannedToken(
                text=token.text,
                segment_index=token.segment_index,
                is_protected=token.is_protected or index in protected_indexes,
            )
            for index, token in enumerate(tokens)
        ]

    def _apply_mapping_patterns(
        self,
        tokens: Sequence[_ScannedToken],
        patterns: Sequence[tuple[tuple[str, ...], tuple[str, ...]]],
    ) -> list[_ScannedToken]:
        result: list[_ScannedToken] = []
        index = 0
        while index < len(tokens):
            current = tokens[index]
            if current.is_protected:
                result.append(current)
                index += 1
                continue

            replacement_applied = False
            for source, target in patterns:
                if not self._matches_at(tokens, index, source):
                    continue
                matched = tokens[index : index + len(source)]
                if any(token.is_protected for token in matched):
                    continue
                segment_index = matched[0].segment_index
                result.extend(
                    _ScannedToken(
                        text=value,
                        segment_index=segment_index,
                        is_protected=False,
                    )
                    for value in target
                )
                index += len(source)
                replacement_applied = True
                break

            if not replacement_applied:
                result.append(current)
                index += 1
        return result

    def _collect_stopword_indexes(
        self,
        tokens: Sequence[_ScannedToken],
        *,
        domain: str | None,
    ) -> set[int]:
        patterns = list(self._general_stopword_patterns)
        if domain:
            patterns.extend(
                self._domain_stopword_patterns.get(domain.strip().upper(), ())
            )
        patterns = sorted(set(patterns), key=lambda item: (-len(item), item))

        indexes: set[int] = set()
        for pattern in patterns:
            for start in self._find_pattern_matches(tokens, pattern):
                span = range(start, start + len(pattern))
                if any(tokens[position].is_protected for position in span):
                    continue
                indexes.update(span)
        return indexes

    @classmethod
    def _find_pattern_matches(
        cls,
        tokens: Sequence[_ScannedToken],
        pattern: Sequence[str],
    ) -> Iterable[int]:
        if not pattern:
            return ()
        return (
            index
            for index in range(0, len(tokens) - len(pattern) + 1)
            if cls._matches_at(tokens, index, pattern)
        )

    @staticmethod
    def _matches_at(
        tokens: Sequence[_ScannedToken],
        start: int,
        pattern: Sequence[str],
    ) -> bool:
        end = start + len(pattern)
        if end > len(tokens):
            return False
        span = tokens[start:end]
        if not span:
            return False
        segment = span[0].segment_index
        return (
            all(token.segment_index == segment for token in span)
            and tuple(token.text for token in span) == tuple(pattern)
        )

    @staticmethod
    def _lemmatize(token: str) -> str:
        if len(token) <= 3 or _NUMBER_RE.match(token) or _LATIN_RE.match(token):
            return token

        for suffix in ("‌هایی", "‌های", "‌ها"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                return token[: -len(suffix)].rstrip(_ZWNJ)

        return token

    @staticmethod
    def _pos_tag(token: str) -> str:
        if _NUMBER_RE.match(token):
            return "NUM"
        if _LATIN_RE.match(token):
            return "LATIN"
        if token in _ADPOSITIONS:
            return "ADP"
        if token in _CONJUNCTIONS:
            return "CCONJ"
        if token in _PRONOUNS:
            return "PRON"
        if token in _COMMON_VERBS or token.startswith(("می‌", "نمی‌")):
            return "VERB"
        return "X"
