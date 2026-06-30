# Contributing

Thanks for improving Image Harvest.

## Local Setup

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

## Development Notes

- Keep extraction logic in `extract_images.core` and `extract_images.extractors`.
- Keep metadata, duplicate detection, and reports in `extract_images.quality` and `extract_images.reporting`.
- Keep user interfaces in `extract_images.cli` and `extract_images.gui`.
- Prefer preserving original image bytes. Render PDF pages only as a fallback for pages without embedded image objects.

## Before Opening a Pull Request

```powershell
python -m pytest
python -m extract_images.cli --help
```
