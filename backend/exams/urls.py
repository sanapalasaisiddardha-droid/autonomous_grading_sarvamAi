"""URL configuration for the exams app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnswerSegmentViewSet,
    AnswerSheetViewSet,
    ClassSectionViewSet,
    ExamViewSet,
    StudentViewSet,
)

router = DefaultRouter()
router.register(r"class-sections", ClassSectionViewSet)
router.register(r"students", StudentViewSet)
router.register(r"exams", ExamViewSet)
router.register(r"sheets", AnswerSheetViewSet)
router.register(r"segments", AnswerSegmentViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
