from __future__ import annotations

import hashlib

from src.core.services.candidate.candidate_extraction_service import CandidateExtractionService
from src.core.services.course.course_analysis_service import CourseAnalysisService
from src.core.services.media.media_analysis_service import MediaAnalysisService
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.ranking.hybrid_ranking_service import HybridRankingService
from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.providers.reranker_provider import RerankerProvider
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.soldier_concern.soldier_concern_analysis_service import SoldierConcernAnalysisService
from src.core.services.statistical.statistical_analysis_service import StatisticalAnalysisService
from src.core.services.topic.topic_analysis_service import TopicAnalysisService
from src.core.services.trend.trend_analysis_service import TrendAnalysisService
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import PersianNlpResourceProvider
from src.infrastructure.providers.topic.semantic_agglomerative_topic_model_provider import SemanticAgglomerativeTopicModelProvider
from src.infrastructure.utils.config_reader import ConfigReader


_METADATA = SemanticProviderMetadata(
    provider="phase10-evaluation",
    provider_version="1",
    model_identifier="deterministic-synthetic-fixture",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase10-evaluation",
)


class DeterministicEmbedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append(
                tuple((value - 127.5) / 127.5 for value in digest[:24])
            )
        return tuple(vectors)


class DeterministicReranker(RerankerProvider):
    @property
    def metadata(self):
        return _METADATA

    async def rerank_async(self, query, candidates):
        return tuple(
            min(0.99, 0.30 + 0.20 * max(1, query.count(candidate)))
            for candidate in candidates
        )


def build_profile_services():
    config = ConfigReader(env_type="development")
    resource_provider = PersianNlpResourceProvider(config)
    processor = PersianTextProcessor(resource_provider)
    extractor = CandidateExtractionService(config)
    statistical = StatisticalAnalysisService(config)
    embedding = DeterministicEmbedding()
    semantic = SemanticAnalysisService(
        embedding,
        DeterministicReranker(),
        config,
    )
    ranking = HybridRankingService(embedding, config)
    topic_provider = SemanticAgglomerativeTopicModelProvider(embedding, config)
    topics = TopicAnalysisService(topic_provider, config)
    trends = TrendAnalysisService(config)
    return {
        "COURSE": CourseAnalysisService(
            processor,
            extractor,
            statistical,
            semantic,
            ranking,
            config,
            topic_analysis_service=topics,
        ),
        "SOLDIER_CONCERN": SoldierConcernAnalysisService(
            processor,
            extractor,
            statistical,
            semantic,
            ranking,
            config,
            topic_analysis_service=topics,
        ),
        "MEDIA": MediaAnalysisService(
            processor,
            extractor,
            statistical,
            semantic,
            ranking,
            config,
            topic_analysis_service=topics,
            trend_analysis_service=trends,
        ),
    }
