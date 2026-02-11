from django.contrib import admin

from .models import AnswerSegment, AnswerSheet, ClassSection, Exam, Student


@admin.register(ClassSection)
class ClassSectionAdmin(admin.ModelAdmin):
    list_display = ("class_name", "section", "display_name", "created_at")
    list_filter = ("class_name",)
    search_fields = ("class_name", "section")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("roll_number", "name", "class_section", "created_at")
    list_filter = ("class_section",)
    search_fields = ("roll_number", "name")


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "class_section", "total_questions", "status", "created_at")
    list_filter = ("status", "class_section")


@admin.register(AnswerSheet)
class AnswerSheetAdmin(admin.ModelAdmin):
    list_display = ("anonymous_id", "exam", "roll_number", "student", "status", "created_at")
    list_filter = ("status", "exam")


@admin.register(AnswerSegment)
class AnswerSegmentAdmin(admin.ModelAdmin):
    list_display = ("answer_sheet", "question_number", "confidence", "needs_review")
    list_filter = ("needs_review", "question_number")
