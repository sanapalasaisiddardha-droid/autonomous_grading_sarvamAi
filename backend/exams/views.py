"""Views for the exams app."""

import logging
import os
import shutil

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from .models import AnswerSegment, AnswerSheet, ClassSection, Exam, Student
from .serializers import (
    AnswerSegmentSerializer,
    AnswerSheetSerializer,
    AnswerSheetUploadSerializer,
    ClassSectionSerializer,
    ExamSerializer,
    ProcessingStatusSerializer,
    StudentSerializer,
)


class ClassSectionViewSet(viewsets.ModelViewSet):
    """ViewSet for ClassSection CRUD operations."""

    queryset = ClassSection.objects.all()
    serializer_class = ClassSectionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        class_name = self.request.query_params.get("class_name")
        if class_name:
            queryset = queryset.filter(class_name=class_name)
        return queryset

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Class sections retrieved"},
        )

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Class section created"},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="classes")
    def classes(self, request) -> Response:
        """Return distinct class names with aggregated counts."""
        data = (
            ClassSection.objects
            .values("class_name")
            .annotate(
                section_count=Count("id"),
                student_count=Count("students"),
                exam_count=Count("exams"),
            )
            .order_by("class_name")
        )
        return Response(
            {"status": "success", "data": list(data), "message": "Classes retrieved"},
        )

    @action(detail=False, methods=["post"], url_path="delete-class")
    def delete_class(self, request) -> Response:
        """Delete all sections, students, exams, and media for a class name."""
        class_name = request.data.get("class_name", "").strip()
        if not class_name:
            return Response(
                {"status": "error", "data": None, "message": "class_name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sections = ClassSection.objects.filter(class_name=class_name)
        if not sections.exists():
            return Response(
                {"status": "error", "data": None, "message": f'Class "{class_name}" not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Clean up media files for every exam under these sections
        for section in sections:
            for exam in section.exams.all():
                exam_id = str(exam.pk)
                # Delete uploaded PDFs
                for sheet in exam.answer_sheets.all():
                    if sheet.pdf_file:
                        try:
                            if os.path.isfile(sheet.pdf_file.path):
                                os.remove(sheet.pdf_file.path)
                        except Exception as e:
                            logger.warning("Failed to delete PDF %s: %s", sheet.pdf_file.path, e)
                # Delete page images
                pages_dir = os.path.join(settings.MEDIA_ROOT, "pages", exam_id)
                if os.path.isdir(pages_dir):
                    shutil.rmtree(pages_dir, ignore_errors=True)
                # Delete segment images
                segments_dir = os.path.join(settings.MEDIA_ROOT, "segments", exam_id)
                if os.path.isdir(segments_dir):
                    shutil.rmtree(segments_dir, ignore_errors=True)

        # CASCADE deletes students, exams, sheets, segments
        count = sections.count()
        sections.delete()

        return Response(
            {
                "status": "success",
                "data": None,
                "message": f'Class "{class_name}" deleted ({count} section{"s" if count != 1 else ""})',
            },
        )

    @action(detail=False, methods=["post"], url_path="get-or-create")
    def get_or_create_action(self, request) -> Response:
        """Idempotent get-or-create for a class-section."""
        class_name = request.data.get("class_name", "").strip()
        section = request.data.get("section", "").strip()
        if not class_name or not section:
            return Response(
                {"status": "error", "data": None, "message": "class_name and section are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            obj, created = ClassSection.objects.get_or_create(
                class_name=class_name, section=section,
            )
        except IntegrityError:
            obj = ClassSection.objects.get(class_name=class_name, section=section)
            created = False
        serializer = self.get_serializer(obj)
        return Response(
            {
                "status": "success",
                "data": serializer.data,
                "message": "Class section created" if created else "Class section retrieved",
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StudentViewSet(viewsets.ModelViewSet):
    """ViewSet for Student CRUD operations."""

    queryset = Student.objects.all()
    serializer_class = StudentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        class_section = self.request.query_params.get("class_section")
        if class_section:
            queryset = queryset.filter(class_section_id=class_section)
        return queryset

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Students retrieved"},
        )

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Student created"},
            status=status.HTTP_201_CREATED,
        )


class ExamViewSet(viewsets.ModelViewSet):
    """ViewSet for Exam CRUD operations."""

    queryset = Exam.objects.all()
    serializer_class = ExamSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        class_section = self.request.query_params.get("class_section")
        if class_section:
            queryset = queryset.filter(class_section_id=class_section)
        return queryset

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Exam created"},
            status=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Exams retrieved"},
        )

    def destroy(self, request, *args, **kwargs) -> Response:
        """Delete an exam and all associated data + media files."""
        exam = self.get_object()
        exam_id = str(exam.pk)

        # Delete uploaded PDF files for each answer sheet
        for sheet in exam.answer_sheets.all():
            if sheet.pdf_file:
                try:
                    if os.path.isfile(sheet.pdf_file.path):
                        os.remove(sheet.pdf_file.path)
                except Exception as e:
                    logger.warning("Failed to delete PDF %s: %s", sheet.pdf_file.path, e)

        # Delete page images directory: media/pages/{exam_id}/
        pages_dir = os.path.join(settings.MEDIA_ROOT, "pages", exam_id)
        if os.path.isdir(pages_dir):
            shutil.rmtree(pages_dir, ignore_errors=True)

        # Delete segment images directory: media/segments/{exam_id}/
        segments_dir = os.path.join(settings.MEDIA_ROOT, "segments", exam_id)
        if os.path.isdir(segments_dir):
            shutil.rmtree(segments_dir, ignore_errors=True)

        exam_name = exam.name
        # CASCADE deletes AnswerSheets and AnswerSegments
        exam.delete()

        return Response(
            {"status": "success", "data": None, "message": f'Exam "{exam_name}" deleted'},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="process")
    def start_processing(self, request, pk=None) -> Response:
        """Kick off PDF processing for all uploaded sheets in this exam."""
        from .tasks import process_exam

        exam = self.get_object()

        if exam.status not in ("created", "review"):
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "message": f"Exam is in '{exam.status}' state, can only process from 'created' or 'review'",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        sheet_count = exam.answer_sheets.filter(status="uploaded").count()
        if sheet_count == 0:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "message": "No uploaded answer sheets to process",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        process_exam.delay(str(exam.pk))

        return Response(
            {
                "status": "success",
                "data": {"exam_id": str(exam.pk), "sheets_queued": sheet_count},
                "message": f"Processing started for {sheet_count} sheets",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="grading-status")
    def grading_status(self, request, pk=None) -> Response:
        """Return grading progress: per-question graded/total counts."""
        exam = self.get_object()
        total_questions = exam.total_questions

        # Count total segmented sheets (only those with segments for each question)
        sheets = exam.answer_sheets.filter(
            status__in=["segmented", "needs_review"]
        )
        total_sheets = sheets.count()

        questions = []
        for q in range(1, total_questions + 1):
            segments = AnswerSegment.objects.filter(
                answer_sheet__exam=exam,
                question_number=q,
            )
            total = segments.count()
            graded = segments.filter(grade__isnull=False).count()
            questions.append({
                "question_number": q,
                "total": total,
                "graded": graded,
                "max_marks": (
                    exam.max_marks_per_question[q - 1]
                    if q <= len(exam.max_marks_per_question)
                    else 10
                ),
            })

        return Response({
            "status": "success",
            "data": {
                "exam_id": str(exam.pk),
                "exam_name": exam.name,
                "exam_status": exam.status,
                "current_grading_question": exam.current_grading_question,
                "total_questions": total_questions,
                "total_sheets": total_sheets,
                "questions": questions,
            },
            "message": "Grading status retrieved",
        })

    @action(detail=True, methods=["post"], url_path="advance-question")
    def advance_question(self, request, pk=None) -> Response:
        """Advance to the next grading question after all current are graded."""
        exam = self.get_object()
        current_q = exam.current_grading_question

        # Check all segments for current question are graded
        segments = AnswerSegment.objects.filter(
            answer_sheet__exam=exam,
            question_number=current_q,
        )
        ungraded = segments.filter(grade__isnull=True).count()
        if ungraded > 0:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "message": f"Q{current_q} has {ungraded} ungraded answer(s)",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if current_q >= exam.total_questions:
            exam.status = "completed"
            exam.save(update_fields=["status", "updated_at"])
            return Response({
                "status": "success",
                "data": {"exam_status": "completed"},
                "message": "All questions graded. Exam completed!",
            })

        exam.current_grading_question = current_q + 1
        exam.save(update_fields=["current_grading_question", "updated_at"])
        return Response({
            "status": "success",
            "data": {"current_grading_question": exam.current_grading_question},
            "message": f"Advanced to Q{exam.current_grading_question}",
        })

    @action(detail=True, methods=["post"], url_path="approve-review")
    def approve_review(self, request, pk=None) -> Response:
        """Move exam from review to grading, marking needs_review sheets as accepted."""
        exam = self.get_object()
        if exam.status != "review":
            return Response(
                {"status": "error", "data": None, "message": f"Exam is '{exam.status}', not 'review'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Accept needs_review sheets as segmented
        exam.answer_sheets.filter(status="needs_review").update(status="segmented")

        # Check if there are any segmented sheets to grade
        segmented = exam.answer_sheets.filter(status="segmented").count()
        if segmented == 0:
            return Response(
                {"status": "error", "data": None, "message": "No segmented sheets to grade"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exam.status = "grading"
        exam.save(update_fields=["status", "updated_at"])
        return Response({
            "status": "success",
            "data": {"exam_status": "grading", "segmented_sheets": segmented},
            "message": f"Approved. {segmented} sheet(s) ready for grading.",
        })

    @action(detail=True, methods=["get"], url_path="report")
    def report(self, request, pk=None) -> Response:
        """Return full grading report with roll numbers revealed."""
        from grading.models import Grade

        exam = self.get_object()
        sheets = exam.answer_sheets.all().order_by("roll_number")

        students_data = []
        for sheet in sheets:
            question_marks = []
            total = 0
            for q in range(1, exam.total_questions + 1):
                try:
                    segment = sheet.segments.get(question_number=q)
                    grade = Grade.objects.filter(segment=segment).first()
                    m = float(grade.marks) if grade else None
                except AnswerSegment.DoesNotExist:
                    m = None
                question_marks.append(m)
                if m is not None:
                    total += m

            max_total = sum(exam.max_marks_per_question) if exam.max_marks_per_question else 0
            percentage = round((total / max_total) * 100, 1) if max_total > 0 else 0

            students_data.append({
                "roll_number": sheet.roll_number,
                "anonymous_id": sheet.short_anonymous_id,
                "question_marks": question_marks,
                "total": total,
                "max_total": max_total,
                "percentage": percentage,
            })

        return Response({
            "status": "success",
            "data": {
                "exam_id": str(exam.pk),
                "exam_name": exam.name,
                "subject": exam.subject,
                "class_section_display": exam.class_section.display_name if exam.class_section else "",
                "total_questions": exam.total_questions,
                "max_marks_per_question": exam.max_marks_per_question,
                "students": students_data,
            },
            "message": "Report generated",
        })

    @action(detail=True, methods=["get"], url_path="processing-status")
    def processing_status(self, request, pk=None) -> Response:
        """Return per-status counts and per-sheet status (anonymous only)."""
        exam = self.get_object()
        sheets = exam.answer_sheets.all()

        # Count by status
        status_counts: dict[str, int] = {}
        sheet_data = []
        for sheet in sheets:
            status_counts[sheet.status] = status_counts.get(sheet.status, 0) + 1
            sheet_data.append(
                {
                    "anonymous_id": sheet.anonymous_id,
                    "short_id": sheet.short_anonymous_id,
                    "status": sheet.status,
                    "page_count": sheet.page_count,
                    "segment_count": sheet.segments.count(),
                }
            )

        data = {
            "exam_id": exam.pk,
            "exam_status": exam.status,
            "total_sheets": sheets.count(),
            "status_counts": status_counts,
            "sheets": sheet_data,
        }

        serializer = ProcessingStatusSerializer(data)
        return Response(
            {
                "status": "success",
                "data": serializer.data,
                "message": "Processing status retrieved",
            },
        )


class AnswerSheetViewSet(viewsets.ModelViewSet):
    """ViewSet for AnswerSheet operations."""

    queryset = AnswerSheet.objects.all()
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == "create":
            return AnswerSheetUploadSerializer
        return AnswerSheetSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        exam_id = self.request.query_params.get("exam")
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        return queryset

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exam = serializer.validated_data["exam"]
        roll_number = serializer.validated_data["roll_number"]

        student = None
        if hasattr(exam, "class_section") and exam.class_section_id:
            student, _ = Student.objects.get_or_create(
                class_section=exam.class_section,
                roll_number=roll_number,
            )

        serializer.save(student=student)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Answer sheet uploaded"},
            status=status.HTTP_201_CREATED,
        )


class AnswerSegmentViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for AnswerSegment (read-only)."""

    queryset = AnswerSegment.objects.all()
    serializer_class = AnswerSegmentSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        question = self.request.query_params.get("question")
        exam_id = self.request.query_params.get("exam")
        if question:
            queryset = queryset.filter(question_number=question)
        if exam_id:
            queryset = queryset.filter(answer_sheet__exam_id=exam_id)
        return queryset

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Segments retrieved"},
        )
