from django.urls import path
from .api_views import (
    UploadReceiptView, ReceiptListView, ReceiptDetailView, ReceiptStatusView,
)

app_name = 'receipts_api'

urlpatterns = [
    path('upload/', UploadReceiptView.as_view(), name='upload'),
    path('receipts/', ReceiptListView.as_view(), name='receipt_list'),
    path('receipts/status/', ReceiptStatusView.as_view(), name='receipt_status'),
    path('receipts/<int:pk>/', ReceiptDetailView.as_view(), name='receipt_detail'),
]
