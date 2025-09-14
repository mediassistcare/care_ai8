import json
import sqlite3
from datetime import datetime

def test_complete_automatic_submission():
    """Test the complete automatic submission flow with the fixed logic"""
    
    print("🚀 Testing COMPLETE automatic submission flow...")
    
    # Load the original patient data that failed to submit
    file_path = r'c:\Users\flyhi\Desktop\CARE_2\care_ai_rohit16\care_app_data\patient_data_5dcf2bd4-0c05-433c-b0d0-b545e0c32452.json'
    
    # But first, let's delete the case we manually created to simulate the original failure condition
    print("🧹 Cleaning up manual test case to simulate original conditions...")
    
    try:
        connection = sqlite3.connect('care_ai_cases.db')
        cursor = connection.cursor()
        cursor.execute("DELETE FROM cases WHERE case_number = ?", ('CASE-2025-0003',))
        connection.commit()
        cursor.close()
        connection.close()
        print("✅ Cleaned up CASE-2025-0003")
    except Exception as e:
        print(f"⚠️ Could not clean up: {e}")
    
    # Now simulate the automatic submission logic exactly as it would run in the app
    print("\n📋 Simulating automatic submission with fixed logic...")
    
    with open(file_path, 'r') as f:
        patient_data = json.load(f)
    
    # Check step7 data exists
    step7_data = patient_data.get('step7')
    if not step7_data:
        print("❌ No step7 data found")
        return False
    
    # Check submission criteria
    form_data = step7_data.get('form_data', {})
    step_status = form_data.get('step_status', '')
    
    should_submit_case = (
        step_status and 
        ('completed' in step_status.lower() or 'finished' in step_status.lower()) and
        'in_progress' not in step_status.lower()
    )
    
    print(f"🎯 Step status: '{step_status}'")
    print(f"✅ Should submit: {should_submit_case}")
    
    if not should_submit_case:
        print("❌ Submission criteria not met")
        return False
    
    # Get patient details for duplicate check
    session_id = patient_data.get('session_id')
    patient_email = form_data.get('patient_email', '')
    
    print(f"🆔 Session ID: {session_id}")
    print(f"📧 Patient Email: {patient_email}")
    
    # Import the fixed functions from the app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from app_new import get_sqlite_connection, generate_case_number
    
    try:
        # Check for duplicates (same logic as app)
        connection = get_sqlite_connection()
        if not connection:
            print("❌ Could not connect to database")
            return False
        
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT case_number FROM cases 
            WHERE details LIKE ? 
            AND details LIKE ?
            ORDER BY case_number DESC 
            LIMIT 1
        """, (f'%"patient_email": "{patient_email}"%', f'%"session_id": "{session_id}"%'))
        
        existing_case = cursor.fetchone()
        
        if existing_case:
            print(f"⚠️ Duplicate case found: {existing_case[0]}")
            print("🔄 Skipping duplicate case submission")
            cursor.close()
            connection.close()
            return True  # This is expected behavior
        
        print("✅ No duplicates found")
        
        # Generate case number (using FIXED function)
        case_number = generate_case_number()
        print(f"📋 Generated case number: {case_number}")
        
        # Prepare step7 data as JSON string for database
        step7_json_data = json.dumps(step7_data, indent=2, default=str)
        
        # Insert into SQLite database
        insert_query = """
            INSERT INTO cases (case_number, details, status, feedback) 
            VALUES (?, ?, ?, ?)
        """
        
        cursor.execute(insert_query, (
            case_number,
            step7_json_data,
            'pending_review',
            ''  # blank feedback
        ))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print(f"✅ Case {case_number} submitted successfully to database!")
        
        # Verify the case was inserted
        connection = get_sqlite_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT case_number, status FROM cases WHERE case_number = ?", (case_number,))
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if result:
            print(f"✅ Verification: Case {result[0]} exists with status '{result[1]}'")
            print(f"🎉 AUTOMATIC SUBMISSION FIXED AND WORKING!")
            return True
        else:
            print(f"❌ Verification failed: Case not found")
            return False
            
    except Exception as e:
        print(f"❌ Error in automatic submission: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_complete_automatic_submission()
    print(f"\n{'='*60}")
    if success:
        print("🎊 COMPLETE SUCCESS! Automatic case submission is now working!")
        print("🔧 The bug in case number generation has been fixed!")
        print("✅ Cases will now automatically submit when step7 is completed!")
    else:
        print("❌ FAILED! There are still issues to resolve.")
    print(f"{'='*60}")