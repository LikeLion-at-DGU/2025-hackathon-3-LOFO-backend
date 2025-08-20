from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator


class TimeStampedModel(models.Model):
     created_at = models.DateTimeField(default=timezone.now, db_index=True)
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          abstract = True


class Outcome(TimeStampedModel):
     mission = models.ForeignKey("missions.Mission", on_delete=models.CASCADE, related_name="outcomes")
     youth = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="outcomes_as_youth")
     owner = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="outcomes_as_owner")
     nopo_pick = models.BooleanField(default=False)  # 노포 픽(Y/N)

     def __str__(self):
          return f"Outcome#{self.id} (mission {self.mission_id})"


def outcome_file_path(instance, filename):
     return f"outcomes/{instance.outcome_id}/{filename}"


class OutcomeFile(TimeStampedModel):
     class Kind(models.TextChoices):
          IMAGE = "IMAGE", "이미지"
          VIDEO = "VIDEO", "비디오"
          PDF = "PDF", "PDF"

     outcome = models.ForeignKey(Outcome, on_delete=models.CASCADE, related_name="files")
     kind = models.CharField(max_length=10, choices=Kind.choices)

     file = models.FileField(
          upload_to=outcome_file_path,
          validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "mp4", "pdf"])]
     )
     mime_type = models.CharField(max_length=100, blank=True)
     size_bytes = models.BigIntegerField(null=True, blank=True)

     # 순서
     order = models.PositiveIntegerField(default=0, db_index=True)

     class Meta:
          ordering = ["order", "id"]
          indexes = [models.Index(fields=["outcome", "order"])]

     def __str__(self):
          return f"{self.kind} file for outcome {self.outcome_id}"