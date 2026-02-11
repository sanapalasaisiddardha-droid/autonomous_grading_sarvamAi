# Anonymous Answer Sheet Evaluation System — Full Project Plan

## 1. Project Summary

An exam evaluation platform where a teacher uploads 100 answer sheet PDFs (named `roll_subject.pdf`), the system uses **Sarvam Vision** to detect question boundaries and crop individual answer images, and the teacher grades **one question at a time across all students anonymously**. After grading all questions, a report is generated with roll number, per-question marks, total, and percentage.

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    REACT FRONTEND                           │
│                                                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ Exam     │  │ Grading      │  │ Report             │    │
│  │ Setup    │→ │ Interface    │→ │ Dashboard          │    │
│  │ Page     │  │ (Anonymous)  │  │ (Per-student view)  │    │
│  └──────────┘  └──────────────┘  └────────────────────┘    │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────────┐
│                    DJANGO BACKEND                           │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ Upload &     │  │ Grading      │  │ Report           │   │
│  │ Processing   │  │ Engine       │  │ Generator        │   │
│  │ Service      │  │              │  │                  │   │
│  └──────┬───────┘  └──────────────┘  └─────────────────┘   │
│         │                                                    │
│  ┌──────▼───────────────────────────────────────────────┐   │
│  │              PROCESSING PIPELINE                      │   │
│  │                                                       │   │
│  │  PDF → Pages → Sarvam Vision API → Question Regions  │   │
│  │        (images)   (OCR + Layout)    → Cropped Images  │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  PostgreSQL DB  │  Media Storage (cropped images)    │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. How Sarvam Vision Fits (Detailed)

### 3.1 The Core Problem
Given a semi-structured answer sheet PDF where students write answers under printed question numbers (Q1, Q2, etc.), we need to:
1. Detect where each question's answer **starts** and **ends** (across pages)
2. Crop those regions as images
3. Handle multi-page answers (Q3 starts on page 2, continues on page 3)

### 3.2 Sarvam Vision's Role

**Step 1 — PDF to Page Images**
Convert each PDF page to an image using `pdf2image` / `PyMuPDF` (this is pre-processing, not Sarvam).

**Step 2 — Send each page image to Sarvam Vision API**
Use the **Document Intelligence API** with a prompt like:

```
Identify all question numbers visible on this page.
For each question number found, return:
- question_number (e.g., 1, 2, 3)
- bounding_box (x, y, width, height) of the question number marker
- y_coordinate of where the answer content begins
Return as JSON.
```

Sarvam Vision's **semantic layout parser** will:
- Detect printed question markers ("1.", "Q1", "1)", etc.)
- Understand the reading order (important for multi-column or messy layouts)
- Handle mixed English + Indic script headers

**Step 3 — Intelligent Cropping**
Using the detected question number positions + teacher's pre-configured question count:

```python
# Pseudo-logic
for each page_image:
    question_markers = sarvam_vision_detect(page_image)
    # markers = [{"q_num": 1, "y_start": 120}, {"q_num": 2, "y_start": 780}]

    for i, marker in enumerate(question_markers):
        y_start = marker["y_start"]
        y_end = next_marker["y_start"] if next_marker else page_height
        cropped = page_image.crop(0, y_start, page_width, y_end)
        save(cropped, student_id, question_number)
```

**Step 4 — Multi-page Answer Stitching**
If Q3 starts on page 2 but no Q4 marker is found until page 3:
- Crop from Q3's start to end of page 2
- Crop from top of page 3 to Q4's marker on page 3
- Link both images as "Q3 answer parts" for that student

### 3.3 Why Sarvam Vision Over Alternatives?

| Factor | Sarvam Vision | Google Vision | Tesseract |
|--------|--------------|---------------|-----------|
| Indic language OCR | ✅ Best-in-class (22 languages) | ⚠️ Decent | ❌ Poor |
| Layout parsing | ✅ Semantic + reading order | ⚠️ Basic | ⚠️ Basic |
| Cost (Feb 2026) | ✅ FREE this month | 💰 Paid | ✅ Free |
| Mixed script handling | ✅ Native | ⚠️ Needs hints | ❌ Weak |
| Document intelligence | ✅ Built for this | ⚠️ General purpose | ❌ OCR only |

### 3.4 Sarvam Vision API Usage

