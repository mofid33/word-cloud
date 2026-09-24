from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable
from pathlib import Path
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

    modules: set[str] = set()
    for package_path in package_paths:
        root = Path(package_path)
        if not root.is_dir():
            continue

        for file_path in root.rglob("*.py"):
            relative = file_path.relative_to(root)
            relative_parts = relative.parts

            if any(part in EXCLUDED_PARTS for part in relative_parts[:-1]):
                continue
            if relative.name == "__init__.py":
                continue

            module_parts = relative.with_suffix("").parts
            module_name = ".".join((package.__name__, *module_parts))
            if module_name in EXCLUDED_MODULES:
                continue
            modules.add(module_name)

    return tuple(sorted(modules))


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
