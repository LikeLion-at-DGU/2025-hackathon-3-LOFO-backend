from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
     created_at = models.DateTimeField(default=timezone.now, db_index=True)
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          abstract = True


class Mission(TimeStampedModel):
     class Status(models.TextChoices):
          IN_PROGRESS = "IN_PROGRESS", "진행중"
          DONE = "DONE", "완료"

     request = models.OneToOneField("inquiries.Request", on_delete=models.PROTECT, related_name="mission")
     youth = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="missions")
     deadline = models.DateTimeField(null=True, blank=True)
     status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
     plan = models.TextField(blank=True)  # 작업/프로토타입 기록

     def __str__(self):
          return f"Mission#{self.id} for {self.request_id}"
