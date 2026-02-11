# ExamLens — Build Prompt Plan

> **How to use this file with Claude Code:**
> Open Claude Code in the project root directory (where CLAUDE.md and this file live).
> Copy-paste each prompt below one at a time. Wait for Claude to finish and verify before moving to the next prompt.
> Each prompt builds on the previous one. Do NOT skip prompts.
> After each prompt, verify the output works before proceeding.

---

## PROMPT 1: Project Scaffolding & Docker Setup
**Status:** ⬜ Not Started

```
Read CLAUDE.md and prompt_plan.md to understand the full project.

Set up the project scaffolding:

1. Create the Django backend:
   - Initialize Django project named "config" inside a "backend/" directory
   - Create two Django apps: "exams" and "grading"
   - Set up requirements.txt with: django, djangorestframework, django-cors-headers, celery, redis, psycopg2-binary, Pillow, PyMuPDF, requests, python-dotenv, gunicorn, reportlab
   - Configure settings.py with: REST framework, CORS, Celery, PostgreSQL database (from env), media file handling, and installed apps
   - Set up config/celery.py with Redis broker
   - Create .env.example with all required environment variables

2. Create the React frontend:
   - Initialize with Vite + React template inside "frontend/" directory
   - Install: axios, react-router-dom, zustand, tailwindcss, @headlessui/react, lucide-react, react-dropzone
   - Configure Tailwind CSS
   - Configure Vite proxy to Django backend at localhost:8000
   - Set up basic App.jsx with React Router (5 routes: /, /processing/:id, /review/:id, /grading/:id, /report/:id)

3. Create docker-compose.yml with services:
   - db: PostgreSQL 16
   - redis: Redis Alpine
   - backend: Django (Dockerfile in backend/)
   - celery_worker: same image as backend, runs Celery
   - frontend: Node dev server (Dockerfile in frontend/)

4. Create a basic Layout.jsx component with navigation sidebar.

Verify: `docker compose build` should succeed. Both servers should start without errors.
```

---

## PROMPT 2: Database Models & Migrations
**Status:** ⬜ Not Started

```
Create all Django models exactly as specified below. Read CLAUDE.md for the full schema context.

In exams/models.py create:

1. Exam model:
   - title: CharField(max_length=255)
   - subject: CharField(max_length=100)
   - total_questions: IntegerField
   - created_at: DateTimeField(auto_now_add)
   - updated_at: DateTimeField(auto_now)
   - status: CharField with choices: setup, processing, review_segments, grading, completed (default: setup)
   - current_grading_question: IntegerField(default=1)
   - Add __str__ returning title

2. QuestionConfig model:
   - exam: ForeignKey(Exam, related_name='questions', CASCADE)
   - question_number: IntegerField
   - max_marks: DecimalField(max_digits=5, decimal_places=1)
   - topic: CharField(max_length=255, blank=True) — optional label
   - class Meta: unique_together = ['exam', 'question_number'], ordering = ['question_number']

3. AnswerSheet model:
   - exam: ForeignKey(Exam, related_name='sheets', CASCADE)
   - roll_number: CharField(max_length=50) — extracted from filename
   - original_pdf: FileField(upload_to='answer_sheets/')
   - anonymous_id: UUIDField(default=uuid4, unique=True, editable=False)
   - processing_status: CharField with choices: pending, processing, completed, failed, needs_review (default: pending)
   - total_pages: IntegerField(null=True, blank=True)
   - error_message: TextField(blank=True) — stores processing errors
   - created_at: DateTimeField(auto_now_add)
   - class Meta: unique_together = ['exam', 'roll_number']
   - Add property `anonymous_display` that returns first 8 chars of anonymous_id like "#anon-a7f2e9b1"

4. AnswerSegment model:
   - answer_sheet: ForeignKey(AnswerSheet, related_name='segments', CASCADE)
   - question: ForeignKey(QuestionConfig, related_name='segments', CASCADE)
   - image: ImageField(upload_to=dynamic_segment_path) — path: segments/{exam_id}/{question_number}/{anonymous_id}_{part}.jpg
   - page_number: IntegerField
   - part_number: IntegerField(default=1) — for multi-page answers
   - confidence_score: FloatField(default=0.0)
   - manually_adjusted: BooleanField(default=False)
   - y_start: IntegerField(null=True)
   - y_end: IntegerField(null=True)
   - class Meta: ordering = ['question__question_number', 'part_number']

In grading/models.py create:

5. Grade model:
   - answer_sheet: ForeignKey(AnswerSheet, related_name='grades', CASCADE)
   - question: ForeignKey(QuestionConfig, related_name='grades', CASCADE)
   - marks_awarded: DecimalField(max_digits=5, decimal_places=1, null=True)
   - remarks: TextField(blank=True) — optional teacher notes
   - graded_at: DateTimeField(auto_now)
   - class Meta: unique_together = ['answer_sheet', 'question']

Register all models in their respective admin.py files with sensible list_display, list_filter, and search_fields.

Run makemigrations and migrate. Verify all tables are created correctly.
```

