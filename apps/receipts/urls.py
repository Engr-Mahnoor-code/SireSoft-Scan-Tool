from django.urls import path
from . import views

app_name = 'receipts'

urlpatterns = [
    path('', views.index, name='index'),
    path('history/', views.history, name='history'),
    path('receipt/<int:pk>/', views.detail, name='detail'),
]
