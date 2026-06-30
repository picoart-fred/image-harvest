"""Document-specific image extractors."""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extract_images.core import ExtractionOptions


PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | OFFICE_EXTENSIONS

OFFICE_MEDIA_PREFIXES = {
    ".docx": "word/media/",
    ".pptx": "ppt/media/",
    ".xlsx": "xl/media/",
}


@dataclass(slots=True)
class ExtractedImage:
    """A single image written to disk."""

    source_path: Path
    output_path: Path
    extractor: str
    original_format: str
    bytes_written: int
    page_number: int | None = None
    image_index: int | None = None
    width: int | None = None
    height: int | None = None
    note: str | None = None


@dataclass(slots=True)
class ExtractionIssue:
    """Non-fatal or fatal issue captured for callers."""

    source_path: Path
    message: str
    exception_type: str | None = None


@dataclass(slots=True)
class FileExtractionResult:
    """Extraction result for one source file."""

    source_path: Path
    output_dir: Path
    extractor: str
    images: list[ExtractedImage] = field(default_factory=list)
    issues: list[ExtractionIssue] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def image_count(self) -> int:
        return len(self.images)


def extract_file(
    source_path: Path,
    output_dir: Path,
    options: ExtractionOptions,
) -> FileExtractionResult:
    """Extract images from a supported source file."""

    suffix = source_path.suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return extract_pdf(source_path, output_dir, options)
    if suffix in OFFICE_EXTENSIONS:
        return extract_office(source_path, output_dir, options)

    return FileExtractionResult(
        source_path=source_path,
        output_dir=output_dir,
        extractor="unsupported",
        skipped=True,
        skip_reason=f"Unsupported file extension: {source_path.suffix}",
    )


def extract_pdf(
    source_path: Path,
    output_dir: Path,
    options: ExtractionOptions,
) -> FileExtractionResult:
    """Extract embedded PDF images and optionally render image-less pages."""

    result = FileExtractionResult(source_path=source_path, output_dir=output_dir, extractor="pdf")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import fitz
    except ImportError as exc:
        result.issues.append(
            ExtractionIssue(
                source_path=source_path,
                message="PyMuPDF is required to extract images from PDF files.",
                exception_type=type(exc).__name__,
            )
        )
        return result

    try:
        document = fitz.open(source_path)
    except Exception as exc:  # pragma: no cover - exercised by integration tests with bad PDFs.
        result.issues.append(_issue(source_path, "Could not open PDF file.", exc))
        return result

    seen_xrefs: set[int] = set()
    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_number = page_index + 1
            page_images = page.get_images(full=True)

            wrote_embedded = False
            for image_position, image_info in enumerate(page_images, start=1):
                xref = int(image_info[0])
                if options.dedupe_pdf_xrefs and xref in seen_xrefs:
                    continue

                try:
                    image = document.extract_image(xref)
                except Exception as exc:
                    result.issues.append(_issue(source_path, f"Could not extract PDF image xref {xref}.", exc))
                    continue

                image_bytes = image.get("image")
                if not image_bytes:
                    continue
                if len(image_bytes) < options.min_image_bytes:
                    continue

                extension = _normalize_extension(str(image.get("ext") or "bin"))
                output_path = _unique_path(
                    output_dir / f"page-{page_number:04d}_image-{image_position:03d}_xref-{xref}.{extension}",
                    overwrite=options.overwrite,
                )
                output_path.write_bytes(image_bytes)
                seen_xrefs.add(xref)
                wrote_embedded = True

                result.images.append(
                    ExtractedImage(
                        source_path=source_path,
                        output_path=output_path,
                        extractor="pdf",
                        original_format=extension,
                        bytes_written=output_path.stat().st_size,
                        page_number=page_number,
                        image_index=image_position,
                        width=_as_int(image.get("width")),
                        height=_as_int(image.get("height")),
                    )
                )

            if options.render_scanned_pages and not wrote_embedded:
                rendered = _render_pdf_page(page, page_number, source_path, output_dir, options)
                result.images.append(rendered)
    finally:
        document.close()

    return result


def extract_office(
    source_path: Path,
    output_dir: Path,
    options: ExtractionOptions,
) -> FileExtractionResult:
    """Extract media files directly from zip-based Office documents."""

    result = FileExtractionResult(source_path=source_path, output_dir=output_dir, extractor="office")
    output_dir.mkdir(parents=True, exist_ok=True)

    media_prefix = OFFICE_MEDIA_PREFIXES[source_path.suffix.lower()]
    try:
        with zipfile.ZipFile(source_path) as archive:
            media_members = [
                member
                for member in archive.infolist()
                if not member.is_dir() and member.filename.startswith(media_prefix)
            ]

            for image_index, member in enumerate(media_members, start=1):
                original_name = Path(member.filename).name
                extension = _normalize_extension(Path(original_name).suffix.lstrip(".") or "bin")
                stem = Path(original_name).stem or f"image-{image_index:03d}"
                output_path = _unique_path(
                    output_dir / f"{image_index:03d}_{stem}.{extension}",
                    overwrite=options.overwrite,
                )

                with archive.open(member) as source, output_path.open("wb") as target:
                    shutil.copyfileobj(source, target)

                result.images.append(
                    ExtractedImage(
                        source_path=source_path,
                        output_path=output_path,
                        extractor="office",
                        original_format=extension,
                        bytes_written=output_path.stat().st_size,
                        image_index=image_index,
                        note=member.filename,
                    )
                )
    except zipfile.BadZipFile as exc:
        result.issues.append(_issue(source_path, "Office file is not a readable zip package.", exc))
    except Exception as exc:  # pragma: no cover - defensive boundary for corrupt office packages.
        result.issues.append(_issue(source_path, "Could not extract Office media.", exc))

    return result


def _render_pdf_page(
    page: object,
    page_number: int,
    source_path: Path,
    output_dir: Path,
    options: ExtractionOptions,
) -> ExtractedImage:
    scale = options.dpi / 72

    import fitz

    matrix = fitz.Matrix(scale, scale)

    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    output_path = _unique_path(
        output_dir / f"page-{page_number:04d}_rendered-{options.dpi}dpi.png",
        overwrite=options.overwrite,
    )
    pixmap.save(output_path)

    return ExtractedImage(
        source_path=source_path,
        output_path=output_path,
        extractor="pdf-render",
        original_format="png",
        bytes_written=output_path.stat().st_size,
        page_number=page_number,
        width=pixmap.width,
        height=pixmap.height,
        note="Rendered because no embedded images were extracted from this page.",
    )


def _issue(source_path: Path, message: str, exc: Exception) -> ExtractionIssue:
    return ExtractionIssue(
        source_path=source_path,
        message=f"{message} {exc}",
        exception_type=type(exc).__name__,
    )


def _normalize_extension(extension: str) -> str:
    extension = extension.lower().lstrip(".")
    if extension == "jpeg":
        return "jpg"
    if extension == "jpx":
        return "jp2"
    return extension or "bin"


def _unique_path(path: Path, *, overwrite: bool) -> Path:
    if overwrite or not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    for counter in range(1, 10_000):
        candidate = path.with_name(f"{stem}_{counter:02d}{suffix}")
        if not candidate.exists():
            return candidate

    raise FileExistsError(f"Could not create a unique filename for {path}")


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
