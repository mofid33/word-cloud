import json
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE_PATH = PROJECT_ROOT / "docs" / "architecture" / "architecture_contract.json"
SPEC_PATH = PROJECT_ROOT / "docs" / "architecture" / "technical_architecture.md"
REQUIREMENTS_PATH = PROJECT_ROOT / "docs" / "requirements" / "requirements_contract.json"


class ArchitectureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for path in (ARCHITECTURE_PATH, SPEC_PATH, REQUIREMENTS_PATH):
            if not path.exists():
                raise AssertionError(f"Required file does not exist: {path}")

        cls.architecture: dict[str, Any] = json.loads(
            ARCHITECTURE_PATH.read_text(encoding="utf-8")
        )
        cls.requirements: dict[str, Any] = json.loads(
            REQUIREMENTS_PATH.read_text(encoding="utf-8")
        )
        cls.specification = SPEC_PATH.read_text(encoding="utf-8")

    def test_phase_two_is_frozen(self) -> None:
        phase = self.architecture["phase"]
        self.assertEqual(phase, {
            "number": 2,
            "name": "Technical Architecture + Runtime Foundation",
            "status": "FROZEN",
            "based_on_phase": 1,
        })

    def test_phase_one_architecture_is_preserved(self) -> None:
        p1 = self.requirements["architecture"]
        p2 = self.architecture["architecture"]
        self.assertEqual(p2["layers"], p1["layers"])
        self.assertEqual(p2["dependency_flow"], p1["dependency_flow"])
        self.assertEqual(
            p2["constructor_injection_required"],
            p1["constructor_injection_required"],
        )
        self.assertEqual(
            p2["generic_crud_uses_base_repository"],
            p1["base_repository_for_generic_crud"],
        )
        self.assertFalse(p2["extra_architectural_layers_allowed"])
        self.assertFalse(
            p2["manual_provider_registration_when_discovery_exists"]
        )

    def test_planned_paths_follow_layer_conventions(self) -> None:
        files = self.architecture["files"]
        self.assertTrue(all(p.startswith("src/application/") for p in files["application"]))
        self.assertTrue(all(p.startswith("src/core/services/") for p in files["core"]))
        self.assertTrue(all(p.startswith("src/infrastructure/") for p in files["infrastructure"]))
        self.assertIn("src/application/analysis/analysis_controller.py", files["application"])
        self.assertIn("src/application/analysis/dtos/analysis_dto.py", files["application"])
        self.assertIn("src/infrastructure/repositories/base/base_repository.py", files["infrastructure"])

    def test_component_dependency_graph_is_complete_and_acyclic(self) -> None:
        components = self.architecture["components"]
        names = set(components)
        for name, component in components.items():
            for dependency in component["dependencies"]:
                self.assertIn(dependency, names, f"{name} -> {dependency} is undeclared")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                self.fail(f"Dependency cycle detected at {name}")
            visiting.add(name)
            for dependency in components[name]["dependencies"]:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

        for name in components:
            visit(name)

    def test_controller_is_thin(self) -> None:
        controller = self.architecture["components"]["AnalysisController"]
        self.assertEqual(controller["dependencies"], ["AnalysisService"])
        self.assertTrue(controller["inject"])
        self.assertFalse(controller["singleton"])
        self.assertIn("sqlalchemy_query", self.architecture["boundaries"]["application_forbidden"])
        self.assertIn("database_session", self.architecture["boundaries"]["application_forbidden"])

    def test_profile_services_share_common_engines(self) -> None:
        components = self.architecture["components"]
        shared = {
            "PersianTextProcessor",
            "CandidateExtractionService",
            "StatisticalAnalysisService",
            "SemanticAnalysisService",
            "HybridRankingService",
            "TopicAnalysisService",
        }
        for name in (
            "CourseAnalysisService",
            "SoldierConcernAnalysisService",
            "MediaAnalysisService",
        ):
            self.assertTrue(shared.issubset(set(components[name]["dependencies"])))
        self.assertIn("TrendAnalysisService", components["MediaAnalysisService"]["dependencies"])

    def test_execution_policy_uses_runtime_configuration(self) -> None:
        components = self.architecture["components"]
        self.assertEqual(
            components["AnalysisExecutionPolicyService"]["dependencies"],
            ["ConfigReader"],
        )

    def test_replaceable_provider_abstractions_are_limited(self) -> None:
        policy = self.architecture["provider_policy"]
        self.assertEqual(set(policy["abstract_contracts"]), {
            "EmbeddingProvider",
            "RerankerProvider",
            "TopicModelProvider",
            "AnalysisQueueProvider",
        })
        self.assertFalse(policy["per_feature_service_interfaces_allowed"])
        self.assertFalse(policy["per_feature_repository_interfaces_allowed"])
        self.assertFalse(policy["concrete_implementation_names_frozen"])

    def test_singleton_policy_matches_reference(self) -> None:
        policy = self.architecture["singleton_policy"]
        self.assertEqual(set(policy["required"]), {
            "ConfigReader",
            "VaultService",
            "PsqlDbContext",
        })
        components = self.architecture["components"]
        for name in policy["required"]:
            self.assertTrue(components[name]["singleton"])
        self.assertEqual(set(policy["non_singleton_by_default"]), {
            "controllers",
            "services",
            "repositories",
        })

    def test_repository_transaction_boundary_is_frozen(self) -> None:
        persistence = self.architecture["persistence"]
        self.assertEqual(
            set(persistence["base_entities"]),
            set(self.requirements["persistence"]["base_entities"]),
        )
        self.assertEqual(persistence["aggregate_repository"], "WordCloudAnalysisRepository")
        self.assertEqual(persistence["generic_crud_base"], "BaseRepository")
        self.assertEqual(
            persistence["result_transaction"],
            "one_repository_session_one_commit_for_complete_analysis_result_graph",
        )
        self.assertFalse(persistence["global_async_session_allowed"])
        self.assertFalse(persistence["engine_per_request_allowed"])

    def test_worker_reuses_same_core_processing_entrypoint(self) -> None:
        worker = self.architecture["worker_boundary"]
        flows = self.architecture["sequence_flows"]
        self.assertFalse(worker["business_logic_allowed"])
        self.assertEqual(worker["entrypoint"], "AnalysisProcessorService")
        self.assertFalse(worker["direct_profile_service_call_allowed"])
        self.assertIn("AnalysisProcessorService", flows["sync"])
        self.assertIn("AnalysisProcessorService", flows["async"])

    def test_soldier_privacy_is_not_weakened(self) -> None:
        privacy = self.architecture["privacy"]
        p1_privacy = self.requirements["privacy"]
        self.assertFalse(privacy["raw_text_logging_allowed"])
        self.assertFalse(privacy["raw_text_in_metrics_allowed"])
        self.assertFalse(privacy["raw_text_in_traces_allowed"])
        self.assertFalse(privacy["soldier_raw_text_database_persistence_allowed"])
        self.assertFalse(privacy["soldier_raw_text_durable_queue_payload_allowed"])
        self.assertEqual(privacy["soldier_async_transport"], "transient_non_durable_only")
        self.assertFalse(p1_privacy["raw_text_logging_allowed"])
        self.assertFalse(p1_privacy["soldier_raw_text_storage_allowed"])

    def test_deferred_phase_one_decisions_remain_deferred(self) -> None:
        p1_deferred = set(self.requirements["deferred_decisions"])
        p2_deferred = set(self.architecture["deferred_decisions_preserved"])
        self.assertTrue(p1_deferred.issubset(p2_deferred))
        self.assertIn("exact_api_routes", self.architecture["phase_ownership"]["3"])
        self.assertIn("queue_worker_technology", self.architecture["phase_ownership"]["12"])

    def test_definition_of_done_is_complete(self) -> None:
        definition = self.architecture["definition_of_done"]
        for key in (
            "component_catalog_frozen",
            "class_file_map_frozen",
            "dependency_graph_frozen",
            "sequence_flows_frozen",
            "singleton_policy_frozen",
            "core_infrastructure_boundary_frozen",
            "worker_reuses_core_processing",
            "privacy_boundary_frozen",
            "phase_ownership_recorded",
            "contract_tests_required",
        ):
            self.assertTrue(definition[key], key)
        self.assertTrue(definition["runtime_implementation_created_in_phase_2"])
        self.assertFalse(definition["todos_allowed"])

    def test_contract_has_no_nulls_and_spec_has_no_unresolved_markers(self) -> None:
        def assert_no_null(value: Any, path: str = "root") -> None:
            if value is None:
                self.fail(f"Null value found at {path}")
            if isinstance(value, dict):
                for key, child in value.items():
                    assert_no_null(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    assert_no_null(child, f"{path}[{index}]")

        assert_no_null(self.architecture)
        forbidden = ("todo:", "[todo]", "placeholder:", "[placeholder]", "implement me")
        unresolved = [
            line.strip().lower()
            for line in self.specification.splitlines()
            if any(line.strip().lower().startswith(marker) for marker in forbidden)
        ]
        self.assertEqual(unresolved, [])


if __name__ == "__main__":
    unittest.main()
