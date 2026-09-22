import unittest
from abc import ABC, abstractmethod

from src.infrastructure.di.inject import inject, reset_di_state, resolve


class DependencyInjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_di_state()

    def test_constructor_dependencies_are_resolved(self) -> None:
        @inject
        class Repository:
            pass

        @inject
        class Service:
            def __init__(self, repository: Repository):
                self.repository = repository

        service = resolve(Service)
        self.assertIsInstance(service.repository, Repository)

    def test_singleton_provider_is_cached(self) -> None:
        @inject
        class Config:
            __di_singleton__ = True

        self.assertIs(resolve(Config), resolve(Config))

    def test_interface_resolves_single_implementation(self) -> None:
        class Provider(ABC):
            @abstractmethod
            def value(self) -> str:
                raise NotImplementedError

        @inject
        class ConcreteProvider(Provider):
            def value(self) -> str:
                return "ok"

        self.assertEqual(resolve(Provider).value(), "ok")


if __name__ == "__main__":
    unittest.main()
