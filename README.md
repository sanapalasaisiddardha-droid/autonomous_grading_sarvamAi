# Anonymous Answer Sheet Evaluation System (ExamLens)

## Project Overview
A full-stack web application for anonymous exam answer sheet evaluation. Teachers upload student answer sheet PDFs (named `roll_subject.pdf`), the system uses **Sarvam Vision API** to detect question boundaries and crop individual answer images, and teachers grade **one question at a time across all students anonymously**. After grading all questions, the system generates reports with roll number, per-question marks, total, and percentage.

## Tech Stack
- **Backend:** Django 5.x + Django REST Framework + Celery + Redis
- **Frontend:** React 18 + Vite + TailwindCSS + Zustand
- **Database:** PostgreSQL 16
- **AI/OCR:** Sarvam Vision Document Intelligence API (https://dashboard.sarvam.ai/)
- **PDF Processing:** PyMuPDF (fitz)
- **Task Queue:** Celery with Redis broker
- **Containerization:** Docker Compose

## Project Structure
```
examlens/
├── CLAUDE.md
├── prompt_plan.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── celery.py
│   │   └── wsgi.py
│   ├── exams/
│   │   ├── models.py          # Exam, QuestionConfig, AnswerSheet, AnswerSegment
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── tasks.py           # Celery tasks for PDF processing
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── sarvam_client.py    # Sarvam Vision API wrapper
│   │       ├── pdf_processor.py    # PDF → page images
│   │       ├── segmenter.py        # Question detection + cropping
│   │       └── report_generator.py # CSV/PDF report generation
│   └── grading/
│       ├── models.py          # Grade model
│       ├── serializers.py
│       ├── views.py
│       └── urls.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── App.jsx
│       ├── main.jsx
│       ├── api/
│       │   └── client.js      # Axios instance
│       ├── store/
│       │   └── examStore.js   # Zustand store
│       ├── pages/
│       │   ├── ExamSetup.jsx
│       │   ├── ProcessingStatus.jsx
│       │   ├── SegmentReview.jsx
│       │   ├── GradingInterface.jsx
│       │   └── ReportDashboard.jsx
│       └── components/
│           ├── Layout.jsx
│           ├── AnswerImageViewer.jsx
│           ├── BoundaryEditor.jsx
│           ├── MarkInput.jsx
│           └── ProgressBar.jsx
└── media/                     # uploaded PDFs, page images, cropped segments
```

## Commands
- **Backend dev server:** `cd backend && python manage.py runserver`
- **Frontend dev server:** `cd frontend && npm run dev`
- **Run migrations:** `cd backend && python manage.py makemigrations && python manage.py migrate`
- **Create superuser:** `cd backend && python manage.py createsuperuser`
- **Start Celery worker:** `cd backend && celery -A config worker -l info`
- **Start Redis:** `redis-server` or `docker run -d -p 6379:6379 redis:alpine`
- **Full stack (Docker):** `docker compose up --build`
- **Run backend tests:** `cd backend && python manage.py test`
- **Run frontend tests:** `cd frontend && npm test`
- **Lint frontend:** `cd frontend && npm run lint`

## Key Architecture Decisions

### Anonymity System
- Roll number is extracted from filename (`2301_physics.pdf` → roll=`2301`)
- Each AnswerSheet gets a UUID `anonymous_id` at upload time
- **CRITICAL:** Grading APIs NEVER expose `roll_number`. Only `anonymous_id` (displayed as short hash like `#anon-7f2e`) is shown during grading
- Student order is SHUFFLED per question so teacher cannot guess identity by position
- Roll numbers are only revealed in the final report after ALL questions are graded

### Sarvam Vision Integration
- Sarvam Vision Document Intelligence API is used for detecting question number positions on page images
- API endpoint: check latest at https://docs.sarvam.ai/
- Authentication: API key via `SARVAM_API_KEY` env var, passed as `API-Subscription-Key` header
- Each page image is sent to Sarvam Vision to detect question markers (Q1, Q2, 1., 2. etc.)
- Response includes bounding boxes / coordinates of detected text regions
- We use these coordinates to crop answer regions between consecutive question markers
- For multi-page answers: if Q[i] has no Q[i+1] on same page, crop to page bottom and continue on next page

### Question-wise Grading Lock
- Teacher MUST grade all students for Q1 before moving to Q2
- `Exam.current_grading_question` tracks which question is active
- Frontend disables "Next Question" button until all students are graded for current question
- Backend validates: cannot submit grade for Q[n+1] if any Q[n] grades are missing

### Processing Pipeline
1. Upload PDFs → parse filenames → create AnswerSheet records
2. Celery task: PDF → page images (PyMuPDF)
3. Celery task: page images → Sarvam Vision API → question marker coordinates
4. Celery task: coordinates → crop answer regions → save as AnswerSegment records
5. Flag sheets where question detection confidence is low → "needs_review" status

## Environment Variables
```
SARVAM_API_KEY=your_sarvam_api_key
DATABASE_URL=postgresql://examlens:password@localhost:5432/examlens
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173
MEDIA_ROOT=./media
```

## Coding Conventions
- Python: snake_case, type hints on all function signatures, Google-style docstrings
- JavaScript/React: camelCase, functional components only, hooks for state
- API responses: always use `{ "status": "success|error", "data": {...}, "message": "..." }` envelope
- Error handling: always return meaningful error messages, never expose stack traces to frontend
- Models: always include `created_at` and `updated_at` fields
- Serializers: use separate serializers for list vs detail views when needed
- Frontend: all API calls go through `src/api/client.js`, never raw fetch/axios in components

## IMPORTANT Rules
- NEVER expose roll_number in any grading-related API response
- ALWAYS shuffle student order when serving answer images for grading
- ALWAYS validate file naming convention on upload (`roll_subject.pdf`)
- ALWAYS use Celery for PDF processing — never process synchronously in request/response cycle
- ALWAYS save cropped answer segment images to `media/segments/{exam_id}/{question_number}/`
- ALWAYS check `Exam.current_grading_question` before accepting grades — reject out-of-order grading
- When Sarvam Vision API is unreachable, mark sheet as "failed" and allow manual segmentation

