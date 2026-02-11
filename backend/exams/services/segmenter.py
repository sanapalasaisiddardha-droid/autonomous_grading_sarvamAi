"""Segmenter service — detects question boundaries and crops answer regions."""

import logging
import os
import re
from dataclasses import dataclass, field

from PIL import Image, ImageFilter

from .pdf_processor import PageExtractionResult, TextBlock
from .sarvam_client import SarvamPageResult

logger = logging.getLogger(__name__)

# Regex patterns for question markers (same as sarvam_client, for PyMuPDF text)
_QUESTION_PATTERNS = [
    re.compile(r"^Q(\d+)", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Question\s+(\d+)", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(\d+)\.\s", re.MULTILINE),
    re.compile(r"^(\d+)\)\s", re.MULTILINE),
    re.compile(r"^\((\d+)\)\s", re.MULTILINE),
]

# Extended patterns for OCR — also search inside text, not just start
_QUESTION_PATTERNS_SEARCH = [
    re.compile(r"(?:^|\n)\s*Q(\d+)", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(\d+)\)\s"),
    re.compile(r"(?:^|\n)\s*(\d+)\.\s"),
    re.compile(r"(?:^|\n)\s*\((\d+)\)\s"),
]

# Confidence thresholds
CONFIDENCE_HIGH = 0.80
CONFIDENCE_LOW = 0.50

# Padding above question marker to include question text
MARKER_PADDING_PX = 20


@dataclass
class DetectedMarker:
    """A detected question marker with position information."""

    question_number: int
    y_position: float
    page_number: int
    source: str  # "pymupdf", "sarvam", "ocr", "both", or "estimated"
    confidence: float


@dataclass
class CropRegion:
    """Defines the crop region for a single question's answer."""

    question_number: int
    segments: list[dict] = field(default_factory=list)
    # Each segment: {"page_number": int, "y_start": float, "y_end": float}
    confidence: float = 0.85
    source: str = "pymupdf"


@dataclass
class SegmentationResult:
    """Overall result of segmentation for an answer sheet."""

    crop_regions: list[CropRegion] = field(default_factory=list)
    overall_confidence: float = 0.0
    missing_questions: list[int] = field(default_factory=list)
    status: str = "segmented"  # "segmented", "needs_review", "failed"


def detect_question_markers_pymupdf(
    pages: list[PageExtractionResult],
) -> list[DetectedMarker]:
    """Detect question markers from PyMuPDF-extracted text blocks.

    Scans text blocks for question number patterns (Q1, 1., etc.).
    Returns the first occurrence of each question number.

    Args:
        pages: List of PageExtractionResult from pdf_processor.

    Returns:
        List of DetectedMarker sorted by (page_number, y_position).
    """
    markers: list[DetectedMarker] = []
    seen_questions: set[int] = set()

    for page in pages:
        for block in page.text_blocks:
            q_num = _match_question_number(block.text)
            if q_num is not None and q_num not in seen_questions:
                seen_questions.add(q_num)
                markers.append(
                    DetectedMarker(
                        question_number=q_num,
                        y_position=block.y0,
                        page_number=page.page_number,
                        source="pymupdf",
                        confidence=0.85,
                    )
                )

    markers.sort(key=lambda m: (m.page_number, m.y_position))
    return markers


def _ocr_margin_crop(
    img: Image.Image,
    page_number: int,
    pytesseract,  # module reference
    total_questions: int | None = None,
) -> list[DetectedMarker]:
    """Run OCR on the left margin of a page image to find question numbers.

    Uses multiple preprocessing variants (grayscale, binary threshold,
    downscaled) x multiple PSM modes to maximize detection of handwritten
    or circled question numbers. Only structured patterns (e.g. "1.", "2)",
    "Q3") are accepted.

    Args:
        img: Full page PIL Image.
        page_number: 1-based page number.
        pytesseract: The pytesseract module.

    Returns:
        List of DetectedMarker found in the margin.
    """
    # Crop left margin: 15% of width, min 600px — wide enough to capture
    # circled question numbers + closing parenthesis on high-res scans
    margin_width = max(600, int(img.width * 0.15))
    margin_width = min(margin_width, img.width)
    margin_crop = img.crop((0, 0, margin_width, img.height))

    # Build preprocessing variants — different transforms catch different numbers
    variants: list[tuple[str, Image.Image, float]] = []  # (name, image, y_scale)

    gray = margin_crop.convert("L")
    binary = gray.point(lambda x: 0 if x < 128 else 255, "1").convert("L")
    variants.append(("gray", gray, 1.0))
    variants.append(("binary", binary, 1.0))

    # Downscaled version for very high-res images (>4000px wide)
    if img.width > 4000:
        target_width = 2480  # ~A4 at 300 DPI
        scale = target_width / img.width
        resized = margin_crop.resize(
            (int(margin_crop.width * scale), int(margin_crop.height * scale)),
            Image.LANCZOS,
        )
        resized_gray = resized.convert("L")
        # y_scale converts resized y-coordinates back to original image space
        variants.append(("resized_gray", resized_gray, 1.0 / scale))

    # Collect all candidates from all variants, allowing duplicates
    candidates: list[DetectedMarker] = []

    for variant_name, variant_img, y_scale in variants:
        for psm in (6, 11):
            config = f"--psm {psm} --oem 1"
            try:
                data = pytesseract.image_to_data(
                    variant_img, config=config, output_type=pytesseract.Output.DICT
                )
            except Exception as e:
                logger.debug(
                    "Margin OCR %s psm=%d page %d: %s",
                    variant_name, psm, page_number, e,
                )
                continue

            # Build lines from words
            lines: dict[tuple[int, int], list[dict]] = {}
            for i in range(len(data["text"])):
                word = data["text"][i].strip()
                conf = int(data["conf"][i])
                if not word or conf < 30:
                    continue
                key = (data["block_num"][i], data["line_num"][i])
                if key not in lines:
                    lines[key] = []
                lines[key].append(
                    {
                        "text": word,
                        "top": data["top"][i],
                        "conf": conf,
                    }
                )

            for _key, words in sorted(lines.items()):
                line_text = " ".join(w["text"] for w in words)
                q_num = _match_question_number_margin(line_text)
                if q_num is not None and total_questions is not None and q_num > total_questions:
                    q_num = None
                if q_num is not None:
                    y_pos = min(w["top"] for w in words) * y_scale
                    avg_conf = sum(w["conf"] for w in words) / len(words)
                    candidates.append(
                        DetectedMarker(
                            question_number=q_num,
                            y_position=float(y_pos),
                            page_number=page_number,
                            source="ocr-margin",
                            confidence=avg_conf / 100.0,
                        )
                    )

    # Deduplicate: for each question number, keep the detection with
    # highest confidence (best y-position estimate)
    best_by_q: dict[int, DetectedMarker] = {}
    for c in candidates:
        prev = best_by_q.get(c.question_number)
        if prev is None or c.confidence > prev.confidence:
            best_by_q[c.question_number] = c

    # Sanity filter: question numbers must increase with y-position.
    # Removes false positives like Q2 detected at bottom of page.
    sorted_markers = sorted(best_by_q.values(), key=lambda m: m.y_position)
    markers: list[DetectedMarker] = []
    max_q = -1
    for m in sorted_markers:
        if m.question_number > max_q:
            markers.append(m)
            max_q = m.question_number

    return markers


