"""Dramatiq actor entry point."""

from .broker import recover_stale_jobs

__all__ = ["recover_stale_jobs"]
