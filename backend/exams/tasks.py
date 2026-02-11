"""Celery tasks for PDF processing pipeline."""

import logging
import os

from celery import chord, shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(name="exams.process_exam")
def process_exam(exam_id: str) -> dict:
    """Coordinator task: fan out processing for all sheets in an exam.

    Sets exam status to "processing", then launches a Celery chord —
    one process_answer_sheet task per sheet, with finalize_exam_processing
    as the callback.

    Args:
        exam_id: UUID of the Exam to process.

    Returns:
        Status dict.
    """
    from .models import Exam

    try:
        exam = Exam.objects.get(pk=exam_id)
    except Exam.DoesNotExist:
        logger.error("Exam %s not found", exam_id)
        return {"status": "error", "message": f"Exam {exam_id} not found"}

    sheets = exam.answer_sheets.filter(status="uploaded")
    if not sheets.exists():
        return {"status": "error", "message": "No uploaded sheets to process"}

    exam.status = "processing"
    exam.save(update_fields=["status", "updated_at"])

    # Fan out: one task per sheet, finalize when all complete
    sheet_tasks = [
        process_answer_sheet.s(str(sheet.pk)) for sheet in sheets
    ]
    callback = finalize_exam_processing.s(exam_id=str(exam_id))
    chord(sheet_tasks)(callback)

    logger.info(
        "Started processing exam %s with %d sheets", exam_id, sheets.count()
    )
    return {"status": "success", "message": f"Processing {sheets.count()} sheets"}


