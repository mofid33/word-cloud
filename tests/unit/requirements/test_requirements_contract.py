import json
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]

CONTRACT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "requirements"
    / "requirements_contract.json"
)

SPECIFICATION_PATH = (
    PROJECT_ROOT
    / "docs"
    / "requirements"
    / "requirements_specification.md"
)


class RequirementsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CONTRACT_PATH.exists():
            raise AssertionError(
                f"Requirements contract does not exist: {CONTRACT_PATH}"
            )

        if not SPECIFICATION_PATH.exists():
            raise AssertionError(
                f"Requirements specification does not exist: "
                f"{SPECIFICATION_PATH}"
            )

        with CONTRACT_PATH.open(
            "r",
            encoding="utf-8",
        ) as contract_file:
            cls.contract: dict[str, Any] = json.load(contract_file)

        cls.specification = SPECIFICATION_PATH.read_text(
            encoding="utf-8"
        )

    def test_phase_is_requirements_freeze(self) -> None:
        phase = self.contract["phase"]

        self.assertEqual(phase["number"], 1)
        self.assertEqual(phase["name"], "Requirements Freeze")
        self.assertEqual(phase["status"], "FROZEN")

    def test_product_is_json_first_semantic_analytics(self) -> None:
        product = self.contract["product"]

        self.assertEqual(
            product["name"],
            "Persian Semantic Text Analytics Service",
        )
        self.assertEqual(
            product["primary_output"],
            "structured_json",
        )
        self.assertFalse(
            product["wordcloud_is_primary_product"]
        )
        self.assertEqual(
            set(product["visualization_outputs"]),
            {"png", "svg"},
        )

    def test_exactly_three_primary_profiles_are_frozen(self) -> None:
        profiles = set(
            self.contract["product"]["supported_profiles"]
        )

        self.assertEqual(
            profiles,
            {
                "COURSE",
                "SOLDIER_CONCERN",
                "MEDIA",
            },
        )

    def test_architecture_layers_are_frozen(self) -> None:
        architecture = self.contract["architecture"]

        self.assertEqual(
            architecture["layers"],
            [
                "Host",
                "Application",
                "Core",
                "Infrastructure",
            ],
        )

    def test_dependency_flow_is_frozen(self) -> None:
        architecture = self.contract["architecture"]

        self.assertEqual(
            architecture["dependency_flow"],
            [
                "Controller",
                "Service",
                "Repository",
                "PsqlDbContext",
            ],
        )

        self.assertTrue(
            architecture["constructor_injection_required"]
        )
        self.assertTrue(
            architecture["thin_controller_required"]
        )

    def test_architecture_does_not_allow_extra_ceremony(self) -> None:
        architecture = self.contract["architecture"]

        self.assertFalse(
            architecture["unnecessary_interfaces_allowed"]
        )
        self.assertFalse(
            architecture[
                "extra_architectural_layers_allowed_without_explicit_request"
            ]
        )
        self.assertTrue(
            architecture["base_repository_for_generic_crud"]
        )
        self.assertFalse(
            architecture[
                "manual_provider_registration_when_discovery_exists"
            ]
        )

    def test_input_hard_limits_are_frozen(self) -> None:
        limits = self.contract["input"]["limits"]

        self.assertEqual(
            limits["max_documents_per_analysis"],
            5000,
        )
        self.assertEqual(
            limits["max_characters_per_document"],
            500000,
        )
        self.assertEqual(
            limits["max_total_characters_per_analysis"],
            10000000,
        )
        self.assertTrue(
            limits["configuration_driven"]
        )

    def test_execution_modes_are_supported(self) -> None:
        execution_modes = set(
            self.contract["input"]["execution_modes"]
        )

        self.assertEqual(
            execution_modes,
            {
                "auto",
                "sync",
                "async",
            },
        )

    def test_sync_threshold_is_frozen(self) -> None:
        execution = self.contract["execution"]
        threshold = execution["sync_threshold"]

        self.assertTrue(execution["supports_sync"])
        self.assertTrue(execution["supports_async"])
        self.assertTrue(execution["supports_auto"])

        self.assertEqual(
            threshold["max_documents"],
            20,
        )
        self.assertEqual(
            threshold["max_total_characters"],
            100000,
        )

        self.assertFalse(
            execution[
                "explicit_sync_above_threshold_allowed"
            ]
        )

    def test_worker_cannot_own_duplicate_business_logic(self) -> None:
        execution = self.contract["execution"]

        self.assertFalse(
            execution[
                "worker_may_duplicate_business_logic"
            ]
        )

        self.assertEqual(
            execution["large_corpus_flow"],
            [
                "FastAPI",
                "Create Analysis",
                "Queue",
                "Worker",
                "Core Services",
                "Repository",
                "Result",
            ],
        )

    def test_persian_processing_requires_separate_representations(
        self,
    ) -> None:
        persian_nlp = self.contract["persian_nlp"]

        self.assertTrue(
            persian_nlp[
                "separate_candidate_representation"
            ]
        )
        self.assertTrue(
            persian_nlp[
                "separate_embedding_representation"
            ]
        )

    def test_candidate_range_is_one_to_three_grams(self) -> None:
        candidate = self.contract["candidate_extraction"]

        self.assertEqual(
            candidate["minimum_ngram"],
            1,
        )
        self.assertEqual(
            candidate["maximum_ngram"],
            3,
        )
        self.assertTrue(
            candidate["noun_phrases_when_available"]
        )

    def test_semantic_providers_are_frozen(self) -> None:
        semantic = self.contract["semantic"]

        self.assertEqual(
            set(semantic["providers"]),
            {
                "EmbeddingProvider",
                "RerankerProvider",
                "TopicModelProvider",
            },
        )

        self.assertFalse(
            semantic["hard_coded_to_single_model"]
        )
        self.assertTrue(
            semantic[
                "final_model_requires_persian_benchmark"
            ]
        )
        self.assertFalse(
            semantic["heavy_models_loaded_per_request"]
        )

    def test_single_scoring_formula_is_forbidden(self) -> None:
        ranking = self.contract["ranking"]

        self.assertFalse(
            ranking[
                "single_formula_for_all_profiles"
            ]
        )
        self.assertTrue(
            ranking["weights_configurable"]
        )
        self.assertTrue(
            ranking[
                "production_weights_must_be_evaluated"
            ]
        )
        self.assertFalse(
            ranking[
                "production_weights_may_be_finalized_by_guess"
            ]
        )

    def test_course_profile_contract(self) -> None:
        course = self.contract["profiles"]["COURSE"]

        self.assertEqual(
            course["document_model"],
            "long_document_or_sections",
        )

        self.assertTrue(
            {
                "semantic_relevance",
                "frequency",
                "chunk_coverage",
                "section_coverage",
                "phrase_quality",
            }.issubset(
                set(course["scoring_signals"])
            )
        )

        self.assertIn(
            "topic_timeline",
            course["required_capabilities"],
        )
        self.assertIn(
            "section_coverage",
            course["required_capabilities"],
        )

    def test_soldier_concern_is_multi_document(self) -> None:
        soldier = self.contract[
            "profiles"
        ]["SOLDIER_CONCERN"]

        self.assertTrue(
            soldier[
                "each_concern_is_independent_document"
            ]
        )
        self.assertFalse(
            soldier[
                "merge_all_concerns_into_single_document"
            ]
        )
        self.assertTrue(
            soldier[
                "cross_document_repetition_is_positive_signal"
            ]
        )

    def test_soldier_raw_text_persistence_is_forbidden(
        self,
    ) -> None:
        soldier = self.contract[
            "profiles"
        ]["SOLDIER_CONCERN"]

        persistence = self.contract["persistence"]
        privacy = self.contract["privacy"]

        self.assertFalse(
            soldier["raw_text_persistence_allowed"]
        )
        self.assertTrue(
            persistence[
                "soldier_raw_text_persistence_forbidden"
            ]
        )
        self.assertFalse(
            privacy[
                "soldier_raw_text_storage_allowed"
            ]
        )
        self.assertFalse(
            privacy[
                "request_may_disable_soldier_privacy_policy"
            ]
        )

    def test_raw_text_may_not_be_logged(self) -> None:
        privacy = self.contract["privacy"]

        self.assertFalse(
            privacy["raw_text_logging_allowed"]
        )
        self.assertFalse(
            privacy[
                "raw_text_in_exception_message_allowed"
            ]
        )
        self.assertFalse(
            privacy[
                "raw_text_in_metric_labels_allowed"
            ]
        )
        self.assertFalse(
            privacy[
                "raw_text_in_tracing_attributes_allowed"
            ]
        )

    def test_media_roles_are_analyzed_separately(self) -> None:
        media = self.contract["profiles"]["MEDIA"]

        self.assertEqual(
            set(media["document_roles"]),
            {
                "published_content",
                "audience_feedback",
            },
        )
        self.assertTrue(
            media[
                "analyze_roles_separately_before_gap_analysis"
            ]
        )
        self.assertFalse(
            media["scraping_in_scope"]
        )

    def test_media_scoring_signals_are_profile_specific(
        self,
    ) -> None:
        media = self.contract["profiles"]["MEDIA"]

        expected_signals = {
            "mention_share",
            "semantic_relevance",
            "coverage",
            "normalized_engagement",
            "trend_growth",
            "recency",
        }

        self.assertEqual(
            set(media["scoring_signals"]),
            expected_signals,
        )

    def test_required_persistence_entities_are_frozen(
        self,
    ) -> None:
        persistence = self.contract["persistence"]

        self.assertTrue(persistence["required"])

        self.assertEqual(
            set(persistence["base_entities"]),
            {
                "WordCloudAnalysis",
                "AnalysisDocument",
                "AnalysisKeyword",
                "AnalysisTopic",
                "AnalysisTopicKeyword",
            },
        )

        self.assertFalse(
            persistence[
                "raw_text_persisted_by_default"
            ]
        )

    def test_required_evaluation_datasets_are_frozen(
        self,
    ) -> None:
        evaluation = self.contract["evaluation"]

        self.assertEqual(
            set(evaluation["gold_datasets"]),
            {
                "COURSE",
                "SOLDIER_CONCERN",
                "MEDIA",
            },
        )

    def test_required_ranking_metrics_are_frozen(
        self,
    ) -> None:
        evaluation = self.contract["evaluation"]

        self.assertEqual(
            set(evaluation["ranking_metrics"]),
            {
                "Precision@5",
                "Precision@10",
                "Recall@10",
                "NDCG@10",
            },
        )

    def test_topic_and_performance_metrics_are_required(
        self,
    ) -> None:
        evaluation = self.contract["evaluation"]

        self.assertEqual(
            set(evaluation["topic_metrics"]),
            {
                "Topic Coherence",
                "Topic Diversity",
            },
        )

        self.assertEqual(
            set(evaluation["performance_metrics"]),
            {
                "P50",
                "P95",
                "Throughput",
                "RAM",
                "VRAM",
            },
        )

        self.assertTrue(
            evaluation["human_evaluation_required"]
        )

    def test_final_model_and_weights_require_evaluation(
        self,
    ) -> None:
        evaluation = self.contract["evaluation"]

        self.assertTrue(
            evaluation[
                "final_model_selected_by_benchmark"
            ]
        )
        self.assertTrue(
            evaluation[
                "final_weights_selected_by_evaluation"
            ]
        )
        self.assertFalse(
            evaluation[
                "absolute_quality_thresholds_frozen_in_phase_1"
            ]
        )

    def test_regression_gate_is_defined(self) -> None:
        regression = self.contract[
            "evaluation"
        ]["regression_gate"]

        self.assertTrue(
            regression[
                "enabled_after_baseline_acceptance"
            ]
        )
        self.assertEqual(
            regression[
                "relative_max_regression"
            ],
            0.03,
        )
        self.assertEqual(
            set(regression["blocking_metrics"]),
            {
                "Precision@10",
                "NDCG@10",
            },
        )

    def test_laptop_and_production_share_one_codebase(
        self,
    ) -> None:
        environments = self.contract["environments"]

        self.assertTrue(
            environments["single_codebase"]
        )
        self.assertTrue(
            environments["laptop_supported"]
        )
        self.assertTrue(
            environments["laptop_cpu_ready"]
        )
        self.assertTrue(
            environments["production_supported"]
        )
        self.assertTrue(
            environments[
                "production_gpu_configurable"
            ]
        )
        self.assertFalse(
            environments[
                "separate_business_logic_for_cpu_and_gpu"
            ]
        )

    def test_analysis_lifecycle_is_frozen(self) -> None:
        statuses = set(
            self.contract[
                "analysis_lifecycle"
            ]["statuses"]
        )

        self.assertEqual(
            statuses,
            {
                "pending",
                "processing",
                "completed",
                "failed",
            },
        )

    def test_scraping_is_explicitly_out_of_scope(self) -> None:
        out_of_scope = set(
            self.contract["out_of_scope"]
        )

        self.assertIn(
            "web_scraping",
            out_of_scope,
        )
        self.assertIn(
            "social_media_scraping",
            out_of_scope,
        )
        self.assertIn(
            "content_acquisition_pipeline",
            out_of_scope,
        )

    def test_phase_one_does_not_create_runtime_implementation(
        self,
    ) -> None:
        definition_of_done = self.contract[
            "definition_of_done"
        ]

        self.assertFalse(
            definition_of_done[
                "runtime_implementation_created_in_phase_1"
            ]
        )

    def test_phase_one_definition_of_done_is_complete(
        self,
    ) -> None:
        definition_of_done = self.contract[
            "definition_of_done"
        ]

        required_true_flags = [
            "requirements_specification_exists",
            "machine_readable_contract_exists",
            "profiles_frozen",
            "input_limits_frozen",
            "sync_async_policy_frozen",
            "persistence_policy_frozen",
            "privacy_policy_frozen",
            "evaluation_requirements_frozen",
            "architecture_constraints_recorded",
            "deferred_decisions_recorded",
            "contract_tests_required",
        ]

        for flag in required_true_flags:
            with self.subTest(flag=flag):
                self.assertTrue(
                    definition_of_done[flag]
                )

        self.assertFalse(
            definition_of_done[
                "todos_allowed"
            ]
        )

    def test_specification_contains_no_unresolved_markers(
        self,
    ) -> None:
        normalized_lines = [
            line.strip().lower()
            for line in self.specification.splitlines()
        ]

        forbidden_markers = (
            "todo:",
            "todo -",
            "[todo]",
            "<todo>",
            "placeholder:",
            "placeholder -",
            "[placeholder]",
            "<placeholder>",
            "implement me",
            "not implemented",
        )

        unresolved_lines = [
            line
            for line in normalized_lines
            if any(
                line.startswith(marker)
                for marker in forbidden_markers
            )
        ]

        self.assertEqual(
            unresolved_lines,
            [],
            msg=(
                "Requirements specification contains unresolved "
                f"implementation markers: {unresolved_lines}"
            ),
        )

    def test_contract_contains_no_null_values(self) -> None:
        def assert_no_null(
            value: Any,
            path: str = "root",
        ) -> None:
            if value is None:
                self.fail(
                    f"Null value found at {path}"
                )

            if isinstance(value, dict):
                for key, child in value.items():
                    assert_no_null(
                        child,
                        f"{path}.{key}",
                    )

            elif isinstance(value, list):
                for index, child in enumerate(value):
                    assert_no_null(
                        child,
                        f"{path}[{index}]",
                    )

        assert_no_null(self.contract)

    def test_deferred_decisions_are_explicit(self) -> None:
        deferred = set(
            self.contract["deferred_decisions"]
        )

        required_deferred_decisions = {
            "exact_embedding_model",
            "exact_reranker_model",
            "exact_topic_model",
            "final_profile_weights",
            "exact_worker_technology",
            "exact_queue_technology",
            "exact_api_routes",
            "exact_http_error_codes",
        }

        self.assertTrue(
            required_deferred_decisions.issubset(
                deferred
            )
        )

    def test_analysis_input_contract_is_frozen(self) -> None:
        input_contract = self.contract["input"]

        self.assertEqual(
            set(input_contract["required_fields"]),
            {
                "analysis_type",
                "documents",
                "execution_mode",
            },
        )

        self.assertEqual(
            set(input_contract["optional_fields"]),
            {
                "reference",
                "options",
            },
        )


if __name__ == "__main__":
    unittest.main()