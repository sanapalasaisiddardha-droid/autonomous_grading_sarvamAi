"""Sarvam Vision API client for document intelligence."""

import json
import logging
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

# Regex patterns for question markers anchored to line starts
_QUESTION_PATTERNS = [
    re.compile(r"^Q(\d+)", re.MULTILINE | re.IGNORECASE),           # Q1, Q2, q1
    re.compile(r"^Question\s+(\d+)", re.MULTILINE | re.IGNORECASE),  # Question 1
    re.compile(r"^(\d+)\.\s", re.MULTILINE),                         # 1. 2.
    re.compile(r"^(\d+)\)\s", re.MULTILINE),                         # 1) 2)
    re.compile(r"^\((\d+)\)\s", re.MULTILINE),                       # (1) (2)
]


@dataclass
class SarvamDetectedQuestion:
    """A question marker detected by Sarvam Vision."""

    question_number: int
    raw_marker: str
    page_number: int
    context_text: str
    y_position: float = 0.0  # y1 coordinate of the block in Sarvam image space
    confidence: float = 0.7


@dataclass
class SarvamPageResult:
    """Result of analyzing a single page with Sarvam Vision."""

    page_number: int
    raw_response: str
    detected_questions: list[SarvamDetectedQuestion] = field(default_factory=list)
    success: bool = True
    error_message: str = ""
    image_width: int = 0   # Sarvam's rendered image width
    image_height: int = 0  # Sarvam's rendered image height