@shared_task(
    name="exams.process_answer_sheet",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_answer_sheet(self, answer_sheet_id: str) -> dict:
    """Process a single answer sheet: extract pages, detect questions, crop segments.

    Pipeline:
    1. Set sheet status = "processing"
    2. Delete existing segments (retry safety)
    3. Extract page images with PyMuPDF
    4. Detect question markers from text
    5. Try Sarvam Vision (optional, skip on failure)
    6. Merge detections
    7. Calculate crop regions
    8. Crop and save segment images
    9. Create AnswerSegment records
    10. Update sheet status

    Args:
        answer_sheet_id: UUID of the AnswerSheet to process.

    Returns:
        Status dict with processing results.
    """
    from .models import AnswerSegment, AnswerSheet
    from .services.pdf_processor import extract_pages, get_page_image_dir
    from .services.sarvam_client import SarvamClient
    from .services.segmenter import (
        _verify_estimated_markers,
        calculate_crop_regions,
        crop_and_save_segments,
        detect_question_markers_ocr,
        detect_question_markers_pymupdf,
        fill_missing_with_equal_split,
        merge_detections,
    )

    try:
        sheet = AnswerSheet.objects.select_related("exam").get(pk=answer_sheet_id)
    except AnswerSheet.DoesNotExist:
        logger.error("AnswerSheet %s not found", answer_sheet_id)
        return {"status": "error", "sheet_id": answer_sheet_id}

    exam = sheet.exam

    try:
        # Step 1: Set status
        sheet.status = "processing"
        sheet.processing_error = ""
        sheet.save(update_fields=["status", "processing_error", "updated_at"])

        # Step 2: Delete existing segments (for retry safety)
        sheet.segments.all().delete()

        # Step 3: Extract page images
        pdf_path = sheet.pdf_file.path
        output_dir = get_page_image_dir(str(exam.pk), str(sheet.pk))
        pages = extract_pages(pdf_path, output_dir)

        sheet.page_count = len(pages)
        sheet.save(update_fields=["page_count", "updated_at"])

        logger.info(
            "Sheet %s: extracted %d pages", answer_sheet_id, len(pages)
        )

        # Step 4: Detect question markers with PyMuPDF
        pymupdf_markers = detect_question_markers_pymupdf(pages)
        logger.info(
            "Sheet %s: PyMuPDF found %d markers", answer_sheet_id, len(pymupdf_markers)
        )

        # Step 5: Try Sarvam Vision (optional)
        sarvam_results = None
        try:
            client = SarvamClient()
            if client.api_key:
                sarvam_results = client.analyze_all_pages(pdf_path, len(pages))
                successful = sum(1 for r in sarvam_results if r.success)
                logger.info(
                    "Sheet %s: Sarvam analyzed %d/%d pages",
                    answer_sheet_id,
                    successful,
                    len(pages),
                )
        except Exception as e:
            logger.warning(
                "Sheet %s: Sarvam Vision failed, continuing with PyMuPDF only: %s",
                answer_sheet_id,
                str(e),
            )

        # Step 5b: Try pytesseract OCR (optional, best for printed text)
        ocr_markers = None
        try:
            ocr_markers = detect_question_markers_ocr(pages, total_questions=exam.total_questions)
            if ocr_markers:
                logger.info(
                    "Sheet %s: OCR found %d markers",
                    answer_sheet_id,
                    len(ocr_markers),
                )
        except Exception as e:
            logger.warning(
                "Sheet %s: OCR detection failed, continuing without: %s",
                answer_sheet_id,
                str(e),
            )

        # Step 6: Merge detections from all sources
        merged_markers = merge_detections(
            pymupdf_markers, sarvam_results, pages, ocr_markers=ocr_markers, total_questions=exam.total_questions
        )
        logger.info(
            "Sheet %s: %d merged markers", answer_sheet_id, len(merged_markers)
        )

        # Step 6b: Fill missing questions with equal-split fallback
        merged_markers = fill_missing_with_equal_split(
            merged_markers, pages, exam.total_questions
        )
        logger.info(
            "Sheet %s: %d markers after equal-split fill",
            answer_sheet_id,
            len(merged_markers),
        )

        # Step 6c: Verify estimated markers with tight-crop re-OCR
        merged_markers = _verify_estimated_markers(merged_markers, pages, exam.total_questions)
        logger.info(
            "Sheet %s: %d markers after verification pass",
            answer_sheet_id,
            len(merged_markers),
        )

        # Step 7: Calculate crop regions
        segmentation = calculate_crop_regions(
            merged_markers, pages, exam.total_questions
        )
        logger.info(
            "Sheet %s: confidence=%.2f, status=%s, missing=%s",
            answer_sheet_id,
            segmentation.overall_confidence,
            segmentation.status,
            segmentation.missing_questions,
        )

        # Step 8: Crop and save segments
        segments_dir = os.path.join(
            settings.MEDIA_ROOT, "segments", str(exam.pk)
        )
        saved_segments = crop_and_save_segments(
            segmentation.crop_regions,
            pages,
            segments_dir,
            str(sheet.anonymous_id),
        )

        # Step 9: Create AnswerSegment records
        for seg_data in saved_segments:
            # Convert absolute path to relative media path
            rel_path = os.path.relpath(seg_data["image_path"], settings.MEDIA_ROOT)
            AnswerSegment.objects.create(
                answer_sheet=sheet,
                question_number=seg_data["question_number"],
                image=rel_path,
                page_number=seg_data["page_number"],
                confidence=seg_data["confidence"],
                boundary_data=seg_data["boundary_data"],
                needs_review=seg_data["needs_review"],
            )

        # Step 10: Update sheet status
        sheet.status = segmentation.status
        if segmentation.missing_questions:
            sheet.processing_error = (
                f"Missing questions: {segmentation.missing_questions}"
            )
        sheet.save(update_fields=["status", "processing_error", "updated_at"])

        logger.info("Sheet %s: processing complete → %s", answer_sheet_id, sheet.status)
        return {
            "status": "success",
            "sheet_id": answer_sheet_id,
            "sheet_status": sheet.status,
            "segments_created": len(saved_segments),
            "confidence": segmentation.overall_confidence,
        }

    except Exception as exc:
        logger.exception("Sheet %s: processing failed", answer_sheet_id)
        sheet.status = "failed"
        sheet.processing_error = str(exc)[:1000]
        sheet.save(update_fields=["status", "processing_error", "updated_at"])

        # Retry if attempts remain
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return {
            "status": "error",
            "sheet_id": answer_sheet_id,
            "error": str(exc)[:200],
        }


@shared_task(name="exams.finalize_exam_processing")
def finalize_exam_processing(results: list[dict], exam_id: str) -> dict:
    """Callback after all sheets are processed — update exam status.

    Sets exam status to:
    - "grading" if all sheets are "segmented"
    - "review" if any sheet is "needs_review" or "failed"

    Args:
        results: List of result dicts from process_answer_sheet tasks.
        exam_id: UUID of the Exam.

    Returns:
        Status dict with summary counts.
    """
    from .models import Exam

    try:
        exam = Exam.objects.get(pk=exam_id)
    except Exam.DoesNotExist:
        logger.error("Exam %s not found during finalization", exam_id)
        return {"status": "error", "message": f"Exam {exam_id} not found"}

    # Count sheet statuses
    status_counts = {}
    for sheet in exam.answer_sheets.all():
        status_counts[sheet.status] = status_counts.get(sheet.status, 0) + 1

    needs_review = status_counts.get("needs_review", 0)
    failed = status_counts.get("failed", 0)

    if needs_review > 0 or failed > 0:
        exam.status = "review"
    else:
        exam.status = "grading"

    exam.save(update_fields=["status", "updated_at"])

    logger.info(
        "Exam %s finalized → %s (counts: %s)", exam_id, exam.status, status_counts
    )
    return {
        "status": "success",
        "exam_status": exam.status,
        "sheet_counts": status_counts,
    }
