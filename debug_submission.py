#!/usr/bin/env python3
import json
import sqlite3
import sys
import os

# Add the main directory to path so we can import from app_new.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_submission_with_new_case():
    """Test the submission logic with the new case that failed to submit"""
    try:
        # Import functions from app_new.py
        from app_new import generate_case_number, get_sqlite_connection
        
        print("🧪 Testing Case Submission with New Data")
        print("=" * 50)
        
        # Load the patient data that should have been submitted
        filepath = 'care_app_data/patient_data_5dcf2bd4-0c05-433c-b0d0-b545e0c32452.json'
        
        with open(filepath, 'r') as f:
            patient_data = json.load(f)
        
        step7_data = patient_data.get('step7')
        if not step7_data:
            print("❌ No step7 data found")
            return
            
        form_data = step7_data.get('form_data', {})
        
        # Test the submission criteria
        step_status = form_data.get('step_status', '')
        should_submit = (
            step_status and 
            ('completed' in step_status.lower() or 'finished' in step_status.lower()) and
            'in_progress' not in step_status.lower()
        )
        
        print(f"Step status: {step_status}")
        print(f"Should submit: {should_submit}")
        
        if should_submit:
            # Test duplicate check
            session_id = patient_data.get('session_id')
            patient_email = form_data.get('patient_email', '')
            
            print(f"Session ID: {session_id}")
            print(f"Patient email: {patient_email}")
            
            connection = get_sqlite_connection()
            if connection:
                cursor = connection.cursor()
                
                # Check for existing case
                cursor.execute("""
                    SELECT case_number FROM cases 
                    WHERE details LIKE ? 
                    AND details LIKE ?
                    ORDER BY case_number DESC 
                    LIMIT 1
                """, (f'%"patient_email": "{patient_email}"%', f'%"session_id": "{session_id}"%'))
                
                existing_case = cursor.fetchone()
                
                if existing_case:
                    print(f"❌ Duplicate found: {existing_case[0]} (would block submission)")
                else:
                    print("✅ No duplicates found")
                    
                    # Test case number generation
                    try:
                        case_number = generate_case_number()
                        print(f"✅ Case number generated: {case_number}")
                        
                        # Test JSON serialization
                        try:
                            step7_json = json.dumps(step7_data, indent=2, default=str)
                            print(f"✅ JSON serialization successful: {len(step7_json)} chars")
                            
                            # Test database insert (but don't actually insert)
                            print("✅ All tests passed - submission should work!")
                            
                        except Exception as json_error:
                            print(f"❌ JSON serialization failed: {json_error}")
                            
                    except Exception as case_num_error:
                        print(f"❌ Case number generation failed: {case_num_error}")
                
                cursor.close()
                connection.close()
                
            else:
                print("❌ Database connection failed")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_submission_with_new_case()