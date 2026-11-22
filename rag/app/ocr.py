import asyncio
import io
import logging
import re
from dataclasses import dataclass

import pytesseract
from PIL import Image, UnidentifiedImageError

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}
MIN_WORD_CONFIDENCE = 0
PERCENT = 100.0
# Dates written the way screenshots of posts and articles show them; the caller reports them as "visible on the
# image", never as the publication date (brief scenario F).
VISIBLE_DATES = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia)"
    r"(?:\s+\d{4})?\b",
    re.IGNORECASE,
)
WHITESPACE_LINES = re.compile(r"[ \t]+")


class OcrError(Exception):
    """The image cannot be read: unsupported or corrupt file, too many pixels, or no text in it."""


class OcrUnavailableError(Exception):
    """Tesseract is missing or failed; a technical limitation, never a statement about the image."""


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float
    dates: list[str]
    engine: str


def visible_dates(text: str) -> list[str]:
    seen: list[str] = []
    for match in VISIBLE_DATES.findall(text):
        cleaned = " ".join(match.split())
        if cleaned not in seen:
            seen.append(cleaned)
    return seen


def _clean_text(raw: str) -> str:
    lines = [WHITESPACE_LINES.sub(" ", line).strip() for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)[: settings.ocr_max_text_chars]


def _open_image(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise OcrError("not a readable PNG, JPEG or WEBP image") from error
    if image.format not in SUPPORTED_FORMATS:
        raise OcrError(f"unsupported image format: {image.format}")
    width, height = image.size
    if width * height > settings.ocr_max_pixels:
        raise OcrError("image has too many pixels")
    # verify() exhausts the file; a fresh open is needed for the actual read.
    return Image.open(io.BytesIO(data)).convert("L")


def _run_tesseract(image: Image.Image) -> tuple[str, float]:
    data = pytesseract.image_to_data(
        image,
        lang=settings.ocr_languages,
        output_type=pytesseract.Output.DICT,
        timeout=settings.ocr_timeout_seconds,
    )
    confidences = [
        float(confidence)
        for confidence, word in zip(data["conf"], data["text"], strict=True)
        if str(word).strip() and float(confidence) > MIN_WORD_CONFIDENCE
    ]
    text = pytesseract.image_to_string(image, lang=settings.ocr_languages, timeout=settings.ocr_timeout_seconds)
    confidence = sum(confidences) / len(confidences) / PERCENT if confidences else 0.0
    return text, confidence


async def read_image(data: bytes) -> OcrResult:
    """
    Text of a screenshot or photo, read locally by Tesseract. The image is processed in memory and never stored.
    Empty text is an OcrError (the citizen must paste the text instead); a missing engine is OcrUnavailableError.
    """
    if len(data) > settings.ocr_max_bytes:
        raise OcrError("image larger than the allowed size")
    image = _open_image(data)
    try:
        raw_text, confidence = await asyncio.to_thread(_run_tesseract, image)
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError) as error:
        logger.error("OCR failed: %s", type(error).__name__)
        raise OcrUnavailableError("OCR engine unavailable") from error
    text = _clean_text(raw_text)
    if not text:
        raise OcrError("no readable text in the image")
    return OcrResult(text=text, confidence=round(confidence, 2), dates=visible_dates(text), engine="tesseract")
