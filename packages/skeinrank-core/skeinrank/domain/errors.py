"""Domain-level exceptions.

These exceptions are part of the stable public API.
"""


class SkeinRankError(RuntimeError):
    """Base class for all SkeinRank errors."""


class ContractError(SkeinRankError):
    """Raised when the input violates SkeinRank contracts."""


class ModelUnavailable(SkeinRankError):
    """Raised when a requested backend/model is not available in the current environment."""