def detect_question_markers_ocr(
    pages: list[PageExtractionResult],
    total_questions: int | None = None,
) -> list[DetectedMarker]:
    """Detect question markers using pytesseract OCR on page images.

    Two-pass strategy (each pass has its own seen_questions to avoid
    one pass blocking the other):
    1. Left-margin crop (first 8% of width) — isolates question numbers.
    2. Full-page OCR — catches anything the margin pass missed.

    Results are merged: if both passes find the same question, the margin
    result is preferred (its y-position is more accurate since it's from
    a cleaner crop).

    Args:
        pages: List of PageExtractionResult (with image_path).

    Returns:
        List of DetectedMarker sorted by (page_number, y_position).
    """
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed, skipping OCR detection")
        return []

    margin_by_q: dict[int, DetectedMarker] = {}
    fullpage_by_q: dict[int, DetectedMarker] = {}

    for page in pages:
        if not page.image_path or not os.path.exists(page.image_path):
            continue

        try:
            img = Image.open(page.image_path)

            # --- Pass 1: Left-margin OCR (independent) ---
            margin_markers = _ocr_margin_crop(
                img, page.page_number, pytesseract,
                total_questions=total_questions,
            )
            for m in margin_markers:
                prev = margin_by_q.get(m.question_number)
                if prev is None or m.page_number < prev.page_number or (m.page_number == prev.page_number and m.confidence > prev.confidence):
                    margin_by_q[m.question_number] = m
            if margin_markers:
                logger.info(
                    "Margin OCR page %d: found Q%s",
                    page.page_number,
                    ", Q".join(str(m.question_number) for m in margin_markers),
                )

            # --- Pass 2: Full-page OCR (independent) ---
            data = pytesseract.image_to_data(
                img, config="--psm 6 --oem 1", output_type=pytesseract.Output.DICT
            )

            lines: dict[tuple[int, int], list[dict]] = {}
            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                conf = int(data["conf"][i])
                if not text or conf < 40:
                    continue
                key = (data["block_num"][i], data["line_num"][i])
                if key not in lines:
                    lines[key] = []
                lines[key].append(
                    {
                        "text": text,
                        "top": data["top"][i],
                        "left": data["left"][i],
                        "conf": conf,
                    }
                )

            for _key, words in sorted(lines.items()):
                line_text = " ".join(w["text"] for w in words)
                normalized_line = _normalize_ocr_text(line_text)
                avg_conf = sum(w["conf"] for w in words) / len(words)

                # Find ALL question markers in this line (not just the first).
                # When tesseract merges multiple questions into one line
                # (e.g. "8) ... 9) b) 600mg"), we need to find each one.
                found_in_line: set[int] = set()
                for search_text in (line_text, normalized_line):
                    for pattern in _QUESTION_PATTERNS_SEARCH:
                        for match in pattern.finditer(search_text):
                            q_num = int(match.group(1))
                            if q_num < 1 or q_num > 99:
                                continue
                            if total_questions is not None and q_num > total_questions:
                                continue
                            # Decimal filter: reject if next char is a digit
                            remaining = search_text[match.end():]
                            if remaining and remaining[0].isdigit():
                                continue
                            if q_num in found_in_line:
                                continue
                            found_in_line.add(q_num)

                            # Estimate y-position: find which word contains
                            # this match based on character offset in the
                            # joined line_text
                            match_pos = match.start()
                            char_count = 0
                            best_word = words[0]
                            for w in words:
                                word_end = char_count + len(w["text"]) + 1  # +1 for space
                                if match_pos < word_end:
                                    best_word = w
                                    break
                                char_count = word_end
                            y_pos = best_word["top"]

                            prev = fullpage_by_q.get(q_num)
                            if prev is None or page.page_number < prev.page_number or (page.page_number == prev.page_number and avg_conf / 100.0 > prev.confidence):
                                fullpage_by_q[q_num] = DetectedMarker(
                                    question_number=q_num,
                                    y_position=float(y_pos),
                                    page_number=page.page_number,
                                    source="ocr",
                                    confidence=avg_conf / 100.0,
                                )
        except Exception as e:
            logger.warning("OCR failed for page %d: %s", page.page_number, e)

    # Merge: prefer earlier page; if same page, prefer margin
    all_q = set(margin_by_q.keys()) | set(fullpage_by_q.keys())
    markers: list[DetectedMarker] = []
    for q_num in all_q:
        margin_m = margin_by_q.get(q_num)
        full_m = fullpage_by_q.get(q_num)
        if margin_m and full_m:
            # Prefer earlier page; if same page, prefer margin
            if full_m.page_number < margin_m.page_number:
                m = full_m
            else:
                m = margin_m
            m.confidence = min(0.90, m.confidence + 0.1)
            m.source = "ocr-margin+ocr"
            markers.append(m)
        elif margin_m:
            markers.append(margin_m)
        else:
            markers.append(full_m)

    markers.sort(key=lambda m: (m.page_number, m.y_position))
    return markers


