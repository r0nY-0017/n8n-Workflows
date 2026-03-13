# 🎋 Bamboo Dine — Booking System

## চালু করার নিয়ম
```bash
pip install -r requirements.txt
cp .env.example .env   # তারপর .env ফাইলে আপনার key বসান
uvicorn main:app --reload --port 8000
```

## URLs
- Website: http://localhost:8000
- Admin:   http://localhost:8000/admin

## n8n Setup
1. n8n চালু করুন
2. `n8n/workflow.json` import করুন
3. Google Sheets credential সেট করুন
4. Gmail SMTP credential সেট করুন
5. Sheet-এ এই headers দিন (row 1):
   `ID | Name | Phone | Email | Date | Time | Guests | Status | Source | Notes | Created_At`
6. Sheet ID দিয়ে workflow-এর `YOUR_SHEET_ID` replace করুন
7. .env-এ n8n URL গুলো বসান