---

## PROMPT 3: Sarvam Vision API Client & PDF Processing Service
**Status:** ⬜ Not Started

```
Create the backend service layer for PDF processing and Sarvam Vision integration.

1. Create backend/exams/services/sarvam_client.py:
   - Class: SarvamVisionClient
   - __init__: reads SARVAM_API_KEY from env, sets base_url = "https://api.sarvam.ai"
   - Method: detect_question_markers(image_path: str) -> list[dict]
     * Reads image file, converts to base64
     * Sends POST request to Sarvam Vision document intelligence endpoint
     * Headers: {"API-Subscription-Key": api_key, "Content-Type": "application/json"}
     * Request body should ask Sarvam to identify question numbers and their positions
     * Parse response to extract: [{"question_number": 1, "y_position": 120, "page": 1, "confidence": 0.95}, ...]
     * Handle API errors gracefully — return empty list on failure with logging
     * Include retry logic (3 retries with exponential backoff)
   
   IMPORTANT: Since Sarvam Vision's exact API format may change, structure this as an ADAPTER pattern.
   Create a method `_parse_sarvam_response(raw_response)` that can be easily updated.
   Also create a FALLBACK method `detect_question_markers_regex(image_path)` that uses
   basic OCR (pytesseract or Sarvam's general OCR endpoint) to find patterns like
   "Q1", "Q.1", "1.", "1)", "Question 1" using regex on extracted text.

2. Create backend/exams/services/pdf_processor.py:
   - Class: PDFProcessor
   - Method: pdf_to_images(pdf_path: str, output_dir: str) -> list[str]
     * Uses PyMuPDF (fitz) to convert each PDF page to a high-res JPEG image (300 DPI)
     * Saves images as page_001.jpg, page_002.jpg, etc. in output_dir
     * Returns list of image file paths
     * Handles corrupt PDFs gracefully
   - Method: parse_filename(filename: str) -> tuple[str, str]
     * Parses "2301_physics.pdf" → ("2301", "physics")
     * Validates format, raises ValueError if invalid

3. Create backend/exams/services/segmenter.py:
   - Class: AnswerSegmenter
   - __init__: takes sarvam_client, exam's question_count
   - Method: segment_answer_sheet(page_images: list[str], question_count: int) -> list[dict]
     * For each page image, calls sarvam_client.detect_question_markers()
     * Consolidates markers across all pages into a sorted list by (page, y_position)
     * Maps detected markers to expected question numbers (1 through question_count)
     * For each question, calculates crop region:
       - y_start = marker position + offset (skip question number text, ~50px)
       - y_end = next marker position OR page bottom
     * Handles multi-page answers: if Q[i] has no Q[i+1] on same page,
       crop to page bottom as part 1, then crop top of next page to Q[i+1] as part 2
     * Returns: [{"question_number": 1, "crops": [{"page": 1, "y_start": 150, "y_end": 780, "part": 1}], "confidence": 0.92}, ...]
   - Method: crop_image(image_path: str, y_start: int, y_end: int, output_path: str) -> str
     * Uses Pillow to crop the image region
     * Saves cropped image to output_path
     * Returns output_path
   - Method: calculate_confidence(detected_count: int, expected_count: int, marker_confidences: list) -> float
     * Returns overall confidence score (0-1)
     * Low confidence if detected != expected or if marker confidences are low

4. Create backend/exams/services/report_generator.py:
   - Class: ReportGenerator
   - Method: generate_csv(exam_id: int) -> str (file path)
     * Queries all grades for the exam
     * De-anonymizes: maps anonymous_id → roll_number
     * Columns: Roll Number, Q1, Q2, ..., QN, Total, Percentage
     * Sorted by roll number
   - Method: generate_report_data(exam_id: int) -> dict
     * Returns structured data for the frontend report page
     * Includes: student_results (list), class_stats (avg, median, highest, lowest, pass_rate)
     * Question-wise stats: per-question average, min, max

Verify: Import all services in Django shell without errors. Write a basic test that instantiates each service.
```

