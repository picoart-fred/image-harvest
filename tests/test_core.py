from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from extract_images.core import ExtractionOptions, discover_sources, extract_path


def test_discover_sources_filters_supported_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"")
    (tmp_path / "b.txt").write_text("x")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.docx").write_bytes(b"")

    found = {path.name for path in discover_sources(tmp_path)}

    assert found == {"a.pdf", "c.docx"}


def test_extract_office_media_from_docx(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (7, 9), "blue").save(image_path)

    docx = tmp_path / "sample.docx"
    with ZipFile(docx, "w") as archive:
        archive.write(image_path, "word/media/image1.png")

    output = tmp_path / "out"
    result = extract_path(docx, output, ExtractionOptions())

    assert result.errors == []
    assert result.extracted_count == 1
    assert result.images[0].width == 7
    assert result.images[0].height == 9
    assert Path(result.images[0].output_path).exists()
