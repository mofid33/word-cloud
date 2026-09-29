from __future__ import annotations

import unittest

from src.core.services.topic.providers.topic_model_provider import TopicModelProvider
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import resolve
from src.infrastructure.providers.topic.semantic_agglomerative_topic_model_provider import (
    SemanticAgglomerativeTopicModelProvider,
)


class Phase11TopicDiscoveryTests(unittest.TestCase):
    def test_topic_provider_resolves_as_singleton_through_di(self):
        bootstrap_di()
        first = resolve(TopicModelProvider)
        second = resolve(TopicModelProvider)

        self.assertIsInstance(first, SemanticAgglomerativeTopicModelProvider)
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
