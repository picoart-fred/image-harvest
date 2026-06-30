"""Quality metadata and duplicate detection for extracted images."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True, slots=True)
class ImageSource:
    """Where an extracted image came from inside an input document."""

    document_path: str
    extractor: str
    page_number: int | None = None
    image_index: int | None = None
    object_id: str | None = None
    rendered_page: bool = False


@dataclass(frozen=True, slots=True)
class ImageRecord:
    """Stable quality metadata for one image written by the extractor."""

    output_path: str
    sha256: str
    byte_size: int
    width: int
    height: int
    format: str
    mode: str | None
    source: ImageSource
    duplicate_of: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_of is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Images with the same sha256 digest."""

    sha256: str
    canonical_path: str
    duplicate_paths: tuple[str, ...]

    @property
    def count(self) -> int:
        return 1 + len(self.duplicate_paths)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Aggregate counts for a batch of image records."""

    total_images: int
    unique_images: int
    duplicate_images: int
    duplicate_groups: int
    total_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def file_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the sha256 digest for a file without loading it all at once."""

    digest = sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_image_record(
    image_path: str | Path,
    source: ImageSource,
    *,
    duplicate_of: str | None = None,
    extra: dict[str, Any] | None = None,
) -> ImageRecord:
    """Inspect an extracted image file and return its quality metadata."""

    path = Path(image_path)
    stat = path.stat()
    try:
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format or path.suffix.lstrip(".").upper() or "UNKNOWN"
            mode = image.mode
    except UnidentifiedImageError as exc:
        raise ValueError(f"Cannot inspect image file: {path}") from exc

    return ImageRecord(
        output_path=str(path),
        sha256=file_sha256(path),
        byte_size=stat.st_size,
        width=width,
        height=height,
        format=image_format.upper(),
        mode=mode,
        source=source,
        duplicate_of=duplicate_of,
        extra=extra or {},
    )


def mark_duplicates(records: Iterable[ImageRecord]) -> list[ImageRecord]:
    """Return records with duplicate_of set to the first path for each sha256."""

    first_seen: dict[str, str] = {}
    marked: list[ImageRecord] = []

    for record in records:
        canonical_path = first_seen.get(record.sha256)
        if canonical_path is None:
            first_seen[record.sha256] = record.output_path
            marked.append(replace(record, duplicate_of=None))
        else:
            marked.append(replace(record, duplicate_of=canonical_path))

    return marked


def duplicate_groups(records: Iterable[ImageRecord]) -> list[DuplicateGroup]:
    """Group records that share the same sha256 digest."""

    grouped: dict[str, list[ImageRecord]] = {}
    for record in records:
        grouped.setdefault(record.sha256, []).append(record)

    groups: list[DuplicateGroup] = []
    for digest, group_records in grouped.items():
        if len(group_records) < 2:
            continue
        canonical = group_records[0].output_path
        duplicates = tuple(record.output_path for record in group_records[1:])
        groups.append(
            DuplicateGroup(
                sha256=digest,
                canonical_path=canonical,
                duplicate_paths=duplicates,
            )
        )

    return groups


def summarize_quality(records: Iterable[ImageRecord]) -> QualitySummary:
    """Build aggregate quality and dedupe counts for a batch."""

    record_list = list(records)
    duplicate_count = sum(1 for record in record_list if record.is_duplicate)
    return QualitySummary(
        total_images=len(record_list),
        unique_images=len(record_list) - duplicate_count,
        duplicate_images=duplicate_count,
        duplicate_groups=len(duplicate_groups(record_list)),
        total_bytes=sum(record.byte_size for record in record_list),
    )
