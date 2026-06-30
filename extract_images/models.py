"""Shared data models for extraction and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ExtractedImage:
    """Metadata for one extracted image file."""

    source_file: Path
    output_file: Path
    method: str
    page: int | None = None
    index: int | None = None
    extension: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int = 0
    sha256: str | None = None
    duplicate_of: Path | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtractionResult:
    """Summary for an extraction run."""

    input_path: Path
    output_dir: Path
    images: list[ExtractedImage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)

    @property
    def extracted_count(self) -> int:
        return len(self.images)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for image in self.images if image.duplicate_of is not None)
