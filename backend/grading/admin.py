from django.contrib import admin

from .models import Grade


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("segment", "marks", "created_at")
    list_filter = ("exam",)
