from django.urls import path
from . import views

app_name = 'receipts'

urlpatterns = [
    path('', views.index, name='index'),
    path('history/', views.history, name='history'),
    path('receipt/<int:pk>/', views.detail, name='detail'),
    path('receipt/<int:pk>/file/', views.receipt_file, name='file'),
    path('receipt/<int:pk>/preview/', views.receipt_preview, name='preview'),
]
