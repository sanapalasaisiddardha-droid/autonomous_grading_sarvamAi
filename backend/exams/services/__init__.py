"""Public API for exam processing services."""

from .pdf_processor import (
    PageExtractionResult,
    TextBlock,
    extract_pages,
    get_page_image_dir,
)
from .sarvam_client import (
    SarvamClient,
    SarvamDetectedQuestion,
    SarvamPageResult,
)
from .segmenter import (
    CropRegion,
    DetectedMarker,
    SegmentationResult,
    calculate_crop_regions,
    crop_and_save_segments,
    detect_question_markers_ocr,
    detect_question_markers_pymupdf,
    fill_missing_with_equal_split,
    merge_detections,
    stitch_images_vertically,
)

__all__ = [
    # pdf_processor
    "TextBlock",
    "PageExtractionResult",
    "extract_pages",
    "get_page_image_dir",
    # sarvam_client
    "SarvamClient",
    "SarvamDetectedQuestion",
    "SarvamPageResult",
    # segmenter
    "DetectedMarker",
    "CropRegion",
    "SegmentationResult",
    "detect_question_markers_pymupdf",
    "detect_question_markers_ocr",
    "fill_missing_with_equal_split",
    "merge_detections",
    "calculate_crop_regions",
    "crop_and_save_segments",
    "stitch_images_vertically",
]