---

## PROMPT 4: Celery Tasks for Async PDF Processing
**Status:** ⬜ Not Started

```
Create Celery tasks that orchestrate the PDF processing pipeline.

Create backend/exams/tasks.py:

1. Task: process_exam_sheets(exam_id: int)
   - Triggered after teacher uploads all PDFs and clicks "Start Processing"
   - Sets Exam.status = "processing"
   - Queries all AnswerSheets with status="pending" for this exam
   - For each sheet, dispatches process_single_sheet.delay(sheet_id)
   - Uses a Celery chord/group so we know when ALL sheets are done
   - After all sheets finish, calls finalize_processing.delay(exam_id)

2. Task: process_single_sheet(sheet_id: int)
   - Sets AnswerSheet.processing_status = "processing"
   - Step 1: Convert PDF to page images using PDFProcessor
     * Save to media/pages/{exam_id}/{anonymous_id}/
     * Update AnswerSheet.total_pages
   - Step 2: Detect question markers using SarvamVisionClient
     * Call detect_question_markers() for each page image
     * If Sarvam API fails, try detect_question_markers_regex() as fallback
   - Step 3: Segment and crop using AnswerSegmenter
     * Crop answer regions for each question
     * Save cropped images to media/segments/{exam_id}/{question_number}/
     * Create AnswerSegment records in database
   - Step 4: Evaluate confidence
     * If confidence > 0.8 → set status = "completed"
     * If confidence 0.5-0.8 → set status = "needs_review"
     * If confidence < 0.5 or critical failure → set status = "failed"
   - Error handling: wrap in try/except, set status="failed" with error_message on any exception
   - Clean up temporary page images after segmentation (keep only cropped segments)

3. Task: finalize_processing(exam_id: int)
   - Count completed, needs_review, failed sheets
   - If any sheets need review → set Exam.status = "review_segments"
   - If all completed → set Exam.status = "grading"
   - If all failed → keep Exam.status = "processing" (with error info)

Also update the Exam model or add a helper method:
- Exam.get_processing_progress() → returns {"total": 100, "completed": 72, "needs_review": 6, "processing": 16, "failed": 6}

Verify: Start Celery worker, trigger process_exam_sheets for a test exam, confirm tasks execute.
```

---

## PROMPT 5: Backend API Endpoints (Exam Management & Upload)
**Status:** ⬜ Not Started

```
Create Django REST Framework serializers and views for exam management and PDF upload.

1. In exams/serializers.py create:
   - QuestionConfigSerializer: all fields
   - ExamCreateSerializer: title, subject, questions (nested writable QuestionConfigSerializer, many=True)
     * Override create() to create Exam + all QuestionConfig records in one transaction
   - ExamListSerializer: id, title, subject, total_questions, status, created_at
   - ExamDetailSerializer: all Exam fields + nested questions + processing_progress (from get_processing_progress)
   - AnswerSheetUploadSerializer: validates uploaded files
     * Validate filename format: must match pattern `{roll}_{subject}.pdf`
     * Validate file is PDF (check content type and magic bytes)
     * Validate no duplicate roll numbers in batch
   - ProcessingStatusSerializer: returns processing progress for polling

2. In exams/views.py create:
   - ExamViewSet (ModelViewSet):
     * list: returns all exams (ExamListSerializer)
     * create: creates exam + question configs (ExamCreateSerializer)
     * retrieve: returns exam detail with processing progress (ExamDetailSerializer)
     
   - upload_answer_sheets (action on ExamViewSet, POST):
     * Accepts multipart form with multiple PDF files
     * For each file: parse filename, create AnswerSheet record, save PDF to media
     * Validates all files before creating any records (atomic)
     * Returns count of uploaded sheets
     * Triggers process_exam_sheets.delay(exam_id) 
   
   - processing_status (action on ExamViewSet, GET):
     * Returns current processing progress (for frontend polling)
     * Include per-sheet status breakdown
   
   - flagged_sheets (action on ExamViewSet, GET):
     * Returns list of sheets with status "needs_review" or "failed"
     * Include anonymous_id (NOT roll_number), page count, error details

3. In exams/urls.py:
   - Register ExamViewSet with router
   - Wire up to config/urls.py under /api/ prefix

4. Configure CORS and media serving in settings.py for development.

Verify: Use curl or httpie to:
- POST /api/exams/ with question config → creates exam
- POST /api/exams/{id}/upload_answer_sheets/ with PDF files → creates sheets and starts processing
- GET /api/exams/{id}/ → returns exam with processing status
- GET /api/exams/{id}/processing_status/ → returns progress
```

