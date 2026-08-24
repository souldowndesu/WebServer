"""Authenticated multi-user management control plane."""

from .storage import AccountStore

__all__ = ["AccountStore", "create_server"]


def __getattr__(name: str):
    """Load the server factory lazily so ``python -m`` has one import path."""
    if name == "create_server":
        from .server import create_server

        return create_server
    raise AttributeError(name)
