import sqlite3, json
conn = sqlite3.connect('care_ai_cases.db')
cursor = conn.cursor()

cursor.execute("SELECT details FROM cases WHERE case_number = 'CASE-2025-0002'")
result = cursor.fetchone()

if result:
    details = json.loads(result[0])
    form_data = details.get('form_data', {})
    print('CASE-2025-0002 contact information:')
    print(f'  Patient Email: {form_data.get("patient_email", "Not found")}')
    print(f'  Patient Phone: {form_data.get("patient_phone", "Not found")}')
    print(f'  Referring Doctor: {form_data.get("referring_doctor_name", "Not found")}')
    print(f'  Doctor Email: {form_data.get("referring_doctor_email", "Not found")}')
    print(f'  Doctor Expertise: {form_data.get("referring_doctor_details", {}).get("area_of_expertise", "Not found")}')

conn.close()