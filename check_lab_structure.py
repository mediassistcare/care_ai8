#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('care_ai_cases.db')
cursor = conn.cursor()

cursor.execute("SELECT details FROM cases WHERE case_number = 'CASE-2025-0001'")
result = cursor.fetchone()

if result:
    details = json.loads(result[0])
    lab_tests = details.get('ai_generated_data', {}).get('recommended_lab_tests', [])
    if lab_tests:
        print('Sample lab test structure from working case:')
        print(json.dumps(lab_tests[0], indent=2))
    else:
        print('No lab tests found in working case')

conn.close()