---

## PROMPT 6: Backend API Endpoints (Grading & Reports)
**Status:** ⬜ Not Started

```
Create the grading and report API endpoints. ANONYMITY IS CRITICAL HERE.

1. In grading/serializers.py create:
   - AnswerImageSerializer:
     * Fields: anonymous_id (first 8 chars), answer_images (list of image URLs), question_number, part_count
     * NEVER include roll_number
   - GradeSubmitSerializer:
     * Fields: anonymous_id, question_number, marks_awarded, remarks (optional)
     * Validate: marks_awarded <= question's max_marks
     * Validate: question_number == exam's current_grading_question (prevent out-of-order grading)
   - GradingProgressSerializer:
     * Per-question: question_number, max_marks, total_students, graded_count, is_current, is_locked
   - ReportStudentSerializer:
     * Fields: roll_number, question_marks (dict), total_marks, percentage
     * This serializer is ONLY used after ALL questions are graded
   - ReportSerializer:
     * Fields: exam info, student_results (list of ReportStudentSerializer), class_stats

2. In grading/views.py create:
   - get_grading_queue (GET /api/exams/{id}/grading/q/{q_num}/):
     * Returns list of all students' answer images for question q_num
     * Each entry: {anonymous_id, answer_images: [url1, url2...], marks_awarded (null if not graded)}
     * ORDER IS RANDOMIZED (use a seeded shuffle based on exam_id + q_num for consistency within session)
     * Validate: q_num must be <= exam.current_grading_question
     * NEVER expose roll_number

   - get_next_ungraded (GET /api/exams/{id}/grading/q/{q_num}/next/):
     * Returns the next ungraded student's answer images for the current question
     * Skips already-graded students
     * Returns null/empty when all are graded

   - submit_grade (POST /api/exams/{id}/grading/):
     * Accepts: {anonymous_id, question_number, marks_awarded, remarks}
     * Validates: question_number == exam.current_grading_question
     * Creates or updates Grade record
     * Returns updated grading progress

   - grading_progress (GET /api/exams/{id}/grading/progress/):
     * Returns per-question grading progress
     * Includes: which question is current, how many graded per question

   - advance_question (POST /api/exams/{id}/grading/advance/):
     * Validates ALL students have been graded for current question
     * Increments exam.current_grading_question
     * If current_grading_question > total_questions → set exam.status = "completed"
     * Returns new current question number

   - exam_report (GET /api/exams/{id}/report/):
     * ONLY accessible when exam.status == "completed"
     * Returns full report data: per-student marks, totals, percentages, class stats
     * NOW includes roll_number (de-anonymized)

   - download_report_csv (GET /api/exams/{id}/report/download/csv/):
     * Returns CSV file download
     * Columns: Roll Number, Q1, Q2, ..., Total, Percentage

3. Register all URLs in grading/urls.py and include in config/urls.py.

Verify:
- GET /grading/q/1/ returns shuffled anonymous answer images (no roll numbers!)
- POST /grading/ with marks saves grade
- POST /grading/advance/ fails if not all students graded
- GET /report/ only works when exam status is "completed"
```

---

## PROMPT 7: Segment Review API (for flagged sheets)
**Status:** ⬜ Not Started

