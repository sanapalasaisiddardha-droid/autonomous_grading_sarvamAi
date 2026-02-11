"""Views for the grading app."""

from rest_framework import status, viewsets
from rest_framework.response import Response

from .models import Grade
from .serializers import GradeSerializer


class GradeViewSet(viewsets.ModelViewSet):
    """ViewSet for Grade CRUD operations."""

    queryset = Grade.objects.all()
    serializer_class = GradeSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        exam_id = self.request.query_params.get("exam")
        question = self.request.query_params.get("question")
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if question:
            queryset = queryset.filter(segment__question_number=question)
        return queryset

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        segment = serializer.validated_data["segment"]
        exam = serializer.validated_data["exam"]

        # Validate: can only grade the current question
        if segment.question_number != exam.current_grading_question:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "message": (
                        f"Cannot grade Q{segment.question_number}. "
                        f"Currently grading Q{exam.current_grading_question}."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate marks against max
        max_marks = (
            exam.max_marks_per_question[segment.question_number - 1]
            if segment.question_number <= len(exam.max_marks_per_question)
            else 10
        )
        if serializer.validated_data["marks"] > max_marks:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "message": f"Marks cannot exceed {max_marks} for Q{segment.question_number}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        self.perform_create(serializer)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Grade saved"},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Grade updated"},
        )

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {"status": "success", "data": serializer.data, "message": "Grades retrieved"},
        )
