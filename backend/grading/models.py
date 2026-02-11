"""Models for the grading app."""

import uuid

from django.db import models

from exams.models import AnswerSegment, Exam


class Grade(models.Model):
    """A grade assigned to a single answer segment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="grades")
    segment = models.OneToOneField(
        AnswerSegment, on_delete=models.CASCADE, related_name="grade"
    )
    marks = models.DecimalField(max_digits=5, decimal_places=2)
    feedback = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["segment__question_number"]

    def __str__(self) -> str:
        return f"Grade: {self.marks} for {self.segment}"
