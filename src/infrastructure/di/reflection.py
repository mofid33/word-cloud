from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable


DEFAULT_SCAN_PACKAGES = (
    "src.infrastructure",
    "src.core",
    "src.application",
)
EXCLUDED_PARTS = {
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


def import_discoverable_modules(
    packages: Iterable[str] = DEFAULT_SCAN_PACKAGES,
) -> tuple[str, ...]:
    imported: list[str] = []
    errors: list[tuple[str, Exception]] = []

    for package_name in packages:
        for module_name in iter_modules(package_name):
            try:
                importlib.import_module(module_name)
                imported.append(module_name)
            except Exception as exc:
                errors.append((module_name, exc))

    if errors:
        details = "; ".join(
            f"{name}: {type(exc).__name__}: {exc}" for name, exc in errors
        )
        raise ImportError(f"DI discovery failed: {details}")

    return tuple(imported)
