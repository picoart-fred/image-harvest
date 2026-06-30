"""Core orchestration for batch image extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from extract_images.quality import ImageRecord, ImageSource, build_image_record, mark_duplicates
from extract_images.extractors import (
    SUPPORTED_EXTENSIONS,
    ExtractionIssue,
    FileExtractionResult,
    extract_file,
)


@dataclass(slots=True)
class ExtractionOptions:
    """Options shared by CLI, GUI, and library callers."""

    output_dir: Path | None = None
    recursive: bool = True
    render_scanned_pages: bool = False
    render_pages: bool | None = None
    dpi: int = 300
    overwrite: bool = False
    dedupe_pdf_xrefs: bool = True
    deduplicate: bool = False
    min_image_bytes: int = 0
    supported_extensions: tuple[str, ...] = tuple(sorted(SUPPORTED_EXTENSIONS))

    def __post_init__(self) -> None:
        if self.output_dir is not None:
            self.output_dir = Path(self.output_dir)
        if self.render_pages is not None:
            self.render_scanned_pages = self.render_pages
        if self.dpi <= 0:
            raise ValueError("dpi must be greater than zero")
        if self.min_image_bytes < 0:
            raise ValueError("min_image_bytes must be zero or greater")
        self.supported_extensions = tuple(
            sorted(
                {
                    extension.lower() if extension.startswith(".") else f".{extension.lower()}"
                    for extension in self.supported_extensions
                }
            )
        )


@dataclass(slots=True)
class ExtractionResult:
    """Batch extraction result returned by :func:`extract_path`."""

    input_path: Path
    output_dir: Path
    images: list[ImageRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    files: list[FileExtractionResult] = field(default_factory=list)
    issues: list[ExtractionIssue] = field(default_factory=list)

    def __iter__(self):
        return iter(self.images)

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def extracted_count(self) -> int:
        return len(self.images)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for image in self.images if image.duplicate_of is not None)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def skipped_count(self) -> int:
        return sum(1 for file_result in self.files if file_result.skipped)

    @property
    def issue_count(self) -> int:
        return len(self.errors)


def extract_path(
    input_path: str | Path,
    output_dir: str | Path | ExtractionOptions | None = None,
    options: ExtractionOptions | None = None,
) -> ExtractionResult:
    """Extract images from a single file or every supported file in a directory.

    Args:
        input_path: Source file or directory to scan.
        output_dir: Directory where per-source output folders will be created.
        options: Optional extraction settings.

    Returns:
        Structured result suitable for CLI/GUI display.
    """

    if isinstance(output_dir, ExtractionOptions):
        options = output_dir
        output_dir = options.output_dir

    options = options or ExtractionOptions()
    if output_dir is None:
        output_dir = options.output_dir
    if output_dir is None:
        raise ValueError("output_dir is required")

    source = Path(input_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    result = ExtractionResult(input_path=source, output_dir=destination)

    if not source.exists():
        _record_issue(result, ExtractionIssue(source_path=source, message="Input path does not exist."))
        return result

    destination.mkdir(parents=True, exist_ok=True)

    for file_path in discover_sources(source, options):
        file_output_dir = _output_dir_for_source(file_path, source, destination)
        file_result = extract_file(file_path, file_output_dir, options)
        result.files.append(file_result)
        if file_result.skipped:
            result.skipped.append(file_result.source_path)
        for issue in file_result.issues:
            _record_issue(result, issue)
        result.images.extend(_build_records(file_result, result))

    if source.is_file() and not result.files:
        file_result = FileExtractionResult(
            source_path=source,
            output_dir=_output_dir_for_source(source, source, destination),
            extractor="unsupported",
            skipped=True,
            skip_reason=f"Unsupported file extension: {source.suffix}",
        )
        result.files.append(file_result)
        result.skipped.append(source)

    result.images = mark_duplicates(result.images)
    if options.deduplicate:
        _remove_duplicate_files(result.images)

    return result


def discover_sources(input_path: str | Path, options: ExtractionOptions | None = None) -> list[Path]:
    """Return supported files for a source file or directory."""

    options = options or ExtractionOptions()
    source = Path(input_path).expanduser().resolve()
    supported = set(options.supported_extensions)

    if source.is_file():
        return [source] if source.suffix.lower() in supported else []

    if not source.is_dir():
        return []

    candidates: Iterable[Path]
    candidates = source.rglob("*") if options.recursive else source.glob("*")
    return sorted(path for path in candidates if path.is_file() and path.suffix.lower() in supported)


def _output_dir_for_source(source_file: Path, input_root: Path, output_root: Path) -> Path:
    if input_root.is_file():
        relative_parent = Path()
    else:
        try:
            relative_parent = source_file.parent.relative_to(input_root)
        except ValueError:
            relative_parent = Path()

    safe_stem = _safe_name(source_file.stem)
    suffix_label = source_file.suffix.lower().lstrip(".") or "file"
    return output_root / relative_parent / f"{safe_stem}_{suffix_label}"


def _safe_name(value: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if char in invalid or ord(char) < 32 else char for char in value).strip()
    return cleaned or "document"


def _build_records(
    file_result: FileExtractionResult,
    batch_result: ExtractionResult,
) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    for image in file_result.images:
        source = ImageSource(
            document_path=str(image.source_path),
            extractor=image.extractor,
            page_number=image.page_number,
            image_index=image.image_index,
            object_id=image.note,
            rendered_page=image.extractor == "pdf-render",
        )
        try:
            records.append(
                build_image_record(
                    image.output_path,
                    source,
                    extra={
                        "original_format": image.original_format,
                        "bytes_written": image.bytes_written,
                    },
                )
            )
        except ValueError as exc:
            batch_result.errors.append(str(exc))
    return records


def _record_issue(result: ExtractionResult, issue: ExtractionIssue) -> None:
    result.issues.append(issue)
    if issue.exception_type:
        result.errors.append(f"{issue.source_path}: {issue.message} [{issue.exception_type}]")
    else:
        result.errors.append(f"{issue.source_path}: {issue.message}")


def _remove_duplicate_files(records: Iterable[ImageRecord]) -> None:
    for record in records:
        if record.duplicate_of is None:
            continue
        path = Path(record.output_path)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            continue
