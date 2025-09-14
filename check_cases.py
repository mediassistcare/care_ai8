import sqlite3

def check_cases():
    conn = sqlite3.connect('care_ai_cases.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT case_number, status, feedback, SUBSTR(details, 1, 150) as details_preview FROM cases ORDER BY case_number')
    rows = cursor.fetchall()
    
    print('Cases Table Content:')
    print('=' * 100)
    
    for row in rows:
        case_num, status, feedback, preview = row
        feedback_display = feedback if feedback else "(empty)"
        print(f'Case: {case_num}')
        print(f'Status: {status}')
        print(f'Feedback: {feedback_display}')
        print(f'Details Preview: {preview}...')
        print('-' * 100)
    
    print(f'Total cases: {len(rows)}')
    conn.close()

if __name__ == "__main__":
    check_cases()