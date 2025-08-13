from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
     created_at = models.DateTimeField(default=timezone.now, db_index=True)
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          abstract = True


class Request(TimeStampedModel):
     class Status(models.TextChoices):
          OPEN = "OPEN", "모집중"
          CLOSED = "CLOSED", "종료/중단"

     class Category(models.TextChoices):
          AD_COPY = "AD_COPY", "광고 문구"
          CARD_NEWS = "CARD_NEWS", "카드 뉴스"
          REELS = "REELS", "릴스"
          INTERIOR = "INTERIOR", "인테리어 제안"
          MARKETING = "MARKETING", "마케팅(기획)"

     owner = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="requests")
     store = models.ForeignKey("accounts.Store", on_delete=models.PROTECT, related_name="requests")
     status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
     category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
     saved_count = models.IntegerField(default=0)
     requirement = models.TextField(blank=True)

     class Meta:
          ordering = ["-created_at"]

     def __str__(self):
          return f"[{self.store}] {self.get_category_display() or '요청'}"



class Saved(TimeStampedModel):
     user = models.ForeignKey("accounts.Profile", on_delete=models.CASCADE, related_name="saves")
     request = models.ForeignKey("inquiries.Request", on_delete=models.CASCADE, related_name="saves")

     class Meta:
          unique_together = ("user", "request")

     def __str__(self):
          return f"{self.user} ▶ {self.request}"


# 찜 개수 자동 동기화
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver([post_save, post_delete], sender=Saved)
def sync_request_saved_count(sender, instance, **kwargs):
     req = instance.request
     count = Saved.objects.filter(request=req).count()
     Request.objects.filter(id=req.id).update(saved_count=count)