class SarvamClient:
    """Client for Sarvam Vision Document Intelligence API (SDK v2)."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize with API key.

        Args:
            api_key: Sarvam API key. Defaults to settings.SARVAM_API_KEY.
        """
        self.api_key = api_key or getattr(settings, "SARVAM_API_KEY", "")

    def analyze_all_pages(
        self, pdf_path: str, page_count: int
    ) -> list[SarvamPageResult]:
        """Analyze all pages of a PDF using Sarvam Document Intelligence SDK.

        Submits the entire PDF as a single job, waits for completion,
        then parses per-page metadata to detect question markers with
        their bounding box coordinates.

        Args:
            pdf_path: Path to the PDF file.
            page_count: Total number of pages (used for fallback).

        Returns:
            List of SarvamPageResult, one per page.
        """
        if not self.api_key:
            logger.warning("SARVAM_API_KEY not configured, skipping Sarvam analysis")
            return [
                SarvamPageResult(
                    page_number=p,
                    raw_response="",
                    success=False,
                    error_message="SARVAM_API_KEY not configured",
                )
                for p in range(1, page_count + 1)
            ]

        try:
            from sarvamai import SarvamAI

            client = SarvamAI(api_subscription_key=self.api_key)

            # Create a document intelligence job
            job = client.document_intelligence.create_job(
                language="en-IN",
                output_format="md",
            )
            logger.info("Sarvam job created: %s", job.job_id)

            # Upload the PDF
            job.upload_file(pdf_path)
            logger.info("Sarvam: PDF uploaded")

            # Start processing
            job.start()
            logger.info("Sarvam: job started")

            # Wait for completion (poll every 3s, timeout 120s)
            result = job.wait_until_complete(poll_interval=3.0, timeout=120.0)
            logger.info(
                "Sarvam: job %s → %s (pages: %d)",
                job.job_id,
                result.job_state,
                result.job_details[0].pages_processed if result.job_details else 0,
            )

            if result.job_state != "Completed":
                error_msg = result.error_message or f"Job state: {result.job_state}"
                logger.error("Sarvam job failed: %s", error_msg)
                return [
                    SarvamPageResult(
                        page_number=p,
                        raw_response="",
                        success=False,
                        error_message=error_msg,
                    )
                    for p in range(1, page_count + 1)
                ]

            # Download output (zip file)
            output_dir = tempfile.mkdtemp(prefix="sarvam_")
            output_path = os.path.join(output_dir, "output")
            job.download_output(output_path)

            # Extract zip
            zip_path = output_path + ".zip"
            os.rename(output_path, zip_path)
            extract_dir = os.path.join(output_dir, "extracted")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # Parse per-page metadata
            results = self._parse_metadata(extract_dir, page_count)

            # Clean up temp files
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)

            return results

        except Exception as exc:
            logger.exception("Sarvam analysis failed: %s", exc)
            return [
                SarvamPageResult(
                    page_number=p,
                    raw_response="",
                    success=False,
                    error_message=str(exc)[:200],
                )
                for p in range(1, page_count + 1)
            ]

    def _parse_metadata(
        self, extract_dir: str, page_count: int
    ) -> list[SarvamPageResult]:
        """Parse per-page metadata JSON files from Sarvam output.

        Each metadata file contains text blocks with coordinates.
        We scan block text for question markers.

        Args:
            extract_dir: Directory containing extracted Sarvam output.
            page_count: Expected number of pages.

        Returns:
            List of SarvamPageResult with detected questions.
        """
        results: list[SarvamPageResult] = []

        for page_num in range(1, page_count + 1):
            metadata_path = os.path.join(
                extract_dir, "metadata", f"page_{page_num:03d}.json"
            )

            if not os.path.exists(metadata_path):
                logger.warning("Sarvam metadata not found for page %d", page_num)
                results.append(
                    SarvamPageResult(
                        page_number=page_num,
                        raw_response="",
                        success=False,
                        error_message=f"Metadata file not found for page {page_num}",
                    )
                )
                continue

            with open(metadata_path, "r") as f:
                page_data = json.load(f)

            image_width = page_data.get("image_width", 0)
            image_height = page_data.get("image_height", 0)
            blocks = page_data.get("blocks", [])

            # Sort blocks by reading order
            blocks.sort(key=lambda b: b.get("reading_order", 0))

            detected: list[SarvamDetectedQuestion] = []
            seen_questions: set[int] = set()

            for block in blocks:
                text = block.get("text", "")
                coords = block.get("coordinates", {})
                block_confidence = block.get("confidence", 0.5)
                y1 = coords.get("y1", 0.0)
                y2 = coords.get("y2", y1)

                # Find ALL question markers in this block's text
                found = _find_all_question_numbers(text)
                for i, (q_num, raw_marker) in enumerate(found):
                    if q_num in seen_questions:
                        continue
                    seen_questions.add(q_num)
                    # Estimate y for subsequent questions within same block
                    if len(found) > 1 and i > 0:
                        block_height = y2 - y1
                        q_y = y1 + (block_height * i / len(found))
                    else:
                        q_y = y1
                    context = text[:80].replace("\n", " ").strip()
                    detected.append(
                        SarvamDetectedQuestion(
                            question_number=q_num,
                            raw_marker=raw_marker,
                            page_number=page_num,
                            context_text=context,
                            y_position=q_y,
                            confidence=block_confidence,
                        )
                    )

            detected.sort(key=lambda d: d.y_position)

            raw = json.dumps(page_data, indent=2)[:500]
            results.append(
                SarvamPageResult(
                    page_number=page_num,
                    raw_response=raw,
                    detected_questions=detected,
                    success=True,
                    image_width=image_width,
                    image_height=image_height,
                )
            )

            logger.info(
                "Sarvam page %d: found %d questions, image=%dx%d",
                page_num,
                len(detected),
                image_width,
                image_height,
            )

        return results


def _match_question_number(text: str) -> int | None:
    """Try to match a question number from the start of text.

    Args:
        text: Text content to match against.

    Returns:
        Question number if matched, None otherwise.
    """
    for pattern in _QUESTION_PATTERNS:
        match = pattern.match(text.strip())
        if match:
            q_num = int(match.group(1))
            if 1 <= q_num <= 100:
                return q_num
    return None


def _find_all_question_numbers(text: str) -> list[tuple[int, str]]:
    """Find all question numbers in a text block.

    Searches entire text (not just start) for question marker patterns.
    Returns unique question numbers in order of appearance.

    Args:
        text: Text content to search.

    Returns:
        List of (question_number, raw_marker) tuples, ordered by position.
    """
    found: list[tuple[int, int, str]] = []  # (position, q_num, raw_marker)
    seen: set[int] = set()

    for pattern in _QUESTION_PATTERNS:
        for match in pattern.finditer(text):
            q_num = int(match.group(1))
            if 1 <= q_num <= 100 and q_num not in seen:
                # Reject if matched number is part of a decimal (e.g., "24.5")
                remaining = text[match.end():]
                if remaining and remaining[0].isdigit():
                    continue
                seen.add(q_num)
                found.append((match.start(), q_num, match.group(0).strip()))

    # Sort by position in text
    found.sort(key=lambda x: x[0])
    return [(q_num, marker) for _, q_num, marker in found]
