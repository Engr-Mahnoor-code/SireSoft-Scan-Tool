import google.generativeai as genai
import json
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from .models import Receipt

# Gemini Setup - Stable Model Use karein
genai.configure(api_key="AIzaSyCbZD_sJwi3Ux16UgyN4YhOOlEaett9LKA")

def index(request):
    return render(request, 'receipts/index.html')

@csrf_exempt
def upload_receipt(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        
        # 1. PEHLE RECORD CREATE KAREIN (PostgreSQL mein row ban jayegi)
        # Professional web applications pehle file save karti hain
        receipt_instance = Receipt.objects.create(file=uploaded_file)
        
        try:
            # AI Model Initialization - (Stable name use karein)
            model = genai.GenerativeModel('gemini-pro')
            
            # File ko binary mein read karein AI ke liye
            file_path = receipt_instance.file.path
            with open(file_path, 'rb') as f:
                file_data = f.read()

            prompt = """Analyze this receipt or invoice. Return ONLY a valid JSON object:
            {
                "establishment": {"name": "", "location": "", "date": "", "receipt_number": ""},
                "items": [{"name": "", "quantity": 1, "unit_price": 0, "total": 0}],
                "bill_summary": {"currency": "PKR", "tax": 0, "grand_total": 0, "payment_method": ""},
                "insights": {"most_expensive_item": "", "verified": true}
            }"""

            # AI Extraction Request (Image/PDF dono ke liye)
            response = model.generate_content([
                prompt, 
                {'mime_type': uploaded_file.content_type, 'data': file_data}
            ])

            # 2. AI Response ko Clean karein
            res_text = response.text.strip()
            if "```json" in res_text:
                res_text = res_text.split("```json")[1].split("```")[0].strip()
            elif "```" in res_text:
                res_text = res_text.split("```")[1].split("```")[0].strip()

            data = json.loads(res_text)

            # 3. POSTGRESQL DATABASE UPDATE (Ab [null] values fill ho jayengi)
            receipt_instance.vendor_name = data.get('establishment', {}).get('name', 'Unknown Vendor')
            receipt_instance.date = data.get('establishment', {}).get('date', 'N/A')
            
            # Total amount ko extract aur save karein
            total = data.get('bill_summary', {}).get('grand_total', 0)
            receipt_instance.total_amount = float(total) if total else 0.0
            
            # Poora JSON bhi store karein professional database schema ki tarah
            receipt_instance.extracted_data = data
            receipt_instance.save() # PostgreSQL mein data update ho gaya

            return JsonResponse(data)

        except Exception as e:
            # Agar error aaye toh record delete nahi hoga lekin user ko error dikhega
            print(f"Server Error: {str(e)}")
            return JsonResponse({'error': f"AI Extraction Error: {str(e)}"}, status=500)

    return JsonResponse({'error': 'No file uploaded'}, status=400)