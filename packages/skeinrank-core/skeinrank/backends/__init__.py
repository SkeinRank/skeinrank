"""Backend discovery and diagnostics.

This package provides a minimal backend registry and runtime diagnostics.
It is intentionally small in v1.x and designed for forward compatibility.
"""

from .registry import diagnose_backends, get_backend, list_backends

__all__ = ["get_backend", "list_backends", "diagnose_backends"]
