from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
     created_at = models.DateTimeField(default=timezone.now, db_index=True)
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          abstract = True


class Profile(TimeStampedModel):
     class Role(models.TextChoices):
          MERCHANT = "MERCHANT", "상인"
          YOUTH = "YOUTH", "청년"

     phone_num = models.CharField(max_length=20, blank=True)
     nickname = models.CharField(max_length=30)
     role = models.CharField(max_length=10, choices=Role.choices, db_index=True)

     def __str__(self):
          return f"{self.nickname}({self.role})"


class Store(TimeStampedModel):
     owner = models.ForeignKey("accounts.Profile", on_delete=models.PROTECT, related_name="stores")
     name = models.CharField(max_length=80)
     is_authorized = models.BooleanField(default=False)  # 인증 유무
     info = models.URLField(blank=True) # 네이버 지도 링크 등

     def __str__(self):
          return self.name