def _validate_monotonicity(markers: list[DetectedMarker]) -> list[DetectedMarker]:
    """Remove markers that violate cross-page monotonicity.

    If a question number appears on a later page but a higher question number
    was already seen on an earlier page, the later detection is likely a
    false positive (e.g., "3" in a calculation on page 2 when real Q3 is on page 1).

    Args:
        markers: Sorted list of DetectedMarker by (page_number, y_position).

    Returns:
        Filtered list with cross-page violations removed.
    """
    if not markers:
        return markers

    # Group by question number — keep earliest page detection
    best_by_q: dict[int, DetectedMarker] = {}
    for m in markers:
        prev = best_by_q.get(m.question_number)
        if prev is None or m.page_number < prev.page_number or (
            m.page_number == prev.page_number and m.confidence > prev.confidence
        ):
            best_by_q[m.question_number] = m

    # Sort by (page, y) and enforce monotonicity
    sorted_markers = sorted(best_by_q.values(), key=lambda m: (m.page_number, m.y_position))
    result: list[DetectedMarker] = []
    max_q = -1
    for m in sorted_markers:
        if m.question_number > max_q:
            result.append(m)
            max_q = m.question_number
        else:
            logger.debug(
                "Monotonicity: dropping Q%d on page %d (max seen Q%d)",
                m.question_number, m.page_number, max_q,
            )

    return result


def merge_detections(
    pymupdf_markers: list[DetectedMarker],
    sarvam_results: list[SarvamPageResult] | None,
    pages: list[PageExtractionResult],
    ocr_markers: list[DetectedMarker] | None = None,
    total_questions: int | None = None,
) -> list[DetectedMarker]:
    """Merge question detections from PyMuPDF, Sarvam Vision, and OCR.

    Priority: PyMuPDF positions preferred when available, then Sarvam
    (with coordinate scaling), then OCR.

    Args:
        pymupdf_markers: Markers from PyMuPDF extraction.
        sarvam_results: Results from Sarvam Vision (may be None).
        pages: Page data for position estimation.
        ocr_markers: Markers from pytesseract OCR (may be None).

    Returns:
        Merged list of DetectedMarker sorted by (page_number, y_position).
    """
    # Index PyMuPDF markers by question number
    pymupdf_by_q: dict[int, DetectedMarker] = {
        m.question_number: m for m in pymupdf_markers
    }

    # Index OCR markers by question number
    ocr_by_q: dict[int, DetectedMarker] = {}
    if ocr_markers:
        for m in ocr_markers:
            if m.question_number not in ocr_by_q:
                ocr_by_q[m.question_number] = m

    # Build page dimension lookups
    page_heights: dict[int, int] = {p.page_number: p.height for p in pages}

    # Collect Sarvam detections with y_position and page image dimensions
    sarvam_by_q: dict[int, "SarvamDetectedQuestion"] = {}
    sarvam_page_dims: dict[int, tuple[int, int]] = {}
    if sarvam_results:
        for result in sarvam_results:
            if not result.success:
                continue
            if result.image_width > 0 and result.image_height > 0:
                sarvam_page_dims[result.page_number] = (
                    result.image_width,
                    result.image_height,
                )
            for dq in result.detected_questions:
                if dq.question_number not in sarvam_by_q:
                    sarvam_by_q[dq.question_number] = dq

    merged: list[DetectedMarker] = []
    all_questions = set(pymupdf_by_q.keys()) | set(sarvam_by_q.keys()) | set(ocr_by_q.keys())
    if total_questions is not None:
        all_questions = {q for q in all_questions if q <= total_questions}

    for q_num in all_questions:
        in_pymupdf = q_num in pymupdf_by_q
        in_sarvam = q_num in sarvam_by_q
        in_ocr = q_num in ocr_by_q

        sources = []
        if in_pymupdf:
            sources.append("pymupdf")
        if in_sarvam:
            sources.append("sarvam")
        if in_ocr:
            sources.append("ocr")

        if in_pymupdf:
            # PyMuPDF has best coordinates — use as base
            marker = pymupdf_by_q[q_num]
            if len(sources) > 1:
                marker.confidence = min(0.95, marker.confidence + 0.1)
                marker.source = "+".join(sources)
            merged.append(marker)
        elif in_sarvam:
            dq = sarvam_by_q[q_num]
            # Scale Sarvam y_position to PyMuPDF image space
            y_pos = dq.y_position
            sarvam_dims = sarvam_page_dims.get(dq.page_number)
            pymupdf_height = page_heights.get(dq.page_number, 0)
            if sarvam_dims and sarvam_dims[1] > 0 and pymupdf_height > 0:
                scale = pymupdf_height / sarvam_dims[1]
                y_pos = dq.y_position * scale

            conf = dq.confidence
            source = "sarvam"
            if in_ocr:
                conf = min(0.90, conf + 0.1)
                source = "sarvam+ocr"

            merged.append(
                DetectedMarker(
                    question_number=q_num,
                    y_position=y_pos,
                    page_number=dq.page_number,
                    source=source,
                    confidence=conf,
                )
            )
        elif in_ocr:
            merged.append(ocr_by_q[q_num])

    merged = _validate_monotonicity(merged)
    merged.sort(key=lambda m: (m.page_number, m.y_position))
    return merged


