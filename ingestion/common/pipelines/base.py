"""Base pipeline classes for data ingestion jobs."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PipelineResult:
    """Pipeline execution result."""

    success: int
    errors: int
    total: int
    index_name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a structured representation for serialization."""
        return {
            "success": self.success,
            "errors": self.errors,
            "total": self.total,
            "index_name": self.index_name,
            "details": dict(self.details),
        }

    def to_structured_log(self) -> str:
        """Return a structured multi-line log payload."""
        payload = self.to_dict()
        lines = [
            "pipeline_result",
            f"  index_name={payload['index_name']}",
            f"  {payload['success']} / {payload['total']} succeeded",
            f"  {payload['errors']} errors",
        ]

        details = payload.get("details") or {}
        if details:
            lines.append("  details:")
            for key, value in details.items():
                lines.append(f"    {key}={value}")

        return "\n".join(lines)


class BasePipeline(ABC):
    """Abstract base class for data ingestion pipelines."""

    def __init__(self, pipeline_dir: Path, dry_run: bool = False, truncate: bool = False):
        """Initialize the pipeline.

        Args:
            pipeline_dir: Directory containing pipeline configuration files
            dry_run: If True, skip actual ingestion operations
            truncate: If True, delete and recreate the index

        """
        self.pipeline_dir = pipeline_dir
        self.dry_run = dry_run
        self.truncate = truncate

    @abstractmethod
    def run(self) -> PipelineResult:
        """Execute the pipeline.

        Subclasses must implement this method. Attempting to instantiate
        a subclass without implementing run() will raise TypeError.

        Returns:
            PipelineResult containing execution summary

        """
        pass
