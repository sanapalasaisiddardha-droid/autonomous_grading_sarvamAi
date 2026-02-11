"""Serializers for the grading app."""

from rest_framework import serializers

from .models import Grade


class GradeSerializer(serializers.ModelSerializer):
    """Serializer for Grade model."""

    class Meta:
        model = Grade
        fields = [
            "id", "exam", "segment", "marks",
            "feedback", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
