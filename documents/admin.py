from django.contrib import admin

from documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "status", "page_count", "created_at"]
    list_filter = ["status"]
    # The extracted text is large and not useful to edit by hand.
    exclude = ["pages"]
    readonly_fields = ["page_count"]