```python
import requests
import base64

SARVAM_API_KEY = "your_api_key"
SARVAM_BASE_URL = "https://api.sarvam.ai"

def detect_question_markers(page_image_path: str) -> list:
    """
    Send a page image to Sarvam Vision and get question marker positions.
    """
    with open(page_image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    # Use Sarvam Vision Document Intelligence endpoint
    response = requests.post(
        f"{SARVAM_BASE_URL}/v1/vision/document-intelligence",
        headers={
            "Authorization": f"Bearer {SARVAM_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "image": image_b64,
            "task": "layout_analysis",  # or appropriate task name
            "prompt": (
                "Identify all question numbers on this answer sheet page. "
                "For each, return the question number and its bounding box "
                "coordinates as JSON array."
            )
        }
    )
    return response.json()
```

> **Note:** Check Sarvam's latest API docs at `docs.sarvam.ai` for exact endpoint names and parameters — they may have updated since launch.

---

## 4. Data Models (Django)

```python
# models.py

class Exam(models.Model):
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=100)
    total_questions = models.IntegerField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(choices=[
        ('setup', 'Setup'),
        ('processing', 'Processing'),        # PDFs being analyzed
        ('review_segments', 'Review Segments'), # Teacher reviews auto-segmentation
        ('grading', 'Grading'),
        ('completed', 'Completed')
    ], default='setup', max_length=20)
    current_grading_question = models.IntegerField(default=1)  # locks progression


class QuestionConfig(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    question_number = models.IntegerField()
    max_marks = models.DecimalField(max_digits=5, decimal_places=1)


class AnswerSheet(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='sheets')
    roll_number = models.CharField(max_length=50)  # extracted from filename
    original_pdf = models.FileField(upload_to='answer_sheets/')
    anonymous_id = models.UUIDField(default=uuid.uuid4, unique=True)  # for anonymity
    processing_status = models.CharField(choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('needs_review', 'Needs Review')  # auto-segmentation uncertain
    ], default='pending', max_length=20)
    total_pages = models.IntegerField(null=True)


class AnswerSegment(models.Model):
    """One cropped image = one question's answer from one student"""
    answer_sheet = models.ForeignKey(AnswerSheet, on_delete=models.CASCADE, related_name='segments')
    question = models.ForeignKey(QuestionConfig, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='segments/')       # cropped answer image
    page_number = models.IntegerField()                    # source page
    part_number = models.IntegerField(default=1)           # for multi-page answers (part 1, 2...)
    confidence_score = models.FloatField(default=0.0)      # Sarvam's confidence
    manually_adjusted = models.BooleanField(default=False)  # teacher corrected boundary
    # Bounding box for audit trail
    y_start = models.IntegerField(null=True)
    y_end = models.IntegerField(null=True)


class Grade(models.Model):
    answer_sheet = models.ForeignKey(AnswerSheet, on_delete=models.CASCADE, related_name='grades')
    question = models.ForeignKey(QuestionConfig, on_delete=models.CASCADE)
    marks_awarded = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    graded_at = models.DateTimeField(auto_now=True)
    # anonymous_id is accessed via answer_sheet.anonymous_id during grading
```

---

## 5. Processing Pipeline (Backend)

### Phase 1: Upload & Parse
```
Teacher uploads 100 PDFs
    │
    ▼
Django receives files → Celery task queued per PDF
    │
    ▼
For each PDF (e.g., "2301_physics.pdf"):
    ├── Extract roll_number = "2301", subject = "physics"
    ├── Create AnswerSheet record (anonymous_id auto-generated)
    ├── Convert PDF pages to images (PyMuPDF / pdf2image)
    └── Store page images temporarily
```

### Phase 2: Question Detection (Sarvam Vision)
```
For each page image:
    │
    ▼
Send to Sarvam Vision Document Intelligence API
    │
    ▼
Receive: question marker positions + bounding boxes
    │
    ▼
Map markers to teacher's pre-configured question list
    │
    ▼
Validate: Did we find all N questions across all pages?
    ├── YES → Auto-crop answer regions
    └── NO  → Flag as "needs_review"
```

### Phase 3: Cropping
```
For each student's answer sheet:
    │
    ▼
Sort detected markers by (page_number, y_coordinate)
    │
    ▼
For each question Q[i]:
    ├── Start: Q[i] marker position + offset (skip the question text)
    ├── End: Q[i+1] marker position OR end of page
    ├── If Q[i] ends at page bottom and Q[i+1] is on next page:
    │       → Crop remainder of current page as Part 1
    │       → Crop top of next page to Q[i+1] marker as Part 2
    └── Save cropped image(s) as AnswerSegment records
```

