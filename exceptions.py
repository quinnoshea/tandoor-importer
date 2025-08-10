"""
Custom exception classes for Tandoor Recipe Importer.

Defines a hierarchy of specific exceptions for different error scenarios.
"""


class TandoorImporterError(Exception):
    """Base exception for Tandoor Importer."""
    pass


class ConfigurationError(TandoorImporterError):
    """Raised when configuration is invalid or missing."""
    pass


class NetworkError(TandoorImporterError):
    """Raised when network operations fail."""
    pass


class RecipeProcessingError(TandoorImporterError):
    """Raised when recipe processing fails."""
    pass


class FileOperationError(TandoorImporterError):
    """Raised when file operations fail."""
    pass