def _effective_page_height(image_path: str, page_height: int) -> int:
    """Find the effective page height by detecting where content ends.

    Scans upward from page bottom to find the last row with significant
    ink/content. Returns a height that trims blank bottom margins.

    Args:
        image_path: Path to the page image.
        page_height: Raw pixel height of the page.

    Returns:
        Effective height (trimmed of bottom blank space), with 50px padding.
    """
    try:
        img = Image.open(image_path).convert("L")
    except Exception:
        return page_height

    try:
        import numpy as np

        arr = np.array(img)
    except ImportError:
        return page_height

    # Scan from bottom upward
    white_threshold = 200
    min_content_ratio = 0.02  # At least 2% of pixels in a row must be dark

    last_content_row = page_height
    for y in range(arr.shape[0] - 1, 0, -1):
        dark_ratio = (arr[y, :] < white_threshold).mean()
        if dark_ratio >= min_content_ratio:
            last_content_row = y
            break

    # Add padding below last content
    effective = min(page_height, last_content_row + 50)

    if effective < page_height - 100:
        logger.debug(
            "Effective page height: %d -> %d (trimmed %dpx blank bottom)",
            page_height,
            effective,
            page_height - effective,
        )

    return effective



def _detect_whitespace_gaps(
    image_path: str,
    y_start: int,
    y_end: int,
    min_gap_height: int = 30,
) -> list[int]:
    """Detect horizontal whitespace gaps in a page image region.

    Scans rows between y_start and y_end, looking for consecutive rows
    of mostly white pixels (>95% white). Returns the y-center of each
    whitespace gap that is at least min_gap_height tall.

    Args:
        image_path: Path to the page image file.
        y_start: Top y-coordinate of the region to scan.
        y_end: Bottom y-coordinate of the region to scan.
        min_gap_height: Minimum number of consecutive white rows to
            count as a gap.

    Returns:
        List of y-coordinates (in original image space) at the center
        of each detected whitespace gap, sorted top to bottom.
    """
    try:
        img = Image.open(image_path).convert("L")
    except Exception:
        return []

    y_start = max(0, int(y_start))
    y_end = min(img.height, int(y_end))

    if y_end <= y_start:
        return []

    try:
        import numpy as np
    except ImportError:
        logger.debug("numpy not available, whitespace gap detection skipped")
        return []

    # Crop the region and check row brightness
    region = np.array(img.crop((0, y_start, img.width, y_end)))

    # A row is "white" if >95% of pixels are above threshold (200)
    white_threshold = 200
    white_ratio = (region > white_threshold).mean(axis=1)
    is_white_row = white_ratio > 0.95

    # Find contiguous white row runs
    gaps: list[int] = []
    gap_start = None
    for i, is_white in enumerate(is_white_row):
        if is_white:
            if gap_start is None:
                gap_start = i
        else:
            if gap_start is not None:
                gap_height = i - gap_start
                if gap_height >= min_gap_height:
                    gap_center = y_start + gap_start + gap_height // 2
                    gaps.append(gap_center)
                gap_start = None

    # Handle trailing gap at end of region
    if gap_start is not None:
        gap_height = len(is_white_row) - gap_start
        if gap_height >= min_gap_height:
            gap_center = y_start + gap_start + gap_height // 2
            gaps.append(gap_center)

    return gaps


