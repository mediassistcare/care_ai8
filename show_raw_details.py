import sqlite3
import json

def show_raw_case_details():
    conn = sqlite3.connect('care_ai_cases.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT case_number, details FROM cases ORDER BY case_number')
    rows = cursor.fetchall()
    
    print('=' * 100)
    print('CASES TABLE - RAW DETAILS COLUMN DATA')
    print('=' * 100)
    
    for row in rows:
        case_num, details_json = row
        
        print(f'\n🔹 CASE: {case_num}')
        print('📋 RAW DETAILS JSON:')
        print('-' * 100)
        
        try:
            # Parse and pretty-print the JSON for readability
            details = json.loads(details_json)
            formatted_json = json.dumps(details, indent=2, ensure_ascii=False)
            print(formatted_json)
        except json.JSONDecodeError as e:
            print(f'❌ ERROR: Invalid JSON - {e}')
            print('Raw string:')
            print(details_json)
        
        print('-' * 100)
    
    print(f'\n📊 SUMMARY: {len(rows)} total cases displayed')
    conn.close()

if __name__ == "__main__":
    show_raw_case_details()