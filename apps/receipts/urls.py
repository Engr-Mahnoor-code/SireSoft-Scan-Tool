from django.urls import path
from . import views

app_name = 'receipts'

urlpatterns = [
    path('', views.index, name='index'),
    path('history/', views.history, name='history'),
    path('receipt/<int:pk>/', views.detail, name='detail'),
    path('receipt/<int:pk>/edit/', views.edit, name='edit'),
    path('receipt/<int:pk>/delete/', views.delete, name='delete'),
    path('receipt/<int:pk>/rescan/', views.rescan, name='rescan'),
    path('receipt/<int:pk>/file/', views.receipt_file, name='file'),
    path('receipt/<int:pk>/corrected/', views.receipt_corrected,
         name='corrected'),
    path('receipt/<int:pk>/preview/', views.receipt_preview, name='preview'),
]