def fill_missing_with_equal_split(
    markers: list[DetectedMarker],
    pages: list[PageExtractionResult],
    total_questions: int,
) -> list[DetectedMarker]:
    """Fill in missing questions using whitespace gap detection with equal-split fallback.

    First attempts to detect natural whitespace gaps between handwritten answers
    in the page image. If the number of detected gaps matches the number of
    missing questions in a region, uses those gap positions for more accurate
    boundaries. Otherwise falls back to equal spacing.

    Uses detected markers as anchors and distributes undetected questions
    into the gaps between them. For example, if Q8 is found at top of
    page 2 and Q1-Q7 are missing, page 1 is divided into 7 equal regions.

    Args:
        markers: Sorted list of detected markers.
        pages: Page extraction data.
        total_questions: Expected number of questions.

    Returns:
        Complete list of markers for all questions, sorted.
    """
    if total_questions <= 0:
        return markers

    found_questions = {m.question_number for m in markers}
    missing = [q for q in range(1, total_questions + 1) if q not in found_questions]

    if not missing:
        return markers

    page_heights: dict[int, int] = {p.page_number: p.height for p in pages}
    sorted_pages = sorted(page_heights.keys())

    if not sorted_pages:
        return markers

    # Trim blank bottom margins for better equal-split accuracy
    page_images: dict[int, str] = {
        p.page_number: p.image_path for p in pages if p.image_path
    }
    for page_num in sorted_pages:
        img_path = page_images.get(page_num)
        if img_path and os.path.exists(img_path):
            page_heights[page_num] = _effective_page_height(
                img_path, page_heights[page_num]
            )

    # Build a timeline: (page, y) positions for all detected markers
    # Plus virtual start (page 1, y=0) and end (last page, y=height)
    anchors: list[tuple[int, float, int | None]] = []  # (page, y, question_number)
    anchors.append((sorted_pages[0], 0.0, None))  # start of document

    for m in markers:
        anchors.append((m.page_number, m.y_position, m.question_number))

    last_page = sorted_pages[-1]
    anchors.append((last_page, float(page_heights[last_page]), None))  # end of document

    # Convert anchors to a linear position (cumulative y across pages)
    def to_linear(page: int, y: float) -> float:
        linear = 0.0
        for p in sorted_pages:
            if p < page:
                linear += page_heights[p]
            elif p == page:
                linear += y
                break
        return linear

    def from_linear(linear_pos: float) -> tuple[int, float]:
        remaining = linear_pos
        for p in sorted_pages:
            h = page_heights[p]
            if remaining <= h:
                return (p, remaining)
            remaining -= h
        return (sorted_pages[-1], page_heights[sorted_pages[-1]])

    # For each missing question, find which gap it belongs in
    # A gap is between two consecutive detected questions (or document start/end)
    # Sort all question numbers (detected + missing)
    all_q_sorted = sorted(
        [(m.question_number, to_linear(m.page_number, m.y_position)) for m in markers],
        key=lambda x: x[0],
    )

    # Pre-compute whitespace-based gap positions for each contiguous run of
    # missing questions between anchor markers.  We group missing questions
    # by (prev_marker, next_marker) so that we call _detect_whitespace_gaps
    # once per gap region instead of once per missing question.
    #
    # gap_key = (q_after_prev, q_before_next)  ->  list of gap y-positions or None
    _whitespace_cache: dict[tuple[int, int], list[int] | None] = {}

    def _get_whitespace_positions(
        q_after_prev: int,
        q_before_next: int,
        prev_marker: DetectedMarker | None,
        next_marker: DetectedMarker | None,
        questions_in_gap: int,
    ) -> list[int] | None:
        """Try whitespace gap detection for a contiguous run of missing questions.

        Returns a list of y-positions (one per missing question) if the number
        of detected gaps matches the number of missing questions, or None to
        signal that equal-split should be used as fallback.
        """
        cache_key = (q_after_prev, q_before_next)
        if cache_key in _whitespace_cache:
            return _whitespace_cache[cache_key]

        # Determine the page and y-range to scan
        if prev_marker:
            scan_page = prev_marker.page_number
            scan_y_start = int(prev_marker.y_position)
        else:
            scan_page = sorted_pages[0]
            scan_y_start = 0

        if next_marker:
            scan_page_end = next_marker.page_number
            scan_y_end = int(next_marker.y_position)
        else:
            scan_page_end = last_page
            scan_y_end = page_heights.get(last_page, 0)

        # Only attempt whitespace detection for same-page gaps
        # (cross-page gaps are harder and equal-split is reasonable)
        if scan_page != scan_page_end:
            _whitespace_cache[cache_key] = None
            return None

        img_path = page_images.get(scan_page)
        if not img_path or not os.path.exists(img_path):
            _whitespace_cache[cache_key] = None
            return None

        try:
            gaps = _detect_whitespace_gaps(
                img_path, scan_y_start, scan_y_end
            )
        except Exception as e:
            logger.debug(
                "Whitespace gap detection failed for page %d: %s",
                scan_page, e,
            )
            _whitespace_cache[cache_key] = None
            return None

        if len(gaps) == questions_in_gap:
            logger.info(
                "Whitespace gaps: found %d gaps matching %d missing questions "
                "between Q%d and Q%d on page %d",
                len(gaps), questions_in_gap,
                q_after_prev, q_before_next, scan_page,
            )
            _whitespace_cache[cache_key] = gaps
            return gaps

        logger.debug(
            "Whitespace gaps: found %d gaps but need %d between Q%d and Q%d "
            "on page %d — falling back to equal-split",
            len(gaps), questions_in_gap,
            q_after_prev, q_before_next, scan_page,
        )
        _whitespace_cache[cache_key] = None
        return None

    # Build gap structure: find contiguous runs of missing questions
    # and which detected markers bound them
    estimated: list[DetectedMarker] = []
    whitespace_used_count = 0

    for q_num in missing:
        # Find the nearest detected markers before and after this question
        prev_marker = None
        next_marker = None

        for m in markers:
            if m.question_number < q_num:
                if prev_marker is None or m.question_number > prev_marker.question_number:
                    prev_marker = m
            elif m.question_number > q_num:
                if next_marker is None or m.question_number < next_marker.question_number:
                    next_marker = m

        # Determine the linear range for this gap
        if prev_marker:
            gap_start = to_linear(prev_marker.page_number, prev_marker.y_position)
            q_after_prev = prev_marker.question_number
        else:
            gap_start = 0.0
            q_after_prev = 0  # virtual Q0 at document start

        if next_marker:
            gap_end = to_linear(next_marker.page_number, next_marker.y_position)
            q_before_next = next_marker.question_number
        else:
            gap_end = to_linear(last_page, float(page_heights[last_page]))
            q_before_next = total_questions + 1  # virtual Q(n+1) at document end

        # How many questions are in this gap (including this one)?
        questions_in_gap = q_before_next - q_after_prev - 1
        if questions_in_gap <= 0:
            questions_in_gap = 1

        # Position of this question within the gap
        position_in_gap = q_num - q_after_prev  # 1-based index within gap

        # Try whitespace gap detection first
        ws_positions = _get_whitespace_positions(
            q_after_prev, q_before_next,
            prev_marker, next_marker,
            questions_in_gap,
        )

        if ws_positions is not None:
            # Use whitespace-detected gap position (0-indexed from position_in_gap)
            gap_y = ws_positions[position_in_gap - 1]
            # Determine which page this y belongs to
            if prev_marker:
                ws_page = prev_marker.page_number
            else:
                ws_page = sorted_pages[0]

            estimated.append(
                DetectedMarker(
                    question_number=q_num,
                    y_position=float(gap_y),
                    page_number=ws_page,
                    source="estimated-whitespace",
                    confidence=0.55,
                )
            )
            whitespace_used_count += 1
        else:
            # Fall back to equal spacing
            gap_size = gap_end - gap_start
            step = gap_size / (questions_in_gap + 1)
            linear_pos = gap_start + step * position_in_gap

            page, y = from_linear(linear_pos)

            estimated.append(
                DetectedMarker(
                    question_number=q_num,
                    y_position=y,
                    page_number=page,
                    source="estimated",
                    confidence=0.40,
                )
            )

    # Combine detected + estimated markers
    all_markers = list(markers) + estimated
    all_markers.sort(key=lambda m: (m.page_number, m.y_position))

    # Sanity check: warn about suspiciously small crop regions
    sorted_check = sorted(all_markers, key=lambda m: (m.page_number, m.y_position))
    for i in range(len(sorted_check) - 1):
        curr = sorted_check[i]
        nxt = sorted_check[i + 1]
        if curr.page_number == nxt.page_number:
            height = nxt.y_position - curr.y_position
            if height < 50 and curr.source not in ("estimated", "estimated-whitespace"):
                logger.warning(
                    "Suspicious: Q%d has only %.0fpx height on page %d (source=%s) — possible false positive",
                    curr.question_number, height, curr.page_number, curr.source,
                )

    logger.info(
        "Gap-fill: filled %d missing questions (had %d detected, total %d) — "
        "%d via whitespace detection, %d via equal-split",
        len(estimated),
        len(markers),
        total_questions,
        whitespace_used_count,
        len(estimated) - whitespace_used_count,
    )

    return all_markers


