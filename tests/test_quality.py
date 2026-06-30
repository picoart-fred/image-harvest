from pathlib import Path

from PIL import Image

from extract_images.quality import ImageSource, build_image_record, file_sha256, mark_duplicates


def test_file_sha256_is_stable(tmp_path: Path) -> None:
    target = tmp_path / "sample.bin"
    target.write_bytes(b"hello")

    assert file_sha256(target) == file_sha256(target)


def test_enrich_image_metadata_reads_dimensions(tmp_path: Path) -> None:
    target = tmp_path / "sample.png"
    Image.new("RGB", (12, 8), "white").save(target)
    image = build_image_record(target, ImageSource(document_path=str(target), extractor="test"))

    assert image.width == 12
    assert image.height == 8
    assert image.format == "PNG"
    assert image.byte_size > 0
    assert image.sha256


def test_duplicate_tracker_marks_second_match(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (4, 4), "red").save(first)
    Image.new("RGB", (4, 4), "red").save(second)

    first_image = build_image_record(first, ImageSource(document_path=str(first), extractor="test"))
    second_image = build_image_record(second, ImageSource(document_path=str(second), extractor="test"))
    marked = mark_duplicates([first_image, second_image])

    assert marked[0].duplicate_of is None
    assert marked[1].duplicate_of == str(first)
