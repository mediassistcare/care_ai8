import sqlite3
import json

def show_case_data():
    conn = sqlite3.connect('care_ai_cases.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT case_number, status, feedback, details FROM cases ORDER BY case_number')
    rows = cursor.fetchall()
    
    print('=' * 100)
    print('CASES TABLE - DETAILED DATA')
    print('=' * 100)
    
    for row in rows:
        case_num, status, feedback, details_json = row
        
        print(f'\n🔹 CASE: {case_num}')
        print(f'📊 STATUS: {status}')
        print(f'💬 FEEDBACK: {feedback if feedback else "(empty)"}')
        print(f'📋 DETAILS:')
        
        try:
            details = json.loads(details_json)
            
            # Show key information from the case
            print(f'   Step Name: {details.get("step_name", "N/A")}')
            
            form_data = details.get('form_data', {})
            print(f'   Patient Email: {form_data.get("patient_email", "N/A")}')
            print(f'   Patient Phone: {form_data.get("patient_phone", "N/A")}')
            print(f'   Referring Doctor: {form_data.get("referring_doctor_name", "N/A")}')
            print(f'   ICD Codes Count: {form_data.get("final_codes_count", "N/A")}')
            print(f'   Lab Tests Count: {form_data.get("total_lab_tests", "N/A")}')
            print(f'   Eliminations Count: {form_data.get("total_eliminations", "N/A")}')
            print(f'   Step Status: {form_data.get("step_status", "N/A")}')
            print(f'   Completion Time: {form_data.get("completion_timestamp", "N/A")}')
            
            # Show AI-generated data summary
            ai_data = details.get('ai_data', {})
            if ai_data:
                icd_codes = ai_data.get('icd_codes_generated', [])
                if icd_codes:
                    print(f'   📋 ICD Codes Generated:')
                    for i, code in enumerate(icd_codes, 1):
                        if isinstance(code, dict):
                            print(f'      {i}. {code.get("code", "N/A")} - {code.get("title", "N/A")} (Confidence: {code.get("confidence", "N/A")}%)')
                
                lab_tests = ai_data.get('recommended_lab_tests', [])
                if lab_tests:
                    print(f'   🔬 Recommended Lab Tests:')
                    for i, test in enumerate(lab_tests, 1):
                        if isinstance(test, dict):
                            print(f'      {i}. {test.get("test_name", "N/A")} - {test.get("urgency", "N/A")}')
            
        except json.JSONDecodeError:
            print(f'   ❌ ERROR: Invalid JSON data')
        
        print('=' * 100)
    
    print(f'\n📊 SUMMARY: {len(rows)} total cases in database')
    conn.close()

if __name__ == "__main__":
    show_case_data()