def _verify_estimated_markers(
    markers: list[DetectedMarker],
    pages: list[PageExtractionResult],
    total_questions: int,
) -> list[DetectedMarker]:
    """Re-OCR tight crops around estimated markers to find actual positions.

    For each 'estimated' marker, crops a small region around the estimated
    y-position from the page image and runs pytesseract to find the actual
    question number marker. If found, updates the position.

    Args:
        markers: List of DetectedMarker (some with source="estimated").
        pages: List of PageExtractionResult with image paths.
        total_questions: Expected number of questions.

    Returns:
        List of DetectedMarker with estimated markers refined where possible.
    """
    try:
        import pytesseract
    except ImportError:
        return markers

    page_images = {p.page_number: p.image_path for p in pages if p.image_path}
    page_heights = {p.page_number: p.height for p in pages}

    refined = []
    for marker in markers:
        if marker.source != "estimated":
            refined.append(marker)
            continue

        img_path = page_images.get(marker.page_number)
        if not img_path or not os.path.exists(img_path):
            refined.append(marker)
            continue

        try:
            img = Image.open(img_path)

            # Search window: +-400px around estimated position, left 20% margin
            search_margin = 400
            y_start = max(0, int(marker.y_position - search_margin))
            y_end = min(img.height, int(marker.y_position + search_margin))
            x_end = max(500, int(img.width * 0.20))

            crop = img.crop((0, y_start, x_end, y_end))
            gray_crop = crop.convert("L")

            best_q = None
            best_y = None
            best_conf = 0

            for psm in (6, 11, 4):
                try:
                    data = pytesseract.image_to_data(
                        gray_crop, config=f"--psm {psm} --oem 1",
                        output_type=pytesseract.Output.DICT
                    )
                except Exception:
                    continue

                for i in range(len(data["text"])):
                    word = data["text"][i].strip()
                    conf = int(data["conf"][i])
                    if not word or conf < 20:
                        continue

                    # Try to match question number (with normalization)
                    q_num = _match_question_number_margin(word)
                    if q_num is not None and q_num == marker.question_number:
                        word_y = y_start + data["top"][i]
                        if conf > best_conf:
                            best_q = q_num
                            best_y = word_y
                            best_conf = conf

            if best_q is not None and best_y is not None:
                logger.info(
                    "Verification: Q%d refined from y=%.0f to y=%.0f (conf=%d)",
                    best_q, marker.y_position, best_y, best_conf,
                )
                refined.append(DetectedMarker(
                    question_number=best_q,
                    y_position=float(best_y),
                    page_number=marker.page_number,
                    source="verified",
                    confidence=best_conf / 100.0,
                ))
            else:
                refined.append(marker)
        except Exception as e:
            logger.debug("Verification failed for Q%d: %s", marker.question_number, e)
            refined.append(marker)

    refined.sort(key=lambda m: (m.page_number, m.y_position))
    return refined


