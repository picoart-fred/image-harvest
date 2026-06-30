"""JSON and CSV report writers for extracted image metadata."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from extract_images.quality import (
    DuplicateGroup,
    ImageRecord,
    QualitySummary,
    duplicate_groups,
    summarize_quality,
)


CSV_FIELDS = (
    "output_path",
    "sha256",
    "byte_size",
    "width",
    "height",
    "format",
    "mode",
    "document_path",
    "extractor",
    "page_number",
    "image_index",
    "object_id",
    "rendered_page",
    "duplicate_of",
)


def report_payload(
    records: Iterable[ImageRecord],
    *,
    summary: QualitySummary | None = None,
    groups: Iterable[DuplicateGroup] | None = None,
) -> dict[str, Any]:
    """Return the JSON-serializable report payload."""

    record_list = list(records)
    duplicate_group_list = list(groups) if groups is not None else duplicate_groups(record_list)
    quality_summary = summary or summarize_quality(record_list)
    return {
        "summary": quality_summary.to_dict(),
        "images": [record.to_dict() for record in record_list],
        "duplicates": [group.to_dict() for group in duplicate_group_list],
    }


def write_json_report(
    records: Iterable[ImageRecord],
    path: str | Path,
    *,
    summary: QualitySummary | None = None,
    groups: Iterable[DuplicateGroup] | None = None,
) -> Path:
    """Write a UTF-8 JSON report and return its path."""

    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = report_payload(records, summary=summary, groups=groups)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def write_csv_report(records: Iterable[ImageRecord], path: str | Path) -> Path:
    """Write a CSV report with one row per extracted image and return its path."""

    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(_record_to_csv_row(record))
    return report_path


def write_reports(
    records: Iterable[ImageRecord],
    output_dir: str | Path,
    *,
    json_name: str = "image-report.json",
    csv_name: str = "image-report.csv",
) -> dict[str, Path]:
    """Write JSON and CSV reports into an output directory."""

    record_list = list(records)
    directory = Path(output_dir)
    return {
        "json": write_json_report(record_list, directory / json_name),
        "csv": write_csv_report(record_list, directory / csv_name),
    }


def _record_to_csv_row(record: ImageRecord) -> dict[str, Any]:
    source = record.source
    return {
        "output_path": record.output_path,
        "sha256": record.sha256,
        "byte_size": record.byte_size,
        "width": record.width,
        "height": record.height,
        "format": record.format,
        "mode": record.mode,
        "document_path": source.document_path,
        "extractor": source.extractor,
        "page_number": source.page_number,
        "image_index": source.image_index,
        "object_id": source.object_id,
        "rendered_page": source.rendered_page,
        "duplicate_of": record.duplicate_of,
    }
