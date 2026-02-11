# ExamLens — Application Pipeline

> A complete walkthrough of how the Anonymous Answer Sheet Evaluation System works, from start to finish.

---

## Overview

ExamLens allows teachers to grade exam answer sheets **anonymously** — meaning the teacher never knows whose paper they are grading until the very end. The system uses AI (Sarvam Vision) to automatically detect where each question's answer begins and ends on the page, crops those regions, and presents them one question at a time for grading.

---

## End-to-End Flow

```
 TEACHER                          SYSTEM                           AI (Sarvam Vision)
────────                         ────────                         ──────────────────
   │                                │                                    │
   │  1. Create Exam                │                                    │
   │  (title, subject, questions)   │                                    │
   │ ──────────────────────────────>│                                    │
   │                                │                                    │
   │  2. Upload PDFs                │                                    │
   │  (100 answer sheets)           │                                    │
   │ ──────────────────────────────>│                                    │
   │                                │  3. Convert PDF pages to images    │
   │                                │ ──────────────────────────────────>│
   │                                │                                    │
   │                                │  4. Detect question boundaries     │
   │                                │ <──────────────────────────────────│
   │                                │                                    │
   │                                │  5. Crop answer regions            │
   │                                │  (one image per question per       │
   │                                │   student)                         │
   │                                │                                    │
   │  6. Review flagged sheets      │                                    │
   │  (fix incorrect boundaries)    │                                    │
   │ ──────────────────────────────>│                                    │
   │                                │                                    │
   │  7. Grade Q1 for ALL students  │                                    │
   │  (anonymous, shuffled order)   │                                    │
   │ ──────────────────────────────>│                                    │
   │                                │                                    │
   │  8. Grade Q2, Q3, ... QN      │                                    │
   │ ──────────────────────────────>│                                    │
   │                                │                                    │
   │  9. View Report                │                                    │
   │  (roll numbers revealed)       │                                    │
   │ <──────────────────────────────│                                    │
```

---

## Stage 1 — Exam Setup

**Who:** Teacher
**Where:** Exam Setup Page
**What happens:**

1. Teacher enters the **exam title** and **subject** (e.g., "Mid-Term — Physics")
2. Teacher defines the **question paper structure**:
   - How many questions (e.g., 5)
   - Max marks per question (e.g., Q1: 10, Q2: 15, Q3: 20, Q4: 5, Q5: 10)
3. Teacher **uploads answer sheet PDFs** via drag-and-drop
   - Each file must be named `rollnumber_subject.pdf` (e.g., `2301_physics.pdf`)
   - The system extracts the roll number from the filename
   - Invalid filenames are flagged immediately
4. Teacher clicks **"Create Exam & Start Processing"**

**Result:** Exam is created in the database. PDFs are stored. Background processing begins.

---

## Stage 2 — PDF Processing (Automatic)

**Who:** System (Celery background workers)
**Where:** Server-side, runs asynchronously
**What happens:**

For each of the 100 uploaded PDFs, the system runs three steps:

### Step 2a — PDF to Images
- Each PDF page is converted to a high-resolution JPEG image (300 DPI) using PyMuPDF
- A 4-page answer sheet produces 4 separate page images
- Images are saved to `media/pages/{exam_id}/{anonymous_id}/`

### Step 2b — Question Boundary Detection (Sarvam Vision AI)
- Each page image is sent to the **Sarvam Vision Document Intelligence API**
- The AI identifies question markers on the page (e.g., "Q1", "1.", "Question 2")
- For each marker, it returns the **position (coordinates)** on the page
- The system maps detected markers to the teacher's configured question list

### Step 2c — Answer Cropping
- Using the detected marker positions, the system **crops each question's answer region**:
  - Q1's answer = from Q1 marker to Q2 marker
  - Q2's answer = from Q2 marker to Q3 marker (or end of page)
- **Multi-page answers** are handled: if Q3 starts on page 2 but Q4 isn't until page 3, the system crops the remainder of page 2 and the top of page 3, saving them as "Part 1" and "Part 2"
- Each cropped image is saved as an **AnswerSegment** in the database

### Confidence Scoring
Each sheet gets a confidence score based on how well the AI detected the questions:
- **High confidence (>80%):** All questions found clearly → marked "completed"
- **Medium confidence (50-80%):** Some markers uncertain → marked "needs review"
- **Low confidence (<50%):** Detection failed → marked "failed"

**Result:** The teacher sees a real-time progress dashboard showing how many sheets are processed, flagged, or failed.

---

## Stage 3 — Segment Review (If Needed)

**Who:** Teacher
**Where:** Segment Review Page
**What happens:**

- Only sheets flagged as "needs review" appear here
- Teacher sees the **full page image** with **draggable boundary lines** overlaid
- Each line represents where the system thinks one question ends and the next begins
- Teacher can **drag lines up or down** to correct mistakes
- After adjusting, the system **re-crops** the answer regions based on the new boundaries
- Teacher can also "Approve As-Is" if the auto-detection looks correct
- A "Skip All & Start Grading" option is available to use best-effort segmentation

**Result:** All answer sheets are now segmented into individual question-answer images, ready for grading.

---

## Stage 4 — Anonymous Grading (Core Feature)

**Who:** Teacher
**Where:** Grading Interface
**What happens:**

This is the heart of the system. The teacher grades **one question at a time, across all students**, without knowing whose paper they are looking at.

### How Anonymity Works

```
  Original file: "2301_physics.pdf"
         │
         ▼
  ┌─────────────────────────────────┐
  │  roll_number = "2301"  (hidden) │
  │  anonymous_id = "a7f2e9b1-..." │
  │  display = "#anon-7f2e"        │
  └─────────────────────────────────┘
         │
         ▼
  Teacher sees ONLY: "#anon-7f2e"
  Teacher NEVER sees: "2301" or the filename
  Student order is SHUFFLED for each question
```