### Phase 4: Confidence & Review
```
For each AnswerSheet:
    │
    ├── High confidence (all questions found clearly) → Mark "completed"
    ├── Medium confidence (some markers uncertain)    → Mark "needs_review"
    └── Failed (can't parse)                          → Mark "failed"
    
Teacher reviews flagged sheets in a "Segmentation Review" UI
    → Can manually drag boundaries to adjust crops
    → System re-crops based on teacher's adjustments
```

---

## 6. Frontend Pages & Flow

### Page 1: Exam Setup
```
┌─────────────────────────────────────────┐
│  CREATE NEW EXAM                        │
│                                         │
│  Exam Title: [___________________]      │
│  Subject:    [___________________]      │
│                                         │
│  QUESTIONS                              │
│  ┌─────┬────────────┬───────────┐       │
│  │ Q#  │ Topic      │ Max Marks │       │
│  ├─────┼────────────┼───────────┤       │
│  │  1  │ [optional] │ [  10  ]  │       │
│  │  2  │ [optional] │ [  15  ]  │       │
│  │  3  │ [optional] │ [  20  ]  │       │
│  │  +  │  Add Question          │       │
│  └─────┴────────────┴───────────┘       │
│                                         │
│  Total Marks: 45                        │
│                                         │
│  [ Upload Answer Sheets (100 PDFs) ]    │
│  ─────────────────────────────          │
│  Drag & drop or browse                  │
│  Files: 2301_physics.pdf, 2302_ph...    │
│                                         │
│         [ Start Processing → ]          │
└─────────────────────────────────────────┘
```

### Page 2: Processing Status
```
┌─────────────────────────────────────────┐
│  PROCESSING ANSWER SHEETS               │
│                                         │
│  ████████████████████░░░░  78/100       │
│                                         │
│  ✅ Completed: 72                       │
│  ⚠️  Needs Review: 6                    │
│  ⏳ Processing: 16                      │
│  ❌ Failed: 6                           │
│                                         │
│  [ Review Flagged Sheets ]              │
│  [ Start Grading → ] (enabled when all  │
│                        sheets processed) │
└─────────────────────────────────────────┘
```

### Page 3: Segmentation Review (for flagged sheets)
```
┌─────────────────────────────────────────┐
│  REVIEW SEGMENTATION — Sheet #anon-a3f  │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │                                  │   │
│  │  [Full page image with draggable │   │
│  │   horizontal lines showing       │   │
│  │   question boundaries]           │   │
│  │                                  │   │
│  │  ── Q1 starts ─── (draggable)    │   │
│  │                                  │   │
│  │  ── Q2 starts ─── (draggable)    │   │
│  │                                  │   │
│  └──────────────────────────────────┘   │
│                                         │
│  Page: [< 1 of 4 >]                    │
│                                         │
│  [ Save & Next Sheet → ]               │
└─────────────────────────────────────────┘
```

### Page 4: Grading Interface (Core Screen)
```
┌─────────────────────────────────────────────────────────┐
│  GRADING — Physics Exam                                 │
│  Question 1 of 5  │  Max Marks: 10                      │
│  Progress: ████████░░░░  67/100 students graded         │
│                                                         │
│  ┌────────────────────────────────┐  ┌───────────────┐  │
│  │                                │  │ MARKS         │  │
│  │  [Cropped answer image for     │  │               │  │
│  │   current anonymous student]   │  │ [ 7.5 ] / 10  │  │
│  │                                │  │               │  │
│  │  Part 1 of 2 (multi-page)     │  │ ┌───────────┐ │  │
│  │  [Part 2 image below]         │  │ │ Quick:    │ │  │
│  │                                │  │ │ [0][5][10]│ │  │
│  │                                │  │ └───────────┘ │  │
│  │                                │  │               │  │
│  └────────────────────────────────┘  │ [← Prev]     │  │
│                                      │ [Save & Next→]│  │
│  Student: #anon-7f2e (anonymous)     │               │  │
│                                      │ [Flag Issue]  │  │
│                                      └───────────────┘  │
│                                                         │
│  ⚠️ You must grade all 100 students for Q1 before       │
│     moving to Q2.                                       │
│                                                         │
│  [ ← Back to Q1 ] [ Finish Q1 & Move to Q2 → ]        │
│  (disabled until all 100 graded)                        │
└─────────────────────────────────────────────────────────┘
```

