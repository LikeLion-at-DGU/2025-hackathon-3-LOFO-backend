from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
     created_at = models.DateTimeField(default=timezone.now, db_index=True)
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          abstract = True


class Like(TimeStampedModel):
     user = models.ForeignKey("accounts.Profile", on_delete=models.CASCADE, related_name="likes")
     outcome = models.ForeignKey("outcomes.Outcome", on_delete=models.CASCADE, related_name="likes")

     class Meta:
          unique_together = ("user", "outcome")

     def __str__(self):
          return f"♥ {self.user_id} -> {self.outcome_id}"


class Comment(TimeStampedModel):
     user = models.ForeignKey("accounts.Profile", on_delete=models.CASCADE, related_name="comments")
     outcome = models.ForeignKey("outcomes.Outcome", on_delete=models.CASCADE, related_name="comments")
     content = models.TextField()

     def __str__(self):
          return f"Comment#{self.id} by {self.user_id}"
