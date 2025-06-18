from django.db import models


class TaskHistory(models.Model):
    name = models.CharField(max_length=255)
    task_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=50)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True, help_text="Duration in seconds")
    args = models.TextField(null=True, blank=True)
    kwargs = models.TextField(null=True, blank=True)
    result = models.TextField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-created_at"]
        indexes = [
            models.Index(fields=["task_id"]),
            models.Index(fields=["name"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.status}) [{self.task_id}]"
