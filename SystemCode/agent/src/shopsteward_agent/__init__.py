"""Lazy public exports keep the pure memory policy usable without the model stack."""

from importlib import import_module

_EXPORTS = {
    "collect_extensions": ".extensions",
    "Runtime": ".runtime",
    "RuntimeFailure": ".runtime",
    "OpenAIModel": ".model",
    "FencedPostgresSaver": ".checkpoint",
    "apply_memory_changes": ".memory.hermes_policy",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
