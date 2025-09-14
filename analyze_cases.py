import sqlite3
import json

def analyze_cases():
    conn = sqlite3.connect('care_ai_cases.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT case_number, details FROM cases ORDER BY case_number')
    rows = cursor.fetchall()
    
    print('Case Analysis:')
    print('=' * 80)
    
    for row in rows:
        case_num, details_json = row
        try:
            details = json.loads(details_json)
            session_id = details.get('session_id', 'N/A')
            step_name = details.get('step_name', 'N/A')
            
            # Try to get patient identifier
            form_data = details.get('form_data', {})
            patient_email = form_data.get('patient_email', 'N/A')
            
            # Get timestamp info
            completion_timestamp = form_data.get('completion_timestamp', 'N/A')
            
            print(f'Case: {case_num}')
            print(f'Session ID: {session_id}')
            print(f'Step Name: {step_name}')
            print(f'Patient Email: {patient_email}')
            print(f'Completion Time: {completion_timestamp}')
            print('-' * 40)
            
        except json.JSONDecodeError:
            print(f'Case: {case_num} - ERROR: Invalid JSON')
            print('-' * 40)
    
    print(f'Total cases: {len(rows)}')
    conn.close()

if __name__ == "__main__":
    analyze_cases()