def calculate_crop_regions(
    markers: list[DetectedMarker],
    pages: list[PageExtractionResult],
    total_questions: int,
) -> SegmentationResult:
    """Calculate crop regions for each question based on detected markers.

    Between consecutive markers: crop from marker y to next marker y.
    Multi-page: crop marker_page y->bottom, full intermediate pages, next_marker_page top->y.
    Last question: marker to end of last page.

    Args:
        markers: Sorted list of detected markers.
        pages: Page extraction data.
        total_questions: Expected number of questions.

    Returns:
        SegmentationResult with crop regions and status.
    """
    if not markers:
        return SegmentationResult(
            crop_regions=[],
            overall_confidence=0.0,
            missing_questions=list(range(1, total_questions + 1)),
            status="failed",
        )

    page_heights: dict[int, int] = {p.page_number: p.height for p in pages}
    last_page = max(page_heights.keys())
    crop_regions: list[CropRegion] = []

    for i, marker in enumerate(markers):
        q_num = marker.question_number
        # Start y: marker position minus padding (don't go below 0)
        start_y = max(0, marker.y_position - MARKER_PADDING_PX)
        start_page = marker.page_number

        # Determine end position
        if i + 1 < len(markers):
            next_marker = markers[i + 1]
            end_page = next_marker.page_number
            end_y = max(0, next_marker.y_position - MARKER_PADDING_PX)
        else:
            # Last question: extend to bottom of last page
            end_page = last_page
            end_y = page_heights.get(last_page, 0)

        # Build segments for this crop region
        segments: list[dict] = []

        if start_page == end_page:
            # Single page crop
            segments.append(
                {
                    "page_number": start_page,
                    "y_start": start_y,
                    "y_end": end_y,
                }
            )
        else:
            # Multi-page crop
            # First page: from marker to bottom
            segments.append(
                {
                    "page_number": start_page,
                    "y_start": start_y,
                    "y_end": page_heights.get(start_page, 0),
                }
            )
            # Intermediate full pages
            for p in range(start_page + 1, end_page):
                if p in page_heights:
                    segments.append(
                        {
                            "page_number": p,
                            "y_start": 0,
                            "y_end": page_heights[p],
                        }
                    )
            # Last page: from top to next marker
            segments.append(
                {
                    "page_number": end_page,
                    "y_start": 0,
                    "y_end": end_y,
                }
            )

        crop_regions.append(
            CropRegion(
                question_number=q_num,
                segments=segments,
                confidence=marker.confidence,
                source=marker.source,
            )
        )

    # Check for missing questions
    found_questions = {r.question_number for r in crop_regions}
    missing = [q for q in range(1, total_questions + 1) if q not in found_questions]

    # Calculate overall confidence
    if crop_regions:
        base_confidence = sum(r.confidence for r in crop_regions) / len(crop_regions)
        found_ratio = len(found_questions) / max(total_questions, 1)
        overall_confidence = base_confidence * found_ratio
    else:
        overall_confidence = 0.0

    # Determine status
    if overall_confidence >= CONFIDENCE_HIGH:
        status = "segmented"
    elif overall_confidence >= CONFIDENCE_LOW or len(crop_regions) > 0:
        status = "needs_review"
    else:
        status = "failed"

    return SegmentationResult(
        crop_regions=crop_regions,
        overall_confidence=overall_confidence,
        missing_questions=missing,
        status=status,
    )


