"""URL configuration for ExamLens project."""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def api_root(request) -> Response:
    """API root endpoint."""
    return Response({
        "status": "success",
        "data": {
            "message": "ExamLens API v1",
            "endpoints": {
                "exams": "/api/exams/",
                "grading": "/api/grading/",
            },
        },
        "message": "Welcome to ExamLens API",
    })


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api_root, name="api-root"),
    path("api/exams/", include("exams.urls")),
    path("api/grading/", include("grading.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
