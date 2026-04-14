from django.contrib import admin

from .models import Book, BookIssue


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "total_copies", "available_copies")
    search_fields = ("title", "author", "isbn")


@admin.register(BookIssue)
class BookIssueAdmin(admin.ModelAdmin):
    list_display = ("book", "student", "issued_on", "due_on", "returned_on")
    list_filter = ("issued_on", "due_on", "returned_on")