```
Create the API for reviewing and manually correcting answer sheet segmentation.

1. In exams/serializers.py add:
   - SegmentReviewSerializer:
     * Returns: anonymous_id, page_images (full page image URLs), current_segments (list of segments with y_start, y_end, question_number, confidence), total_pages
   - SegmentUpdateSerializer:
     * Accepts: list of {question_number, page_number, y_start, y_end} — teacher's corrected boundaries
     * Validates boundaries don't overlap and cover all questions

2. In exams/views.py add:
   - get_flagged_sheets (GET /api/exams/{id}/review/flagged/):
     * Returns all sheets with status "needs_review" or "failed"
     * Include anonymous_id, page_count, current segment boundaries, confidence scores
   
   - get_sheet_for_review (GET /api/exams/{id}/review/{anonymous_id}/):
     * Returns full page images + current detected boundaries for a specific sheet
     * Used by the boundary editor UI

   - update_segments (PUT /api/exams/{id}/review/{anonymous_id}/):
     * Accepts new boundary definitions from teacher
     * Re-crops answer images based on new boundaries
     * Sets AnswerSegment.manually_adjusted = True
     * Updates AnswerSheet.processing_status = "completed"
   
   - approve_all_segments (POST /api/exams/{id}/review/approve-all/):
     * Batch approves all "needs_review" sheets without changes
     * Sets all to "completed"
     * If exam has no more pending/needs_review sheets, advance exam status to "grading"
   
   - skip_to_grading (POST /api/exams/{id}/review/skip/):
     * Allows teacher to skip review and go directly to grading
     * Uses best-effort segmentation for unreviewed sheets
     * Sets exam.status = "grading"

Verify: API correctly returns page images and segment boundaries for flagged sheets.
```

---

## PROMPT 8: Frontend — Exam Setup Page
**Status:** ⬜ Not Started

```
Build the Exam Setup page — the first screen teachers see.

Create frontend/src/pages/ExamSetup.jsx:

1. Page layout:
   - Clean, modern form with TailwindCSS styling
   - Card-based layout with subtle shadows

2. Form sections:
   A. Exam Details:
      - Title input (required)
      - Subject input (required)
   
   B. Questions Configuration:
      - Dynamic table where teacher adds questions
      - Columns: # (auto), Topic (optional text), Max Marks (required number)
      - "Add Question" button adds a new row
      - "Remove" button on each row (except if only 1 question)
      - Auto-calculates and displays Total Marks at bottom
      - Start with 1 empty question row
   
   C. Upload Answer Sheets:
      - react-dropzone area: "Drag & drop PDF files here, or click to browse"
      - Shows file count and list of uploaded filenames
      - Validates: only .pdf files, filename must match pattern roll_subject
      - Shows validation errors inline (red text under invalid files)
      - Displays: "97 valid files, 3 invalid" summary
   
   D. Submit button: "Create Exam & Start Processing"
      - Disabled until: title filled, subject filled, at least 1 question with marks, at least 1 valid PDF
      - On click: POST exam config, then POST upload PDFs, then navigate to /processing/{exam_id}
      - Show loading spinner during upload

3. Create Zustand store (frontend/src/store/examStore.js):
   - State: currentExam, questions, uploadedFiles, processingStatus, gradingProgress
   - Actions: createExam, uploadSheets, fetchProcessingStatus, fetchGradingProgress

4. Create API client (frontend/src/api/client.js):
   - Axios instance with baseURL = "/api" (proxied by Vite)
   - Request interceptor for auth token (if needed later)
   - Response interceptor for error handling
   - Functions: createExam(data), uploadSheets(examId, files), getExamDetail(examId), etc.

Style it professionally — use a clean color scheme (slate/blue), proper spacing, readable fonts.
Verify: Create an exam with 3 questions, upload a few test PDFs, confirm redirect to processing page.
```

---

## PROMPT 9: Frontend — Processing Status Page
**Status:** ⬜ Not Started

