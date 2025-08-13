from django.db import models
from django.utils import timezone


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
     content = models.TextField(blank=True)

     def __str__(self):
          return f"Outcome#{self.id} (mission {self.mission_id})"


def outcome_image_path(instance, filename):
     return f"outcomes/{instance.outcome_id}/{filename}"


class OutcomeImage(TimeStampedModel):
     outcome = models.ForeignKey("outcomes.Outcome", on_delete=models.CASCADE, related_name="images")
     image = models.ImageField(upload_to=outcome_image_path)

     def __str__(self):
          return f"Image for outcome {self.outcome_id}"
