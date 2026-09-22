from __future__ import annotations

from threading import Lock

from src.infrastructure.di.reflection import import_discoverable_modules


_bootstrapped = False
_bootstrap_lock = Lock()


def bootstrap_packages() -> tuple[str, ...]:
    global _bootstrapped
    with _bootstrap_lock:
        if _bootstrapped:
            return ()
        imported = import_discoverable_modules()
        _bootstrapped = True
        return imported


def bootstrap_di() -> tuple[str, ...]:
    return bootstrap_packages()