```
Build the Processing Status page that shows real-time PDF processing progress.

Create frontend/src/pages/ProcessingStatus.jsx:

1. Header: Exam title + subject

2. Overall progress bar:
   - Large progress bar showing X/100 sheets processed
   - Animated fill with percentage label
   - Color-coded: blue for in-progress

3. Status breakdown cards (4 cards in a row):
   - ✅ Completed: count (green)
   - ⚠️ Needs Review: count (amber)
   - ⏳ Processing: count (blue, with spinner)
   - ❌ Failed: count (red)

4. Auto-polling:
   - Poll GET /api/exams/{id}/processing_status/ every 3 seconds
   - Update progress bar and counts in real-time
   - Stop polling when no sheets have status "processing" or "pending"

5. Action buttons (bottom):
   - "Review Flagged Sheets" → navigates to /review/{id}
     * Only visible when needs_review count > 0
   - "Start Grading →" → navigates to /grading/{id}
     * Only enabled when ALL sheets are either "completed" or "failed" (none "processing"/"pending")
     * If some sheets failed, show warning: "6 sheets failed processing. You can proceed without them or re-upload."
   - "Re-upload Failed Sheets" → opens file picker filtered to failed sheets

6. Optional: expandable section showing per-sheet status list
   - Show anonymous_id, status badge, page count
   - Sortable/filterable by status

Add a subtle pulsing animation on the progress bar while processing is active.
Verify: Page polls and updates progress. Buttons enable/disable correctly based on status.
```

---

## PROMPT 10: Frontend — Segment Review Page
**Status:** ⬜ Not Started

```
Build the Segment Review page where teachers correct auto-detected question boundaries.

Create frontend/src/pages/SegmentReview.jsx:

1. Left panel (70% width): Page Image Viewer
   - Display the full answer sheet page image at readable zoom
   - Overlay horizontal lines at detected question boundaries
   - Lines should be DRAGGABLE (teacher drags up/down to adjust boundary)
   - Each line labeled: "Q1 start", "Q2 start", etc.
   - Color-coded by confidence: green (high), yellow (medium), red (low)
   - Page navigation: Previous/Next page buttons with page indicator "Page 2 of 4"

2. Right panel (30% width): Controls
   - Sheet info: anonymous_id, total pages, confidence score
   - Question boundary list:
     * For each question: show page number, y_start, y_end
     * "Reset" button per question (revert to auto-detected)
   - "Add Missing Boundary" button (for when auto-detection missed a question)
   - Preview section: small thumbnails of cropped regions for each question

3. Bottom action bar:
   - "Save & Next Sheet →" — saves adjusted boundaries, re-crops, loads next flagged sheet
   - "Approve As-Is" — accepts auto-detection without changes
   - "Skip All Reviews & Start Grading" — skip remaining reviews
   - Counter: "Reviewing 3 of 6 flagged sheets"

4. Create a BoundaryEditor component (frontend/src/components/BoundaryEditor.jsx):
   - Takes: page image URL, boundaries array, onChange callback
   - Renders image with draggable horizontal boundary lines
   - Use mouse events for drag (onMouseDown on line, onMouseMove to track, onMouseUp to commit)
   - Constrain drag to image bounds
   - Show Y-coordinate tooltip while dragging

This is the most complex UI component. Focus on getting the drag interaction smooth.
For the image, use a canvas element or absolutely-positioned div with the image as background.

Verify: Can view flagged sheets, drag boundaries, save, and move to next sheet.
```

---

## PROMPT 11: Frontend — Grading Interface (Core Feature)
**Status:** ⬜ Not Started

