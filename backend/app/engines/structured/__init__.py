"""Deterministic and exhaustive structured-query engine boundary."""

from .adapter import CanonicalPopulationReader, load_canonical_population
from .engine import StructuredExecutionError, StructuredQueryEngine
from .schemas import CanonicalPopulation, CanonicalRecord, StructuredGroup, StructuredValue

__all__ = [
    "CanonicalPopulation", "CanonicalPopulationReader", "CanonicalRecord",
    "StructuredExecutionError", "StructuredGroup", "StructuredQueryEngine", "StructuredValue",
    "load_canonical_population",
]
