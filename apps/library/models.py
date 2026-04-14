from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    isbn = models.CharField(max_length=64, blank=True)
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def clean(self):
        if self.available_copies > self.total_copies:
            raise ValidationError("Available copies cannot exceed total copies.")

    def save(self, *args, **kwargs):
        if not self.pk and self.available_copies > self.total_copies:
            self.available_copies = self.total_copies
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.available_copies}/{self.total_copies})"


class BookIssue(models.Model):
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="issues")
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="book_issues")
    issued_on = models.DateField(default=timezone.now)
    due_on = models.DateField()
    returned_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_on"]

    def clean(self):
        if self.returned_on and self.returned_on < self.issued_on:
            raise ValidationError("Returned date cannot be before issue date.")

    @property
    def is_overdue(self) -> bool:
        return self.returned_on is None and self.due_on < timezone.localdate()

    def __str__(self):
        return f"{self.student.admission_number} -> {self.book.title}"