```
Build the Grading Interface — this is the MOST IMPORTANT page. Take extra care with UX.

Create frontend/src/pages/GradingInterface.jsx:

1. Top bar:
   - Exam title + subject
   - Current question indicator: "Question 1 of 5 • Max Marks: 10"
   - Overall progress bar: "67/100 students graded for Q1"
   - Question tabs/pills: Q1 ● Q2 ○ Q3 ○ Q4 ○ Q5 ○
     * Filled dot = completed, empty = not started, current = highlighted
     * Clicking a completed question lets teacher review (read-only)
     * Clicking a future question shows "Complete Q{current} first"

2. Main content (split layout):
   Left (65%): Answer Image Viewer
   - Large display of the current student's answer image for the current question
   - If multi-part (answer spans pages): show all parts vertically with "Part 1 of 2" labels
   - Zoom controls: zoom in, zoom out, fit to width, actual size
   - Pan: click and drag to pan when zoomed in
   - Keyboard shortcuts: +/- for zoom, arrow keys for pan

   Right (35%): Grading Panel
   - Anonymous student ID: "#anon-7f2e" (subtle, non-prominent)
   - Marks input: large number input field with +/- steppers
     * Shows max marks: "[ 7.5 ] / 10"
     * Validate: 0 <= marks <= max_marks, allow 0.5 increments
   - Quick mark buttons: row of preset buttons [0] [2.5] [5] [7.5] [10]
     * Generate presets: 0, 25%, 50%, 75%, 100% of max_marks
   - Remarks: optional text area for teacher notes (collapsed by default)
   - Navigation: [← Previous Student] [Save & Next →]
     * "Save & Next" saves grade AND moves to next ungraded student
     * Keyboard shortcut: Enter to save & next
   - "Flag for Review" button — marks this particular sheet for later review

3. Bottom bar:
   - Student navigation: "Student 67 of 100" with a mini progress dots/bar
   - [Finish Q1 → Move to Q2] button
     * DISABLED until all 100 students graded
     * When clicked: calls advance_question API, then loads Q2 with fresh student list
     * Confirmation dialog: "You've graded all students for Q1. Move to Q2?"
   - When on last question and all graded: button becomes "Complete Exam → View Report"

4. Keyboard shortcuts (display a small shortcut hint overlay):
   - Enter: Save & Next
   - Left/Right arrows: Previous/Next student
   - 0-9: Quick mark (if single digit max marks)
   - Esc: Close remarks

5. State management:
   - Fetch grading queue for current question on mount
   - Track: current_student_index, grades (map of anonymous_id → marks)
   - Optimistic UI: show mark immediately, save in background
   - Auto-save when navigating away from a student

IMPORTANT UX considerations:
- The answer image should be as large as possible — this is what the teacher spends 90% of time looking at
- Mark input should be fast — minimize clicks needed
- Navigation should feel snappy — preload next student's image

Verify: Can load grading queue, view answer images, enter marks, navigate between students.
Submit all grades for Q1, advance to Q2. Grading Q2 shows different (Q2) answer images.
```

---

## PROMPT 12: Frontend — Report Dashboard
**Status:** ⬜ Not Started

```
Build the Report Dashboard that shows after all grading is complete.

Create frontend/src/pages/ReportDashboard.jsx:

1. Header section:
   - Exam title + subject
   - "Grading Complete ✓" badge
   - Date completed

2. Class Statistics cards (4 in a row):
   - Class Average: XX.X%
   - Highest Score: XX% (Roll: XXXX)
   - Lowest Score: XX% (Roll: XXXX)
   - Pass Rate: XX% (assuming 40% pass threshold, or make configurable)

3. Full results table:
   - Columns: Roll Number | Q1 (/10) | Q2 (/15) | Q3 (/20) | ... | Total (/50) | Percentage
   - Sortable by any column (click header to sort)
   - Searchable by roll number
   - Color-code percentage: green (>75%), yellow (40-75%), red (<40%)
   - Sticky header for scrolling through 100 students
   - Zebra striping for readability

4. Question-wise Analysis section (collapsible):
   - Bar chart showing average marks per question (use recharts BarChart)
   - For each question: average, highest, lowest, standard deviation
   - Identify "hardest question" (lowest average %) and "easiest question"

5. Distribution chart:
   - Histogram of score percentages (0-10%, 10-20%, ..., 90-100%) using recharts

6. Download buttons:
   - "Download CSV" — triggers CSV download from API
   - "Download PDF Report" — triggers PDF download (if implemented) or show "coming soon"
   - "Print Report" — window.print() with print-friendly CSS

7. Back/navigation:
   - "← Back to Exams" link
   - "Review Grading" — goes back to grading interface in read-only mode

Make the table responsive and handle 100 rows smoothly. Use virtual scrolling if needed.
Verify: Report shows correct data with proper calculations. CSV downloads correctly.
```

---

## PROMPT 13: Integration Testing & Error Handling
**Status:** ⬜ Not Started

