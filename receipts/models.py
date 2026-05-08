from django.db import models

class Receipt(models.Model):
    vendor_name = models.CharField(max_length=255, null=True, blank=True)
    date = models.CharField(max_length=100, null=True, blank=True)
    total_amount = models.FloatField(default=0.0)
    # Original file save karne ke liye
    file = models.FileField(upload_to='receipts/') 
    # Saara extracted data JSON format mein store karne ke liye
    extracted_data = models.JSONField(null=True, blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.vendor_name} - {self.total_amount}"