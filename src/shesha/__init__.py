"""Shesha: Recursive Language Models for document querying."""

from shesha.config import SheshaConfig
from shesha.exceptions import (
    AuthenticationError,
    DocumentError,
    DocumentNotFoundError,
    NoParserError,
    ParseError,
    ProjectError,
    ProjectExistsError,
    ProjectNotFoundError,
    RepoError,
    RepoIngestError,
    SheshaError,
)
from shesha.models import ParsedDocument, QueryContext, RepoProjectResult
from shesha.project import Project
from shesha.rlm import ProgressCallback, QueryResult, StepType, TokenUsage, Trace, TraceStep
from shesha.shesha import Shesha
from shesha.storage import FilesystemStorage

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Main API
    "Shesha",
    "Project",
    "SheshaConfig",
    # Query results
    "ProgressCallback",
    "QueryContext",
    "QueryResult",
    "RepoProjectResult",
    "Trace",
    "TraceStep",
    "StepType",
    "TokenUsage",
    # Storage
    "FilesystemStorage",
    "ParsedDocument",
    # Exceptions
    "SheshaError",
    "ProjectError",
    "ProjectNotFoundError",
    "ProjectExistsError",
    "DocumentError",
    "DocumentNotFoundError",
    "ParseError",
    "NoParserError",
    "RepoError",
    "AuthenticationError",
    "RepoIngestError",
]
