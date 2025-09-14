#!/usr/bin/env python3
import sqlite3

def test_automatic_submission():
    """Test if automatic submission is working properly"""
    print("🧪 Testing Automatic Case Submission Logic")
    print("=" * 50)
    
    # Check the current submission criteria
    step_status_test = "differential_questioning_completed_with_lab_tests"
    
    should_submit = (
        step_status_test and 
        ('completed' in step_status_test.lower() or 'finished' in step_status_test.lower()) and
        'in_progress' not in step_status_test.lower()
    )
    
    print(f"Step status: {step_status_test}")
    print(f"Should submit: {should_submit}")
    print()
    
    # Check for duplicate detection
    conn = sqlite3.connect('care_ai_cases.db')
    cursor = conn.cursor()
    
    session_id = '2025-09-14T19:39:26.429766'
    patient_email = 'bb@gmail.com'
    
    print("Checking duplicate detection logic...")
    
    # This is the same query used in the app
    cursor.execute("""
        SELECT case_number FROM cases 
        WHERE details LIKE ? 
        AND details LIKE ?
        ORDER BY case_number DESC 
        LIMIT 1
    """, (f'%"patient_email": "{patient_email}"%', f'%"session_id": "{session_id}"%'))
    
    existing_case = cursor.fetchone()
    
    if existing_case:
        print(f"❌ Duplicate detection would BLOCK submission")
        print(f"   Found existing case: {existing_case[0]}")
        print(f"   This explains why your case wasn't auto-submitted!")
    else:
        print(f"✅ No duplicates found - submission should proceed")
    
    print("\n" + "=" * 50)
    print("CONCLUSION:")
    if should_submit and not existing_case:
        print("✅ Automatic submission SHOULD work for new medical operator cases")
    elif not should_submit:
        print("❌ Step status logic prevents submission")
    elif existing_case:
        print("❌ Duplicate detection prevents submission")
        print("   This case was already submitted as:", existing_case[0])
    
    conn.close()

if __name__ == "__main__":
    test_automatic_submission()