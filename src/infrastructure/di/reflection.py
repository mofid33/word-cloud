from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterable
from types import ModuleType

from src.infrastructure.di.inject import register_provider


DEFAULT_SCAN_PACKAGES = (
    "src.infrastructure",
    "src.core",
    "src.application",
)
EXCLUDED_PARTS = {
    "di",
    "sso",
    "alembic",
    "versions",
    "scripts",
    "models",
    "dtos",
    "res",
    "__pycache__",
}
EXCLUDED_MODULES = {
    "src.infrastructure.di.inject",
    "src.infrastructure.di.reflection",
    "src.infrastructure.di.bootstrap",
}


def iter_modules(package_name: str) -> Iterable[str]:
    package = importlib.import_module(package_name)
    package_paths = getattr(package, "__path__", None)
    if package_paths is None:
        return ()

    modules: list[str] = []
    for module_info in pkgutil.walk_packages(package_paths, package.__name__ + "."):
        module_name = module_info.name
        parts = set(module_name.split("."))
        if parts & EXCLUDED_PARTS or module_name in EXCLUDED_MODULES:
            continue
        modules.append(module_name)
    return modules


def _register_cached_module_providers(module: ModuleType) -> None:
    for candidate in vars(module).values():
        if (
            inspect.isclass(candidate)
            and candidate.__module__ == module.__name__
            and getattr(candidate, "__di_provider__", False)
        ):
            register_provider(candidate)


def import_discoverable_modules(
    packages: Iterable[str] = DEFAULT_SCAN_PACKAGES,
) -> tuple[str, ...]:
    imported: list[str] = []

    for package_name in packages:
        for module_name in iter_modules(package_name):
            try:
                module = importlib.import_module(module_name)
            except Exception:
                # The reference architecture intentionally skips an import
                # failure in one discoverable module and continues scanning.
                continue

            _register_cached_module_providers(module)
            imported.append(module_name)

    return tuple(imported)
