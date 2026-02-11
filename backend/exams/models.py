"""Models for the exams app."""

import uuid
from typing import Any

from django.db import models


def segment_upload_path(instance: Any, filename: str) -> str:
    """Generate upload path for answer segment images.

    Path format: segments/{exam_id}/{question_number}/{filename}
    """
    exam_id = instance.answer_sheet.exam_id
    return f"segments/{exam_id}/{instance.question_number}/{filename}"


class ClassSection(models.Model):
    """Represents a class-section combination (e.g., Class 4, Section B)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class_name = models.CharField(max_length=50)
    section = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("class_name", "section")]
        ordering = ["class_name", "section"]

    @property
    def display_name(self) -> str:
        """Return human-readable name like '4-B'."""
        return f"{self.class_name}-{self.section}"

    def __str__(self) -> str:
        return self.display_name


class Student(models.Model):
    """Represents a student belonging to a class-section."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, related_name="students"
    )
    roll_number = models.CharField(max_length=50)
    name = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("class_section", "roll_number")]
        ordering = ["roll_number"]

    def __str__(self) -> str:
        return f"{self.roll_number} ({self.class_section.display_name})"


class Exam(models.Model):
    """Represents an exam/evaluation session."""

    STATUS_CHOICES = [
        ("created", "Created"),
        ("processing", "Processing"),
        ("review", "Review"),
        ("grading", "Grading"),
        ("completed", "Completed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, related_name="exams"
    )
    total_questions = models.PositiveIntegerField()
    max_marks_per_question = models.JSONField(
        default=list,
        help_text="List of max marks for each question, e.g. [10, 5, 15]",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created")
    current_grading_question = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} - {self.subject}"


class AnswerSheet(models.Model):
    """Represents a single student's uploaded answer sheet PDF."""

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("segmented", "Segmented"),
        ("needs_review", "Needs Review"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="answer_sheets")
    anonymous_id = models.UUIDField(default=uuid.uuid4, unique=True)
    roll_number = models.CharField(max_length=50)
    student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="answer_sheets",
    )
    pdf_file = models.FileField(upload_to="uploads/")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    page_count = models.PositiveIntegerField(default=0)
    processing_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["roll_number"]
        unique_together = [("exam", "roll_number")]

    def __str__(self) -> str:
        return f"Sheet {self.anonymous_id} (Exam: {self.exam.name})"

    @property
    def short_anonymous_id(self) -> str:
        """Return a short hash for display during grading."""
        return f"#anon-{str(self.anonymous_id)[:4]}"


class AnswerSegment(models.Model):
    """A cropped image of a single answer to a single question."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer_sheet = models.ForeignKey(
        AnswerSheet, on_delete=models.CASCADE, related_name="segments"
    )
    question_number = models.PositiveIntegerField()
    image = models.ImageField(upload_to=segment_upload_path)
    page_number = models.PositiveIntegerField()
    confidence = models.FloatField(
        default=1.0, help_text="Detection confidence from Sarvam Vision"
    )
    boundary_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Crop coordinates: {y_start, y_end, pages, source}",
    )
    needs_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question_number", "page_number"]
        unique_together = [("answer_sheet", "question_number")]

    def __str__(self) -> str:
        return f"Q{self.question_number} - Sheet {self.answer_sheet.anonymous_id}"
