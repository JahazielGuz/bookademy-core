from django.contrib import admin

from documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "status", "page_count", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["ai_file_id", "page_count"]