```
Add comprehensive error handling and create integration tests for the full flow.

1. Backend error handling improvements:
   - Add custom exception handler in DRF (config/exceptions.py)
   - All API responses follow envelope: {"status": "success|error", "data": {...}, "message": "..."}
   - Handle: Sarvam API timeout (30s timeout, retry 3x), invalid PDF uploads, corrupt images
   - Add request logging middleware for debugging
   - Rate limiting on upload endpoint (max 100 files per request)

2. Frontend error handling:
   - Global error boundary component wrapping the app
   - Toast notifications for: upload success/failure, grade saved, processing errors
   - Loading skeletons for all pages while data fetches
   - Empty states: "No exams yet", "No flagged sheets", etc.
   - Retry button on failed API calls
   - Handle: network disconnection during grading (save locally, sync when reconnected)

3. Backend tests (backend/exams/tests.py and backend/grading/tests.py):
   - Test exam creation with nested questions
   - Test filename parsing: valid and invalid filenames
   - Test upload validation: duplicate roll numbers, non-PDF files, invalid names
   - Test grading flow: submit grade, try grading wrong question (should fail)
   - Test advance_question: fails if not all graded, succeeds when all graded
   - Test report: only accessible when exam completed
   - Test anonymity: grading APIs never return roll_number
   - Test processing status endpoint

4. Add a management command: backend/exams/management/commands/create_test_data.py
   - Creates a test exam with 5 questions
   - Generates 10 mock answer sheets with fake segmented images
   - Useful for frontend development without needing real PDFs or Sarvam API

Run all tests. Fix any failures.
Verify: `python manage.py test` passes all tests. Frontend handles errors gracefully.
```

---

## PROMPT 14: Final Polish & Production Readiness
**Status:** ⬜ Not Started

```
Final polish, production configurations, and documentation.

1. Add a comprehensive README.md to the project root:
   - Project description and screenshots (placeholder)
   - Quick start guide (Docker Compose)
   - Manual setup guide (without Docker)
   - Environment variables documentation
   - API documentation summary
   - How to get Sarvam Vision API key
   - Architecture diagram (ASCII)

2. Production settings:
   - backend/config/settings_prod.py (extends settings.py)
   - Whitenoise for static files
   - Secure cookie settings
   - CSRF configuration for API
   - Proper logging configuration

3. Frontend production build:
   - Vite build optimization
   - Ensure API base URL is configurable via env
   - Add favicon and meta tags
   - Loading screen while React initializes

4. Docker production configuration:
   - Multi-stage Dockerfile for frontend (build + nginx)
   - Gunicorn for Django in production
   - Nginx config for serving frontend + proxying API
   - Health check endpoints

5. Add a demo mode:
   - Management command: `python manage.py demo_mode`
   - Creates sample exam with pre-segmented mock answer sheets
   - Allows testing the full grading flow without Sarvam API or real PDFs
   - Useful for demos and development

6. Final code cleanup:
   - Remove all console.log statements from frontend
   - Remove all debug print statements from backend
   - Add proper Python type hints everywhere
   - Add JSDoc comments to key React components
   - Ensure all TODO comments are resolved or converted to GitHub issues

Verify: `docker compose up --build` starts everything. Can complete full flow:
Create exam → Upload PDFs → Processing → Review → Grading → Report
```

---

## NOTES FOR CLAUDE CODE

### Execution Order
Execute prompts 1-14 in strict order. Each depends on the previous.

### When Stuck on Sarvam Vision API
The exact Sarvam Vision API format may need discovery. If the endpoint format is unclear:
1. Check https://docs.sarvam.ai/ for the latest API reference
2. Check https://dashboard.sarvam.ai/vision for interactive testing
3. Use the fallback regex-based question detection as a working alternative
4. Structure the sarvam_client.py as an adapter so the API format can be easily swapped

### Testing Without Sarvam API
Use the `create_test_data` management command (Prompt 13) to generate mock data.
The segmenter should have a `--mock` mode that generates fake segments for development.

### Key Files to Get Right
These are the most critical files — spend extra time on them:
1. `backend/exams/services/segmenter.py` — core answer cropping logic
2. `frontend/src/pages/GradingInterface.jsx` — most-used UI, must be smooth
3. `backend/grading/views.py` — anonymity must be airtight
4. `backend/exams/tasks.py` — async pipeline must be robust

### If Context Gets Long
Use `/compact` in Claude Code to summarize the conversation.
Re-read CLAUDE.md after compacting to refresh project context.
