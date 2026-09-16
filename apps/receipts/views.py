from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Receipt
from .api_views import MAX_FILES_PER_UPLOAD, MAX_FILE_SIZE


@login_required
def index(request):
    """Upload page — entry point for receipt scanning."""
    return render(request, 'receipts/index.html', {
        'max_files': MAX_FILES_PER_UPLOAD,
        'max_file_size': MAX_FILE_SIZE,
    })


@login_required
def history(request):
    """History page — list all receipts for the logged-in user."""
    receipts = Receipt.objects.filter(user=request.user)
    return render(request, 'receipts/history.html', {'receipts': receipts})


@login_required
def detail(request, pk):
    """Detail page — view a single receipt's extracted data."""
    receipt = get_object_or_404(Receipt, pk=pk, user=request.user)
    return render(request, 'receipts/detail.html', {'receipt': receipt})
