import asyncio
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main, ocr
from app.config import settings
from app.main import app
from app.ocr import OcrError, OcrResult, OcrUnavailableError, read_image, visible_dates


def png_bytes(width: int = 40, height: int = 20) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_visible_dates_keeps_order_and_dedupes():
    text = "Opublikowano 12.03.2024 o 10:00. Zdjęcie z 12.03.2024 i 2021-05-05, 5 maja 2021."
    assert visible_dates(text) == ["12.03.2024", "2021-05-05", "5 maja 2021"]


def test_read_image_rejects_non_images_and_oversized_files(monkeypatch):
    with pytest.raises(OcrError):
        asyncio.run(read_image(b"%PDF-1.4 not an image"))
    monkeypatch.setattr(settings, "ocr_max_bytes", 10)
    with pytest.raises(OcrError):
        asyncio.run(read_image(png_bytes()))
    monkeypatch.setattr(settings, "ocr_max_bytes", 5_000_000)
    monkeypatch.setattr(settings, "ocr_max_pixels", 100)
    with pytest.raises(OcrError):
        asyncio.run(read_image(png_bytes(20, 20)))


def test_read_image_reports_empty_text_and_missing_engine(monkeypatch):
    monkeypatch.setattr(ocr, "_run_tesseract", lambda image: ("  \n ", 0.0))
    with pytest.raises(OcrError):
        asyncio.run(read_image(png_bytes()))

    def missing(image):
        raise ocr.pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(ocr, "_run_tesseract", missing)
    with pytest.raises(OcrUnavailableError):
        asyncio.run(read_image(png_bytes()))


def test_ocr_endpoint_returns_text_dates_and_engine(client, monkeypatch):
    async def fake_read_image(data: bytes) -> OcrResult:
        return OcrResult(text="Strajk 20.11.2026\nPAP", confidence=0.91, dates=["20.11.2026"], engine="tesseract")

    monkeypatch.setattr(main, "read_image", fake_read_image)
    response = client.post("/ocr", files={"image": ("shot.png", png_bytes(), "image/png")})
    assert response.status_code == 200
    assert response.json() == {
        "text": "Strajk 20.11.2026\nPAP",
        "confidence": 0.91,
        "dates": ["20.11.2026"],
        "engine": "tesseract",
    }


def test_ocr_endpoint_maps_errors(client, monkeypatch):
    async def unreadable(data: bytes) -> OcrResult:
        raise OcrError("no readable text in the image")

    monkeypatch.setattr(main, "read_image", unreadable)
    response = client.post("/ocr", files={"image": ("shot.png", png_bytes(), "image/png")})
    assert response.status_code == 422
    assert "no readable text" in response.json()["detail"]

    async def down(data: bytes) -> OcrResult:
        raise OcrUnavailableError("OCR engine unavailable")

    monkeypatch.setattr(main, "read_image", down)
    assert client.post("/ocr", files={"image": ("shot.png", png_bytes(), "image/png")}).status_code == 503


@pytest.mark.skipif(
    not __import__("shutil").which("tesseract"), reason="tesseract binary not installed (it is in the Docker image)"
)
def test_tesseract_reads_rendered_text():
    from PIL import ImageDraw

    image = Image.new("RGB", (600, 80), "white")
    ImageDraw.Draw(image).text((10, 20), "Strajk generalny 20.11.2026", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result = asyncio.run(read_image(buffer.getvalue()))
    assert "20.11.2026" in result.dates