def crop_and_save_segments(
    crop_regions: list[CropRegion],
    pages: list[PageExtractionResult],
    output_base_dir: str,
    sheet_anonymous_id: str,
) -> list[dict]:
    """Crop answer regions from page images and save as segment images.

    Multi-page answers are vertically stitched into a single image.

    Args:
        crop_regions: List of CropRegion defining what to crop.
        pages: Page extraction data (with image paths).
        output_base_dir: Base directory (e.g., media/segments/{exam_id}).
        sheet_anonymous_id: Anonymous ID for filename.

    Returns:
        List of dicts with segment metadata for creating AnswerSegment records.
    """
    page_images: dict[int, str] = {p.page_number: p.image_path for p in pages}
    saved_segments: list[dict] = []

    for region in crop_regions:
        q_dir = os.path.join(output_base_dir, str(region.question_number))
        os.makedirs(q_dir, exist_ok=True)

        # Crop fragments from each page segment
        fragments: list[Image.Image] = []
        for seg in region.segments:
            page_num = seg["page_number"]
            image_path = page_images.get(page_num)
            if not image_path or not os.path.exists(image_path):
                logger.warning(
                    "Page image not found for page %d: %s", page_num, image_path
                )
                continue

            img = Image.open(image_path)
            y_start = max(0, int(seg["y_start"]))
            y_end = min(img.height, int(seg["y_end"]))

            if y_end <= y_start:
                continue

            cropped = img.crop((0, y_start, img.width, y_end))
            fragments.append(cropped)

        if not fragments:
            logger.warning(
                "No fragments for question %d, sheet %s",
                region.question_number,
                sheet_anonymous_id,
            )
            continue

        # Stitch fragments if multi-page
        if len(fragments) == 1:
            final_image = fragments[0]
        else:
            final_image = stitch_images_vertically(fragments)

        # Save
        filename = f"{sheet_anonymous_id}.png"
        output_path = os.path.join(q_dir, filename)
        final_image.save(output_path, "PNG")

        # Build boundary data
        boundary_data = {
            "segments": region.segments,
            "source": region.source,
        }

        saved_segments.append(
            {
                "question_number": region.question_number,
                "image_path": output_path,
                "page_number": region.segments[0]["page_number"],
                "confidence": region.confidence,
                "boundary_data": boundary_data,
                "needs_review": region.confidence < CONFIDENCE_HIGH,
            }
        )

    return saved_segments


def stitch_images_vertically(images: list[Image.Image]) -> Image.Image:
    """Stitch multiple images vertically into one tall image.

    Args:
        images: List of PIL Image objects to stitch.

    Returns:
        Single vertically stitched PIL Image.
    """
    total_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)

    stitched = Image.new("RGB", (total_width, total_height), (255, 255, 255))
    y_offset = 0
    for img in images:
        stitched.paste(img, (0, y_offset))
        y_offset += img.height

    return stitched


# Flexible patterns for margin OCR — use .search() instead of .match(),
# and allow end-of-string as alternative to trailing whitespace
_MARGIN_QUESTION_PATTERNS = [
    re.compile(r"\bQ(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\)(?:\s|$)"),
    re.compile(r"\b(\d+)\.(?:\s|$)"),
    re.compile(r"\((\d+)\)"),
]


def _normalize_ocr_text(text: str) -> str:
    """Normalize common OCR misreads of handwritten digits.

    Applies character substitutions for frequent tesseract confusions
    on handwritten text before question number pattern matching.

    Args:
        text: Raw OCR text to normalize.

    Returns:
        Text with common OCR confusions corrected in the first few characters.
    """
    replacements = {
        'I': '1', 'l': '1', 'i': '1',  # thin strokes -> 1
        'O': '0', 'o': '0',             # round -> 0
        'S': '5', 's': '5',             # similar shape -> 5
        '+': '7',                         # crossed 7 -> 7
    }
    # Only apply to the first few characters (question marker area)
    # to avoid corrupting answer text
    prefix_len = min(6, len(text))
    prefix = text[:prefix_len]
    rest = text[prefix_len:]

    normalized = ''.join(replacements.get(c, c) for c in prefix)
    return normalized + rest


def _match_question_number_margin(text: str) -> int | None:
    """Try to find a question number anywhere in text (for margin OCR).

    More flexible than _match_question_number: uses .search() instead of
    .match() so it tolerates OCR noise at the start (e.g. "| 12)"), and
    accepts end-of-string instead of requiring trailing whitespace
    (e.g. "6)" with no trailing space).

    Args:
        text: Text content to search within.

    Returns:
        Question number if found, None otherwise.
    """
    # Try original text first
    for pattern in _MARGIN_QUESTION_PATTERNS:
        match = pattern.search(text.strip())
        if match:
            q_num = int(match.group(1))
            if 1 <= q_num <= 99:
                # Reject if matched number is part of a decimal (e.g., "24.5")
                remaining = text.strip()[match.end():]
                if remaining and remaining[0].isdigit():
                    continue
                return q_num

    # Try normalized text (OCR error correction)
    normalized = _normalize_ocr_text(text.strip())
    if normalized != text.strip():
        for pattern in _MARGIN_QUESTION_PATTERNS:
            match = pattern.search(normalized)
            if match:
                q_num = int(match.group(1))
                if 1 <= q_num <= 99:
                    remaining = normalized[match.end():]
                    if remaining and remaining[0].isdigit():
                        continue
                    return q_num

    return None


def _match_question_number(text: str) -> int | None:
    """Try to match a question number from text.

    Args:
        text: Text content to match against.

    Returns:
        Question number if matched, None otherwise.
    """
    # Try original text first
    for pattern in _QUESTION_PATTERNS:
        match = pattern.match(text.strip())
        if match:
            q_num = int(match.group(1))
            if 1 <= q_num <= 100:
                # Reject if matched number is part of a decimal (e.g., "24.5")
                remaining = text.strip()[match.end():]
                if remaining and remaining[0].isdigit():
                    continue
                return q_num

    # Try normalized text (OCR error correction)
    normalized = _normalize_ocr_text(text.strip())
    if normalized != text.strip():
        for pattern in _QUESTION_PATTERNS:
            match = pattern.match(normalized)
            if match:
                q_num = int(match.group(1))
                if 1 <= q_num <= 100:
                    remaining = normalized[match.end():]
                    if remaining and remaining[0].isdigit():
                        continue
                    return q_num

    return None
