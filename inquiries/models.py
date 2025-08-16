from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
     created_at = models.DateTimeField(default=timezone.now, db_index=True)
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          abstract = True

def request_image_path(instance, filename):
     # /requests/<request_id>/<filename>
     return f"requests/{instance.id or 'new'}/{filename}"

def ai_request_image_path(instance, filename):
     return f"ai_requests/{instance.id or 'new'}/{filename}"

class Request(TimeStampedModel):
     class Status(models.TextChoices):
          OPEN = "OPEN", "모집중"
          ONGOING = "ONGOING", "진행중"
          CLOSED = "CLOSED", "종료/중단"

     class Category(models.TextChoices):
          PROMO_VIDEO = "PROMO_VIDEO", "홍보영상"
          POSTER_FLYER = "POSTER_FLYER", "포스터·전단"
          SNS_IMAGE = "SNS_IMAGE", "SNS 이미지"
          INTERIOR_PROPOSAL = "INTERIOR_PROPOSAL", "인테리어 제안"
          PROMOTION_PLANNING = "PROMOTION_PLANNING", "홍보기획"
          AD_COPY = "AD_COPY", "광고문구"

     owner = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="requests", db_index=True)
     
     # === 필수값 ===
     store_name = models.CharField(max_length=50, db_index=True, default="가게명") # 가게명
     image = models.ImageField(upload_to=request_image_path, default="") # 가게 사진 (요청 썸네일용)
     url = models.URLField(default='https://example.com')
     status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
     category = models.CharField(max_length=30, choices=Category.choices, db_index=True)
     title = models.CharField(max_length=16, default="제목")
     content = models.TextField(blank=True, null=True)
     saved_count = models.IntegerField(default=0)

     class Meta:
          ordering = ["-created_at"]

     def __str__(self):
          return f"[{self.store_name}] {self.get_category_display() or '요청'}"

class AiRequest(TimeStampedModel):
     store_name = models.CharField(max_length=50, db_index=True, default="가게명")
     image = models.ImageField(upload_to=ai_request_image_path, default="")
     url = models.URLField(default="https://example.com")
     category = models.CharField(max_length=30, choices=Request.Category.choices, db_index=True)
     title = models.CharField(max_length=16, default="제목")
     content = models.TextField(blank=True, null=True)
     status = models.CharField(max_length=15, choices=Request.Status.choices, default=Request.Status.OPEN, db_index=True)
     saved_count = models.IntegerField(default=0)

     class Meta:
          ordering = ["-created_at"]

     def __str__(self):
          return f"[AI:{self.store_name}] {self.get_category_display()} ({self.get_status_display()})"


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