### Page 5: Report Dashboard
```
┌────────────────────────────────────────────────────────┐
│  EXAM REPORT — Physics Exam                            │
│                                                        │
│  Class Average: 67.3%  │  Highest: 92%  │  Lowest: 23%│
│                                                        │
│  ┌──────┬─────┬─────┬─────┬─────┬───────┬─────────┐   │
│  │ Roll │ Q1  │ Q2  │ Q3  │ Q4  │ Total │ Percent │   │
│  │      │ /10 │ /15 │ /20 │ /5  │ /50   │         │   │
│  ├──────┼─────┼─────┼─────┼─────┼───────┼─────────┤   │
│  │ 2301 │ 8   │ 12  │ 15  │ 4   │ 39    │ 78.0%   │   │
│  │ 2302 │ 6   │ 10  │ 18  │ 3   │ 37    │ 74.0%   │   │
│  │ ...  │     │     │     │     │       │         │   │
│  └──────┴─────┴─────┴─────┴─────┴───────┴─────────┘   │
│                                                        │
│  [ Download CSV ]  [ Download PDF Report ]             │
│  [ Question-wise Analysis ]                            │
└────────────────────────────────────────────────────────┘
```

---

## 7. API Endpoints (Django REST Framework)

```
# Exam Management
POST   /api/exams/                          → Create exam + question config
GET    /api/exams/{id}/                     → Get exam details
POST   /api/exams/{id}/upload/              → Upload answer sheet PDFs (bulk)
GET    /api/exams/{id}/processing-status/   → Poll processing progress

# Segmentation Review
GET    /api/exams/{id}/flagged-sheets/      → List sheets needing review
GET    /api/sheets/{anon_id}/segments/      → Get segments for a sheet
PUT    /api/sheets/{anon_id}/segments/      → Update segment boundaries (re-crop)

# Grading
GET    /api/exams/{id}/grading/q/{q_num}/           → Get all anonymous answer images for Q[n]
GET    /api/exams/{id}/grading/q/{q_num}/next/      → Get next ungraded student for Q[n]
POST   /api/exams/{id}/grading/                     → Submit grade {anon_id, q_num, marks}
GET    /api/exams/{id}/grading/progress/             → Grading progress per question
POST   /api/exams/{id}/grading/advance-question/     → Lock Q[n], unlock Q[n+1]

# Reports
GET    /api/exams/{id}/report/              → Full report (roll, marks, %, etc.)
GET    /api/exams/{id}/report/download/csv/ → CSV download
GET    /api/exams/{id}/report/download/pdf/ → PDF download
GET    /api/exams/{id}/report/analytics/    → Question-wise stats
```

---

## 8. Anonymity Implementation

This is critical to the system's integrity:

```
UPLOAD TIME:
  filename "2301_physics.pdf"
       │
       ▼
  roll_number = "2301" → stored in AnswerSheet.roll_number
  anonymous_id = UUID  → "a7f2e9b1-..." (auto-generated)

DURING GRADING:
  Teacher sees ONLY: anonymous_id (shown as short hash like "#anon-7f2e")
  Teacher NEVER sees: roll_number, filename, or any identifying info
  
  API response for grading:
  {
    "anonymous_id": "a7f2e...",
    "question_number": 1,
    "answer_images": ["segment_001.jpg", "segment_002.jpg"],
    "marks_awarded": null
  }
  // ❌ roll_number is NEVER in grading API responses

AFTER ALL QUESTIONS GRADED:
  System internally maps anonymous_id → roll_number
  Report reveals: roll_number + all marks
```

**Shuffle order:** When serving answers for grading, randomize the student order per question so the teacher can't guess identity by position.

---

## 9. Tech Stack & Dependencies

### Backend (Django)
```
django==5.x
djangorestframework
celery + redis              # async PDF processing
Pillow                       # image manipulation
PyMuPDF (fitz) or pdf2image  # PDF → page images
requests                     # Sarvam Vision API calls
psycopg2                     # PostgreSQL
django-storages              # S3/media storage (optional)
reportlab or weasyprint       # PDF report generation
```

### Frontend (React)
```
react + react-router
axios                        # API calls
zustand or redux             # state management
react-image-crop             # for segmentation review UI (boundary adjustment)
recharts                     # analytics charts in report
react-dropzone               # file upload
tailwindcss                  # styling
```

---

## 10. Development Phases

### Phase 1 — Foundation (Week 1-2)
- [ ] Django project setup with models, migrations
- [ ] React project setup with routing
- [ ] Exam creation + question config UI & API
- [ ] PDF upload with filename parsing (roll_subject extraction)
- [ ] Basic auth (teacher login)

