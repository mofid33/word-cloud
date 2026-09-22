from __future__ import annotations

import inspect
from functools import wraps
from threading import RLock
from typing import Any, TypeVar, cast, get_type_hints


T = TypeVar("T", bound=type)


class DependencyResolutionError(RuntimeError):
    pass


_registry: dict[type, type] = {}
_singletons: dict[type, Any] = {}
_lock = RLock()


def register_provider(provider_type: type) -> None:
    with _lock:
        _registry[provider_type] = provider_type
        for base in provider_type.__mro__[1:]:
            if base is object:
                continue
            if inspect.isabstract(base) or base.__name__.startswith("I"):
                existing = _registry.get(base)
                if existing is not None and existing is not provider_type:
                    raise DependencyResolutionError(
                        f"Multiple providers registered for {base.__name__}"
                    )
                _registry[base] = provider_type


def resolve(dependency_type: type) -> Any:
    provider_type = _registry.get(dependency_type)
    if provider_type is None:
        if getattr(dependency_type, "__di_provider__", False):
            provider_type = dependency_type
        else:
            raise DependencyResolutionError(
                f"No provider registered for {dependency_type!r}"
            )

    if inspect.isabstract(provider_type):
        raise DependencyResolutionError(
            f"Provider {provider_type.__name__} is abstract and has no implementation"
        )

    if getattr(provider_type, "__di_singleton__", False):
        with _lock:
            if provider_type not in _singletons:
                _singletons[provider_type] = provider_type()
            return _singletons[provider_type]

    return provider_type()


def inject(cls: T) -> T:
    original_init = cls.__init__
    signature = inspect.signature(original_init)

    @wraps(original_init)
    def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
        bound = signature.bind_partial(self, *args, **kwargs)
        try:
            hints = get_type_hints(original_init)
        except (NameError, TypeError) as exc:
            raise DependencyResolutionError(
                f"Cannot resolve type hints for {cls.__name__}.__init__: {exc}"
            ) from exc

        for name, parameter in signature.parameters.items():
            if name == "self" or name in bound.arguments:
                continue
            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if parameter.default is not inspect.Parameter.empty:
                continue
            dependency_type = hints.get(name)
            if dependency_type is None:
                raise DependencyResolutionError(
                    f"Dependency '{name}' in {cls.__name__} requires a type annotation"
                )
            kwargs[name] = resolve(dependency_type)

        original_init(self, *args, **kwargs)

    cls.__init__ = wrapped_init
    cls.__di_provider__ = True
    register_provider(cls)
    return cast(T, cls)


def reset_di_state() -> None:
    with _lock:
        _registry.clear()
        _singletons.clear()
