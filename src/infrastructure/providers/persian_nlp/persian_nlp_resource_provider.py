from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@dataclass(frozen=True)
class PersianNlpResources:
    version: str
    general_stopwords: frozenset[str]
    domain_stopwords: Mapping[str, frozenset[str]]
    protected_terms: frozenset[str]
    synonyms: Mapping[str, str]
    canonical_terms: Mapping[str, str]
    lemmatization_enabled: bool
    pos_processing_enabled: bool


@inject
class PersianNlpResourceProvider:
    __di_singleton__ = True

    def __init__(self, config_reader: ConfigReader):
        self._config_reader = config_reader
        self._resources = self._load_resources()

    @property
    def resources(self) -> PersianNlpResources:
        return self._resources

    def _load_resources(self) -> PersianNlpResources:
        configured_path = str(
            self._config_reader.require("persian_nlp.resources.path")
        ).strip()
        if not configured_path:
            raise ValueError("persian_nlp.resources.path must not be empty")

        resource_path = Path(configured_path)
        if not resource_path.is_absolute():
            project_root = Path(__file__).resolve().parents[4]
            resource_path = project_root / resource_path

        if not resource_path.is_file():
            raise FileNotFoundError(
                f"Persian NLP resource file not found: {resource_path}"
            )

        with resource_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)

        if not isinstance(payload, dict):
            raise ValueError("Persian NLP resource root must be an object")

        version = self._required_string(payload, "version")
        general_stopwords = self._string_set(payload, "general_stopwords")
        protected_terms = self._string_set(payload, "protected_terms")
        domain_stopwords = self._domain_stopwords(payload)
        synonyms = self._string_mapping(payload, "synonyms")
        canonical_terms = self._string_mapping(payload, "canonical_terms")

        return PersianNlpResources(
            version=version,
            general_stopwords=frozenset(general_stopwords),
            domain_stopwords=MappingProxyType(
                {
                    key: frozenset(values)
                    for key, values in sorted(domain_stopwords.items())
                }
            ),
            protected_terms=frozenset(protected_terms),
            synonyms=MappingProxyType(dict(sorted(synonyms.items()))),
            canonical_terms=MappingProxyType(dict(sorted(canonical_terms.items()))),
            lemmatization_enabled=bool(
                self._config_reader.get("persian_nlp.lemmatization.enabled", False)
            ),
            pos_processing_enabled=bool(
                self._config_reader.get("persian_nlp.pos_processing.enabled", False)
            ),
        )

    @staticmethod
    def _required_string(payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Persian NLP resource '{key}' must be a non-empty string")
        return value.strip()

    @staticmethod
    def _string_set(payload: dict[str, object], key: str) -> set[str]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"Persian NLP resource '{key}' must be an array")
        result: set[str] = set()
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"Persian NLP resource '{key}' contains an invalid term"
                )
            result.add(item.strip())
        return result

    @staticmethod
    def _string_mapping(payload: dict[str, object], key: str) -> dict[str, str]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"Persian NLP resource '{key}' must be an object")
        result: dict[str, str] = {}
        for source, target in value.items():
            if (
                not isinstance(source, str)
                or not source.strip()
                or not isinstance(target, str)
                or not target.strip()
            ):
                raise ValueError(
                    f"Persian NLP resource '{key}' contains an invalid mapping"
                )
            result[source.strip()] = target.strip()
        return result

    @classmethod
    def _domain_stopwords(
        cls,
        payload: dict[str, object],
    ) -> dict[str, set[str]]:
        value = payload.get("domain_stopwords")
        if not isinstance(value, dict):
            raise ValueError(
                "Persian NLP resource 'domain_stopwords' must be an object"
            )

        result: dict[str, set[str]] = {}
        for domain, terms in value.items():
            if not isinstance(domain, str) or not domain.strip():
                raise ValueError("Persian NLP domain name must be a non-empty string")
            if not isinstance(terms, list):
                raise ValueError(
                    f"Persian NLP domain '{domain}' stopwords must be an array"
                )
            normalized_terms: set[str] = set()
            for term in terms:
                if not isinstance(term, str) or not term.strip():
                    raise ValueError(
                        f"Persian NLP domain '{domain}' contains an invalid stopword"
                    )
                normalized_terms.add(term.strip())
            result[domain.strip().upper()] = normalized_terms
        return result
