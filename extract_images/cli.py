"""Command-line interface for Image Harvest."""

from __future__ import annotations

import argparse
import csv
import inspect
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".pptx", ".xlsx")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="image-harvest",
        description="Batch extract high-quality images from PDF and Office files.",
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Input file or directory containing PDF/Office documents.",
    )
    parser.add_argument(
        "output_path",
        type=Path,
        help="Directory where extracted images and optional reports will be written.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI used when rendering scanned PDF pages. Default: 300.",
    )
    parser.add_argument(
        "--render-scanned-pages",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Render PDF pages that do not expose embedded images. Default: enabled.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively scan input directories.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional report path. Extension controls format: .json, .csv, or text.",
    )
    parser.add_argument(
        "--include",
        nargs="+",
        default=list(SUPPORTED_EXTENSIONS),
        help="File extensions to include when scanning a directory.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print errors and final status.",
    )
    return parser


def normalize_extensions(values: Iterable[str]) -> tuple[str, ...]:
    extensions = []
    for value in values:
        value = value.strip().lower()
        if not value:
            continue
        extensions.append(value if value.startswith(".") else f".{value}")
    return tuple(dict.fromkeys(extensions))


def result_to_data(result: Any) -> Any:
    if is_dataclass(result):
        return asdict(result)
    if isinstance(result, Path):
        return str(result)
    if isinstance(result, dict):
        return {str(key): result_to_data(value) for key, value in result.items()}
    if isinstance(result, (list, tuple, set)):
        return [result_to_data(value) for value in result]
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "__dict__"):
        return {
            key: result_to_data(value)
            for key, value in vars(result).items()
            if not key.startswith("_")
        }
    return result


def summarize_result(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        summary = dict(data)
    else:
        summary = {"result": data}

    files = summary.get("files") or summary.get("documents") or []
    images = summary.get("images") or summary.get("extracted_images") or []

    if "file_count" not in summary and isinstance(files, list):
        summary["file_count"] = len(files)
    if "image_count" not in summary and isinstance(images, list):
        summary["image_count"] = len(images)

    return summary


def write_report(report_path: Path, result: Any) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    data = result_to_data(result)

    if report_path.suffix.lower() == ".json":
        report_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return

    if report_path.suffix.lower() == ".csv":
        rows = _flatten_report_rows(data)
        fieldnames = sorted({key for row in rows for key in row})
        with report_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return

    report_path.write_text(_format_text_report(data), encoding="utf-8")


def _flatten_report_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("images", "extracted_images", "items", "files", "documents"):
            value = data.get(key)
            if isinstance(value, list) and value:
                return [
                    row if isinstance(row, dict) else {"value": row}
                    for row in result_to_data(value)
                ]
        return [{key: value for key, value in data.items() if not isinstance(value, (list, dict))}]
    if isinstance(data, list):
        return [row if isinstance(row, dict) else {"value": row} for row in data]
    return [{"result": data}]


def _format_text_report(data: Any) -> str:
    summary = summarize_result(data)
    lines = ["Image Harvest report", ""]
    for key, value in summary.items():
        if isinstance(value, (list, dict)):
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def build_options(args: argparse.Namespace) -> Any:
    try:
        from extract_images.core import ExtractionOptions
    except ModuleNotFoundError as exc:
        if exc.name == "extract_images.core":
            raise RuntimeError(
                "extract_images.core is not implemented yet. "
                "Implement ExtractionOptions and extract_path before running the CLI."
            ) from exc
        raise

    values = {
        "dpi": args.dpi,
        "render_scanned_pages": args.render_scanned_pages,
        "recursive": args.recursive,
        "include_extensions": normalize_extensions(args.include),
        "report_path": args.report,
    }

    signature = inspect.signature(ExtractionOptions)
    accepted = {
        key: value
        for key, value in values.items()
        if key in signature.parameters
        or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
    }
    return ExtractionOptions(**accepted)


def run_extraction(
    input_path: Path,
    output_path: Path,
    *,
    dpi: int = 300,
    render_scanned_pages: bool = True,
    recursive: bool = False,
    report_path: Path | None = None,
    include_extensions: Iterable[str] = SUPPORTED_EXTENSIONS,
) -> Any:
    """Run extraction through the core module.

    The core module owns document parsing. This wrapper keeps the public CLI/GUI
    stable while allowing the extraction implementation to evolve.
    """

    try:
        from extract_images.core import ExtractionOptions, extract_path
    except ModuleNotFoundError as exc:
        if exc.name == "extract_images.core":
            raise RuntimeError(
                "extract_images.core is not implemented yet. "
                "Expected core API: ExtractionOptions and extract_path."
            ) from exc
        raise

    input_path = Path(input_path)
    output_path = Path(output_path)
    report_path = Path(report_path) if report_path else None
    output_path.mkdir(parents=True, exist_ok=True)

    option_values = {
        "dpi": dpi,
        "render_scanned_pages": render_scanned_pages,
        "recursive": recursive,
        "include_extensions": normalize_extensions(include_extensions),
        "report_path": report_path,
    }

    option_signature = inspect.signature(ExtractionOptions)
    has_var_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in option_signature.parameters.values()
    )
    options = ExtractionOptions(
        **{
            key: value
            for key, value in option_values.items()
            if has_var_kwargs or key in option_signature.parameters
        }
    )

    result = _call_extract_path(extract_path, input_path, output_path, options)

    if report_path:
        write_report(report_path, result)

    return result


def _call_extract_path(extract_path: Any, input_path: Path, output_path: Path, options: Any) -> Any:
    signature = inspect.signature(extract_path)
    params = signature.parameters

    if "input_path" in params and "output_path" in params:
        kwargs = {"input_path": input_path, "output_path": output_path}
        if "options" in params:
            kwargs["options"] = options
        return extract_path(**kwargs)

    if "path" in params and "output_dir" in params:
        kwargs = {"path": input_path, "output_dir": output_path}
        if "options" in params:
            kwargs["options"] = options
        return extract_path(**kwargs)

    if "options" in params:
        return extract_path(input_path, output_path, options=options)

    return extract_path(input_path, output_path, options)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.dpi <= 0:
        parser.error("--dpi must be greater than 0")

    input_path = args.input_path.expanduser().resolve()
    output_path = args.output_path.expanduser().resolve()
    report_path = args.report.expanduser().resolve() if args.report else None

    if not input_path.exists():
        parser.error(f"Input path does not exist: {input_path}")

    try:
        result = run_extraction(
            input_path,
            output_path,
            dpi=args.dpi,
            render_scanned_pages=args.render_scanned_pages,
            recursive=args.recursive,
            report_path=report_path,
            include_extensions=args.include,
        )
    except Exception as exc:  # pragma: no cover - exercised by integration tests.
        print(f"image-harvest: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        summary = summarize_result(result_to_data(result))
        print(f"Output: {output_path}")
        if report_path:
            print(f"Report: {report_path}")
        if "file_count" in summary:
            print(f"Files processed: {summary['file_count']}")
        if "image_count" in summary:
            print(f"Images extracted: {summary['image_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
