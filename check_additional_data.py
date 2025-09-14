import sqlite3
import json

# Connect to database and fetch a detailed case
conn = sqlite3.connect('care_ai_cases.db')
cur = conn.cursor()

# Get the detailed case
cur.execute("SELECT case_number, details FROM cases WHERE case_number = 'CASE-2025-0001'")
case = cur.fetchone()

if case:
    print(f"Case Number: {case[0]}")
    print("="*60)
    
    try:
        details = json.loads(case[1])
        
        print("CURRENTLY DISPLAYED IN P_STEP2:")
        print("- clinical_summary")
        print("- icd_codes_generated") 
        print("- elimination_history")
        print("- recommended_lab_tests")
        print("- patient_data_summary")
        print("- differential_questions")
        
        print("\n" + "="*60)
        print("ADDITIONAL DATA AVAILABLE BUT NOT DISPLAYED:")
        
        # Check all keys in ai_generated_data
        ai_data = details.get('ai_generated_data', {})
        displayed_keys = {
            'clinical_summary', 'icd_codes_generated', 'elimination_history', 
            'recommended_lab_tests', 'patient_data_summary', 'differential_questions'
        }
        
        for key in ai_data.keys():
            if key not in displayed_keys:
                value = ai_data[key]
                if isinstance(value, dict):
                    print(f"- {key}: [Dict with {len(value)} keys: {list(value.keys())[:3]}...]")
                elif isinstance(value, list):
                    print(f"- {key}: [List with {len(value)} items]")
                elif isinstance(value, str) and len(value) > 100:
                    print(f"- {key}: [Text content, {len(value)} characters]")
                else:
                    print(f"- {key}: {value}")
        
        print("\nOTHER TOP-LEVEL DATA:")
        top_level_keys = {'ai_generated_data', 'form_data', 'files_uploaded', 'timestamp', 'step_name', 'data_source', 'step_completed'}
        for key in details.keys():
            if key not in {'ai_generated_data'}:
                value = details[key]
                if isinstance(value, dict):
                    print(f"- {key}: [Dict with {len(value)} keys: {list(value.keys())[:3]}...]")
                elif isinstance(value, list):
                    print(f"- {key}: [List with {len(value)} items]")
                else:
                    print(f"- {key}: {value}")
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")

conn.close()