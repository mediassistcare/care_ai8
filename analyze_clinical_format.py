import sqlite3
import json

def check_clinical_summary_format():
    """Check the format of clinical summary to optimize display"""
    
    try:
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        cursor.execute('SELECT details FROM cases WHERE case_number = ?', ('CASE-2025-0004',))
        result = cursor.fetchone()
        
        if result:
            data = json.loads(result[0])
            clinical = data.get('form_data', {}).get('clinical_summary_edited', '')
            
            print("📄 Clinical Summary Analysis:")
            print(f"Total length: {len(clinical)} characters")
            print(f"Number of \\n: {clinical.count(chr(10))}")
            print(f"Number of \\n\\n: {clinical.count(chr(10)+chr(10))}")
            
            print("\\n📝 First 400 characters:")
            print(repr(clinical[:400]))
            
            print("\\n🔍 Structure breakdown:")
            lines = clinical.split('\\n')
            for i, line in enumerate(lines[:15]):  # First 15 lines
                print(f"Line {i+1:2d}: '{line[:60]}{'...' if len(line) > 60 else ''}'")
            
            if len(lines) > 15:
                print(f"... and {len(lines) - 15} more lines")
        
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_clinical_summary_format()