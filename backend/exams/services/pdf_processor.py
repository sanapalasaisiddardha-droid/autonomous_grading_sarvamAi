"""PDF processing service — extracts page images and text blocks from PDFs."""

import os
from dataclasses import dataclass, field

import fitz  # PyMuPDF
from django.conf import settings


@dataclass
class TextBlock:
    """A text block extracted from a PDF page with bounding box coordinates (in pixels)."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page_number: int


@dataclass
class PageExtractionResult:
    """Result of extracting a single page from a PDF."""

    page_number: int
    image_path: str
    width: int
    height: int
    text_blocks: list[TextBlock] = field(default_factory=list)


def get_page_image_dir(exam_id: str, sheet_id: str) -> str:
    """Return the directory path for storing page images.

    Args:
        exam_id: UUID of the exam.
        sheet_id: UUID of the answer sheet.

    Returns:
        Absolute path to the page image directory.
    """
    return os.path.join(settings.MEDIA_ROOT, "pages", str(exam_id), str(sheet_id))


def extract_pages(
    pdf_path: str, output_dir: str, dpi: int = 300
) -> list[PageExtractionResult]:
    """Extract page images and text blocks from a PDF file.

    Opens the PDF with PyMuPDF, renders each page as a PNG at the given DPI,
    and extracts text blocks with bounding boxes (converted to pixel coordinates).

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save page images.
        dpi: Resolution for rendering pages (default 300).

    Returns:
        List of PageExtractionResult, one per page.

    Raises:
        FileNotFoundError: If pdf_path does not exist.
        fitz.FileDataError: If the file is not a valid PDF.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    os.makedirs(output_dir, exist_ok=True)

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    results: list[PageExtractionResult] = []

    doc = fitz.open(pdf_path)
    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_number = page_idx + 1  # 1-based

            # Render page as PNG
            pix = page.get_pixmap(matrix=matrix)
            image_filename = f"page_{page_number}.png"
            image_path = os.path.join(output_dir, image_filename)
            pix.save(image_path)

            # Extract text blocks with bounding boxes
            text_blocks = _extract_text_blocks(page, page_number, zoom)

            results.append(
                PageExtractionResult(
                    page_number=page_number,
                    image_path=image_path,
                    width=pix.width,
                    height=pix.height,
                    text_blocks=text_blocks,
                )
            )
    finally:
        doc.close()

    return results


def _extract_text_blocks(
    page: fitz.Page, page_number: int, zoom: float
) -> list[TextBlock]:
    """Extract text blocks from a page, converting coordinates to pixels.

    Args:
        page: A PyMuPDF page object.
        page_number: 1-based page number.
        zoom: Zoom factor (dpi / 72).

    Returns:
        List of TextBlock with pixel-space coordinates.
    """
    blocks: list[TextBlock] = []
    page_dict = page.get_text("dict")

    for block in page_dict.get("blocks", []):
        # Skip image blocks (type 1), only process text blocks (type 0)
        if block.get("type") != 0:
            continue

        # Concatenate all spans in all lines of this block
        text_parts: list[str] = []
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text_parts.append(span.get("text", ""))

        text = " ".join(text_parts).strip()
        if not text:
            continue

        # Convert PDF-point coordinates to pixel coordinates
        bbox = block.get("bbox", (0, 0, 0, 0))
        blocks.append(
            TextBlock(
                text=text,
                x0=bbox[0] * zoom,
                y0=bbox[1] * zoom,
                x1=bbox[2] * zoom,
                y1=bbox[3] * zoom,
                page_number=page_number,
            )
        )

    return blocks
