from __future__ import annotations

from threading import Lock

from src.infrastructure.di.inject import get_di_generation
from src.infrastructure.di.reflection import import_discoverable_modules


_bootstrapped_generation: int | None = None
_bootstrap_lock = Lock()


def bootstrap_packages() -> tuple[str, ...]:
    global _bootstrapped_generation
    with _bootstrap_lock:
        generation = get_di_generation()
        if _bootstrapped_generation == generation:
            return ()

        imported = import_discoverable_modules()
        _bootstrapped_generation = generation
        return imported


def bootstrap_di() -> tuple[str, ...]:
    return bootstrap_packages()
