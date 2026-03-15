from django.db import models
from django.contrib.auth.models import User


class Receipt(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='receipts')
    vendor_name = models.CharField(max_length=255, null=True, blank=True)
    date = models.CharField(max_length=100, null=True, blank=True)
    total_amount = models.FloatField(default=0.0)
    file = models.FileField(upload_to='receipts/')
    extracted_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vendor_name or 'Unknown'} — {self.total_amount} ({self.user.username})"
