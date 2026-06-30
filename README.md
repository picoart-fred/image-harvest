# Image Harvest

Image Harvest is a local batch tool for extracting high-quality images from PDF and Office files.

It favors original embedded assets over screenshots or page rasterization:

- PDF: extracts embedded image objects with their original bytes and format where possible.
- PDF scan fallback: optionally renders pages that have no embedded images at a chosen DPI.
- Office files: extracts original media from `.docx`, `.pptx`, and `.xlsx` packages.
- Reports: writes JSON and CSV metadata, including dimensions, byte size, SHA-256, and duplicates.
- Interfaces: command line, a small tkinter desktop GUI, and a local browser web app.

## Install

```powershell
python -m pip install -e .
```

For development:

```powershell
python -m pip install -e ".[dev]"
```

## Command Line

```powershell
image-harvest "H:\docs" "H:\extracted" --recursive --render-scanned-pages --dpi 300 --report "H:\extracted\report.json"
```

Without installing entry points, run the same CLI as a module:

```powershell
python -m extract_images.cli "H:\docs" "H:\extracted" --recursive --report "H:\extracted\report.json"
```

Common options:

- `--render-scanned-pages` / `--no-render-scanned-pages`: control PDF page rendering fallback.
- `--dpi 600`: increase quality for rendered scan-only PDF pages.
- `--recursive`: scan folders recursively.
- `--report report.json`: write `.json`, `.csv`, or `.txt` report output.
- `--include .pdf .docx`: choose file extensions to scan.

## GUI

```powershell
image-harvest-gui
```

Or:

```powershell
python -m extract_images.gui
```

The GUI lets you choose input/output folders, a report path, DPI, recursive scanning, and scan-page rendering.

## Web Tool

Run the local web app:

```powershell
python -m extract_images.web
```

Then open:

```text
http://127.0.0.1:8765/
```

The web page lets you upload PDF, DOCX, PPTX, and XLSX files, choose extraction settings, and download a ZIP containing the extracted images plus a JSON report.

After installing the package, you can also run:

```powershell
image-harvest-web
```

## Three-Agent Design

The project is organized around three responsibilities:

1. File parsing agent: `extract_images.core` and `extract_images.extractors`
2. Quality control agent: `extract_images.quality` and `extract_images.reporting`
3. Interface agent: `extract_images.cli` and `extract_images.gui`

This keeps the extraction engine reusable while allowing the CLI, GUI, reports, and future automation to evolve independently.

## Supported Files

- `.pdf`
- `.docx`
- `.pptx`
- `.xlsx`

## Notes on Quality

For PDFs, Image Harvest first tries to copy the original embedded image bytes. This is the highest-quality path because no resampling or recompression happens. Rendering is only used when `--render-scanned-pages` is enabled and a PDF page has no embedded image object.

## Test

```powershell
python -m pytest
```

## GitHub CI

The repository includes a Windows GitHub Actions workflow at `.github/workflows/ci.yml`.
It installs the package with development dependencies, runs tests, and checks the CLI help output.