### Phase 2 — Sarvam Vision Integration (Week 2-3)
- [ ] PDF → page image conversion pipeline
- [ ] Sarvam Vision API integration for question marker detection
- [ ] Cropping logic (single-page + multi-page stitching)
- [ ] Confidence scoring & flagging uncertain segmentations
- [ ] Celery task queue for batch processing 100 PDFs
- [ ] Processing status page with real-time progress

### Phase 3 — Segmentation Review (Week 3-4)
- [ ] Review UI with draggable boundaries on page images
- [ ] Re-cropping API when teacher adjusts boundaries
- [ ] Batch approve for high-confidence segmentations

### Phase 4 — Grading Interface (Week 4-5)
- [ ] Anonymous grading API (serves images by anonymous_id only)
- [ ] Question-wise batching with progression lock
- [ ] Grading UI with image viewer + mark input
- [ ] Multi-part image display for multi-page answers
- [ ] Quick mark buttons + keyboard shortcuts
- [ ] Progress tracking per question

### Phase 5 — Reports (Week 5-6)
- [ ] De-anonymization after all grading complete
- [ ] Report generation (table with roll, per-Q marks, total, %)
- [ ] CSV + PDF download
- [ ] Question-wise analytics (average, distribution, hardest question)
- [ ] Class statistics (mean, median, pass %)

### Phase 6 — Polish & Scale (Week 6-7)
- [ ] Error handling for failed PDFs (re-upload, manual entry)
- [ ] Optimistic UI updates during grading
- [ ] Image zoom/pan in grading view
- [ ] Mobile-responsive grading interface
- [ ] Rate limiting for Sarvam API calls
- [ ] Testing with real answer sheets

---

## 11. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sarvam Vision can't detect question markers in messy handwriting | High | Teacher pre-configures question count; fallback to manual boundary marking |
| Multi-page answers incorrectly stitched | Medium | Show teacher all parts with "merge" / "split" controls in review UI |
| Sarvam API rate limits on 100 PDFs × N pages | Medium | Queue with Celery, process with delays; Sarvam offers ₹1000 free credits |
| Students don't write question numbers clearly | High | Use "expected question count" from config + page position heuristics |
| Some PDFs are scanned at poor quality | Medium | Pre-process with contrast enhancement before sending to Sarvam |
| Sarvam free tier ends after February 2026 | Low | Budget for paid tier or fallback to open-source (Surya OCR) |

---

## 12. Sarvam Vision — Getting Started Right Now

1. **Sign up** at https://dashboard.sarvam.ai/
2. **Get API key** from the dashboard
3. **Free until end of Feb 2026** — Document Intelligence APIs are completely free this month
4. **API docs** at https://docs.sarvam.ai/
5. **Test with one PDF first** — upload a sample answer sheet, check the layout detection quality
6. **Join Discord** for developer support from the Sarvam team

---

## 13. Folder Structure

```
project/
├── backend/
│   ├── config/                    # Django settings, URLs, ASGI/WSGI
│   ├── exams/
│   │   ├── models.py              # Exam, QuestionConfig, AnswerSheet, etc.
│   │   ├── serializers.py
│   │   ├── views.py               # API views
│   │   ├── urls.py
│   │   ├── tasks.py               # Celery tasks (PDF processing)
│   │   └── services/
│   │       ├── sarvam_vision.py   # Sarvam API wrapper
│   │       ├── pdf_processor.py   # PDF → images
│   │       ├── segmenter.py       # Question boundary detection + cropping
│   │       └── report_generator.py
│   ├── grading/
│   │   ├── models.py              # Grade model
│   │   ├── views.py               # Anonymous grading APIs
│   │   └── serializers.py
│   └── manage.py
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ExamSetup.jsx
│   │   │   ├── ProcessingStatus.jsx
│   │   │   ├── SegmentReview.jsx
│   │   │   ├── GradingInterface.jsx
│   │   │   └── ReportDashboard.jsx
│   │   ├── components/
│   │   │   ├── AnswerImageViewer.jsx
│   │   │   ├── BoundaryEditor.jsx
│   │   │   ├── MarkInput.jsx
│   │   │   └── ProgressBar.jsx
│   │   ├── api/
│   │   │   └── client.js          # Axios instance + API functions
│   │   └── store/
│   │       └── examStore.js       # Zustand state
│   └── package.json
│
└── docker-compose.yml             # Django + Postgres + Redis + Celery
```
