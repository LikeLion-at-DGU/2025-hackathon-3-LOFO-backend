from django.db import models, transaction
from django.utils import timezone


class TimeStampedModel(models.Model):
     created_at = models.DateTimeField(default=timezone.now, db_index=True)
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          abstract = True

class Mission(TimeStampedModel):
     class Status(models.TextChoices):
          IN_PROGRESS = "IN_PROGRESS", "진행중"
          DISCARD = "DISCARD", "포기"
          EXPIRE = "EXPIRE", "기한만료"
          DONE = "DONE", "완료"
     request = models.ForeignKey("inquiries.Request", on_delete=models.PROTECT, related_name="missions", db_index=True,)
     #request = models.OneToOneField("inquiries.Request", on_delete=models.PROTECT, related_name="mission")
     youth = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="missions")
     deadline = models.DateTimeField(null=True, blank=True)
     status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
     
     ai_model = models.CharField(max_length=50, default="gpt-4o-mini")
     ai_plan_ver = models.PositiveIntegerField(default=1) #플랜 재생성 시 버전 증가
     plan = models.JSONField(blank=True, null=True)  # AI가 만든 3단계 계획 JSON 으로 저장

     def __str__(self):
          return f"Mission#{self.id} for {self.request_id}"
     

class MissionStep(TimeStampedModel):
     class StepStatus(models.TextChoices):
          TODO    = "TODO", "대기"
          DOING   = "DOING", "진행중"
          DONE    = "DONE", "완료"
          EXPIRED = "EXPIRED", "기한만료"

     mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name="steps")
     step_no = models.PositiveSmallIntegerField() # 1,2,3
     title = models.CharField(max_length=200)
     description = models.TextField()
     reference = models.TextField()
     due = models.DateField(null=True, blank=True)

     status = models.CharField(max_length=10, choices=StepStatus.choices, default=StepStatus.TODO, db_index=True)
     completed_at = models.DateTimeField(null=True, blank=True)
     # 파일 저장 안하고 피드백 요청만 카운트
     feedback_count = models.PositiveIntegerField(default=0)

     class Meta:
          unique_together = [("mission", "step_no")]
          indexes = [models.Index(fields=["mission", "step_no"])]

     def mark_done(self):
          self.status = self.StepStatus.DONE
          self.completed_at = timezone.now()
          self.save(update_fields=["status", "completed_at", "updated_at"])
