"""Add ClassSection and Student models, link to Exam and AnswerSheet."""

import uuid

import django.db.models.deletion
from django.db import migrations, models


def backfill_class_sections(apps, schema_editor):
    """Assign existing exams to a default ClassSection and link students."""
    ClassSection = apps.get_model("exams", "ClassSection")
    Student = apps.get_model("exams", "Student")
    Exam = apps.get_model("exams", "Exam")
    AnswerSheet = apps.get_model("exams", "AnswerSheet")

    exams = Exam.objects.filter(class_section__isnull=True)
    if not exams.exists():
        return

    default_cs, _ = ClassSection.objects.get_or_create(
        class_name="Unknown",
        section="Unknown",
    )

    exams.update(class_section=default_cs)

    for sheet in AnswerSheet.objects.filter(student__isnull=True):
        student, _ = Student.objects.get_or_create(
            class_section=default_cs,
            roll_number=sheet.roll_number,
        )
        sheet.student = student
        sheet.save(update_fields=["student"])


def reverse_backfill(apps, schema_editor):
    """No-op reverse — FKs will be dropped by reversing structural ops."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0002_answersegment_boundary_data_and_more"),
    ]

    operations = [
        # 1. Create ClassSection model
        migrations.CreateModel(
            name="ClassSection",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("class_name", models.CharField(max_length=50)),
                ("section", models.CharField(max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["class_name", "section"],
                "unique_together": {("class_name", "section")},
            },
        ),
        # 2. Create Student model
        migrations.CreateModel(
            name="Student",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("roll_number", models.CharField(max_length=50)),
                ("name", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "class_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="students",
                        to="exams.classsection",
                    ),
                ),
            ],
            options={
                "ordering": ["roll_number"],
                "unique_together": {("class_section", "roll_number")},
            },
        ),
        # 3. Add class_section FK to Exam as NULLABLE first
        migrations.AddField(
            model_name="exam",
            name="class_section",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="exams",
                to="exams.classsection",
            ),
            preserve_default=False,
        ),
        # 4. Add student FK to AnswerSheet (nullable, stays nullable)
        migrations.AddField(
            model_name="answersheet",
            name="student",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="answer_sheets",
                to="exams.student",
            ),
        ),
        # 5. Data migration: backfill existing records
        migrations.RunPython(backfill_class_sections, reverse_backfill),
        # 6. Make Exam.class_section required
        migrations.AlterField(
            model_name="exam",
            name="class_section",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="exams",
                to="exams.classsection",
            ),
        ),
    ]
