#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime

def submit_missing_case():
    """Manually submit the missing case to the database"""
    try:
        # Load the patient data
        with open('care_app_data/patient_data_7447df6e-6643-429f-818f-fff98aae61e4.json', 'r') as f:
            patient_data = json.load(f)
        
        step7_data = patient_data['step7']
        
        # Generate case number (simple increment)
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT case_number FROM cases WHERE case_number LIKE 'CASE-2025-%' ORDER BY case_number DESC")
        all_cases = cursor.fetchall()
        
        # Find the highest numeric case number
        max_num = 0
        for case in all_cases:
            case_num = case[0]
            try:
                # Extract number from cases like CASE-2025-0001
                if case_num.count('-') >= 2:
                    num_part = case_num.split('-')[-1]
                    if num_part.isdigit():
                        max_num = max(max_num, int(num_part))
            except:
                continue
        
        case_number = f"CASE-2025-{max_num + 1:04d}"
        
        print(f"Generated case number: {case_number}")
        
        # Prepare step7 data as JSON
        step7_json = json.dumps(step7_data, indent=2, default=str)
        
        # Insert into database
        cursor.execute("""
            INSERT INTO cases (case_number, details, status, feedback) 
            VALUES (?, ?, ?, ?)
        """, (case_number, step7_json, 'pending_review', ''))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Successfully submitted case: {case_number}")
        
        # Verify submission
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cases")
        count = cursor.fetchone()[0]
        print(f"Total cases now: {count}")
        
        cursor.execute("SELECT case_number, status FROM cases ORDER BY case_number DESC LIMIT 3")
        recent_cases = cursor.fetchall()
        print("Recent cases:")
        for case_num, status in recent_cases:
            print(f"  - {case_num}: {status}")
        
        conn.close()
        
    except Exception as e:
        print(f"Error submitting case: {e}")

if __name__ == "__main__":
    submit_missing_case()