### Grading Flow

1. **Q1 Grading Round:**
   - System shows all 100 students' Q1 answer images, one at a time, in **random order**
   - Teacher views the cropped answer image (zooming/panning available)
   - Teacher enters marks (e.g., 7.5 / 10) using input field or quick-mark buttons
   - Teacher clicks "Save & Next" (or presses Enter) to move to the next student
   - Progress bar: "67/100 students graded for Q1"

2. **Lock Mechanism:**
   - Teacher **cannot move to Q2 until all 100 students are graded for Q1**
   - The "Move to Q2" button stays disabled until 100/100 is reached
   - Backend enforces this — rejects grades for Q2 if any Q1 grade is missing

3. **Q2 Grading Round:**
   - Students are re-shuffled in a **different random order** for Q2
   - Same process: view image → enter marks → next
   - This continues for Q3, Q4, ... until all questions are graded

4. **Why This Matters:**
   - Teacher can't recognize students by position (order changes every question)
   - Teacher can't see roll numbers (only anonymous IDs)
   - Grading one question at a time means the teacher applies **consistent standards** across all students

**Result:** Every student has marks for every question, all graded anonymously.

---

## Stage 5 — Report Generation

**Who:** Teacher
**Where:** Report Dashboard
**What happens:**

Only after ALL questions for ALL students are graded does the system **de-anonymize** the results.

### What the Report Shows

| Roll No. | Q1 (/10) | Q2 (/15) | Q3 (/20) | Q4 (/5) | Q5 (/10) | Total (/60) | Percentage |
|----------|----------|----------|----------|---------|----------|-------------|------------|
| 2301     | 8.0      | 12.0     | 15.0     | 4.0     | 8.5      | 47.5        | 79.2%      |
| 2302     | 6.5      | 10.0     | 18.0     | 3.0     | 7.0      | 44.5        | 74.2%      |
| ...      | ...      | ...      | ...      | ...     | ...      | ...         | ...        |

### Class Statistics
- **Class Average** — overall percentage
- **Highest / Lowest Score** — with roll numbers
- **Pass Rate** — percentage of students above the passing threshold
- **Question-wise Analysis** — which question was hardest/easiest, average marks per question

### Downloads
- **CSV Export** — spreadsheet-ready file with all results
- **PDF Report** — printable report document

**Result:** Teacher gets a complete, de-anonymized report with detailed analytics.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        REACT FRONTEND                            │
│                     (Vite + TailwindCSS)                         │
│                                                                  │
│   ExamSetup → ProcessingStatus → SegmentReview → Grading → Report│
└──────────────────────────┬───────────────────────────────────────┘
                           │ REST API (JSON)
┌──────────────────────────▼───────────────────────────────────────┐
│                      DJANGO BACKEND                              │
│                  (REST Framework + Celery)                        │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │ Exam &      │  │ Grading      │  │ Report               │    │
│  │ Upload APIs │  │ APIs         │  │ Generator            │    │
│  │             │  │ (anonymous)  │  │ (de-anonymizes)      │    │
│  └──────┬──────┘  └──────────────┘  └──────────────────────┘    │
│         │                                                        │
│  ┌──────▼────────────────────────────────────────────────────┐   │
│  │              CELERY TASK QUEUE (Redis)                     │   │
│  │                                                           │   │
│  │  PDF → Page Images → Sarvam Vision → Crop Answers         │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────────────────────────┐   │
│  │  PostgreSQL 16   │  │  Media Storage                     │   │
│  │  (all records)   │  │  /pages, /segments (cropped imgs)  │   │
│  └──────────────────┘  └────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ Sarvam      │
                    │ Vision API  │
                    │ (external)  │
                    └─────────────┘
```

---

## Data Flow Summary

```
PDF Upload                    Processing                     Grading                  Report
──────────                    ──────────                     ───────                  ──────

2301_physics.pdf ──┐
2302_physics.pdf ──┤    ┌──> Page Images ──> Sarvam AI ──> Cropped Segments
2303_physics.pdf ──┼──> │                                       │
      ...          │    │   (per page)      (detect Q#s)    (per question     ──> Teacher grades  ──> De-anonymize
2400_physics.pdf ──┘    │                                    per student)         Q1 for all          & generate
                        │                                       │                Q2 for all          CSV / PDF
                  Parse filenames                          Save as               Q3 for all          report
                  Extract roll #s                          AnswerSegment              ...
                  Assign anonymous IDs                     records
```

---

## Key Design Principles

| Principle | How It's Enforced |
|-----------|-------------------|
| **Anonymity during grading** | Roll numbers never appear in grading APIs. Only `#anon-XXXX` is shown. Student order is shuffled per question. |
| **Consistent grading standards** | Teacher must finish grading one question for ALL students before moving to the next question. |
| **Async processing** | All PDF processing happens in Celery background tasks — the teacher's browser never blocks. |
| **Graceful failure handling** | If Sarvam Vision fails, sheets are flagged for manual boundary correction. Teachers can always proceed. |
| **De-anonymization only at the end** | Roll numbers are revealed only after every question for every student is graded — no peeking. |

---

## Tech Stack at a Glance

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, TailwindCSS, Zustand |
| Backend API | Django 5.x, Django REST Framework |
| Database | PostgreSQL 16 |
| Task Queue | Celery + Redis |
| AI / OCR | Sarvam Vision Document Intelligence API |
| PDF Processing | PyMuPDF (fitz) |
| Containerization | Docker Compose |
