"""Serializers for the exams app."""

from rest_framework import serializers

from .models import AnswerSegment, AnswerSheet, ClassSection, Exam, Student


class ClassSectionSerializer(serializers.ModelSerializer):
    """Serializer for ClassSection model."""

    student_count = serializers.SerializerMethodField()
    exam_count = serializers.SerializerMethodField()
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = ClassSection
        fields = [
            "id", "class_name", "section", "display_name",
            "student_count", "exam_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "display_name", "created_at", "updated_at"]

    def get_student_count(self, obj: ClassSection) -> int:
        return obj.students.count()

    def get_exam_count(self, obj: ClassSection) -> int:
        return obj.exams.count()


class StudentSerializer(serializers.ModelSerializer):
    """Serializer for Student model."""

    class_section_display = serializers.CharField(
        source="class_section.display_name", read_only=True
    )

    class Meta:
        model = Student
        fields = [
            "id", "class_section", "class_section_display",
            "roll_number", "name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StudentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Student lists."""

    class Meta:
        model = Student
        fields = ["id", "roll_number", "name"]
        read_only_fields = ["id"]


class ExamSerializer(serializers.ModelSerializer):
    """Serializer for Exam model."""

    sheet_count = serializers.SerializerMethodField()
    class_section_display = serializers.CharField(
        source="class_section.display_name", read_only=True
    )

    class Meta:
        model = Exam
        fields = [
            "id", "name", "subject", "class_section", "class_section_display",
            "total_questions", "max_marks_per_question", "status",
            "current_grading_question", "sheet_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "current_grading_question", "created_at", "updated_at"]

    def get_sheet_count(self, obj: Exam) -> int:
        return obj.answer_sheets.count()


class AnswerSheetUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading answer sheets — accepts roll_number and pdf_file."""

    class Meta:
        model = AnswerSheet
        fields = [
            "id", "exam", "roll_number", "pdf_file",
            "student", "anonymous_id", "status", "created_at",
        ]
        read_only_fields = ["id", "student", "anonymous_id", "status", "created_at"]


class AnswerSheetSerializer(serializers.ModelSerializer):
    """Serializer for AnswerSheet — excludes roll_number for anonymity."""

    short_id = serializers.CharField(source="short_anonymous_id", read_only=True)

    class Meta:
        model = AnswerSheet
        fields = [
            "id", "exam", "anonymous_id", "short_id",
            "status", "page_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "anonymous_id", "status", "page_count", "created_at", "updated_at"]


class AnswerSegmentSerializer(serializers.ModelSerializer):
    """Serializer for AnswerSegment."""

    class Meta:
        model = AnswerSegment
        fields = [
            "id", "answer_sheet", "question_number",
            "image", "page_number", "confidence",
            "boundary_data", "needs_review", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SheetStatusSerializer(serializers.Serializer):
    """Serializer for a single sheet's processing status."""

    anonymous_id = serializers.UUIDField()
    short_id = serializers.CharField()
    status = serializers.CharField()
    page_count = serializers.IntegerField()
    segment_count = serializers.IntegerField()


class ProcessingStatusSerializer(serializers.Serializer):
    """Serializer for exam processing status response."""

    exam_id = serializers.UUIDField()
    exam_status = serializers.CharField()
    total_sheets = serializers.IntegerField()
    status_counts = serializers.DictField(child=serializers.IntegerField())
    sheets = SheetStatusSerializer(many=True)
