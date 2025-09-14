#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('care_ai_cases.db')
cursor = conn.cursor()

cursor.execute('SELECT case_number, status FROM cases WHERE status = "pending_review"')
cases = cursor.fetchall()

print('Available test cases:')
for case_number, status in cases:
    print(f'  - {case_number}: {status}')

# Check if our test case has contact info
cursor.execute('SELECT details FROM cases WHERE case_number = "CASE-2025-CONTACTS"')
result = cursor.fetchone()

if result:
    details = json.loads(result[0])
    form_data = details.get('form_data', {})
    print(f'\nCASE-2025-CONTACTS contact info:')
    print(f'  Patient Email: {form_data.get("patient_email", "Not found")}')
    print(f'  Patient Phone: {form_data.get("patient_phone", "Not found")}')
    print(f'  Doctor Name: {form_data.get("referring_doctor_name", "Not found")}')
    print(f'  Doctor Email: {form_data.get("referring_doctor_email", "Not found")}')

conn.close()