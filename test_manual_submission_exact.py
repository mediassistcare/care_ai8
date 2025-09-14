import json
import sqlite3
import uuid
from datetime import datetime

def test_manual_submission():
    """Test manual submission using the exact same logic as the app"""
    
    print("🔄 Testing manual case submission...")
    
    # Load the patient data
    file_path = r'c:\Users\flyhi\Desktop\CARE_2\care_ai_rohit16\care_app_data\patient_data_5dcf2bd4-0c05-433c-b0d0-b545e0c32452.json'
    
    with open(file_path, 'r') as f:
        patient_data = json.load(f)
    
    # Get step7 data (same as app logic)
    step7_data = patient_data.get('step7')
    if not step7_data:
        print("❌ No step7 data found")
        return
    
    print("✅ Step7 data found")
    
    # Check step status (same criteria as app)
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
        return
    
    # Check for duplicates (same logic as app)
    session_id = patient_data.get('session_id')
    patient_email = form_data.get('patient_email', '')
    
    print(f"🆔 Session ID: {session_id}")
    print(f"📧 Patient Email: {patient_email}")
    
    try:
        # Database connection (same as app)
        db_path = 'care_ai_cases.db'
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Check for duplicates (same query as app)
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
            cursor.close()
            connection.close()
            return
        
        print("✅ No duplicates found")
        
        # Generate case number (same logic as app)
        def generate_case_number():
            """Generate unique case number"""
            # Get current year
            current_year = datetime.now().year
            
            # Get next case number for this year
            cursor.execute("""
                SELECT case_number FROM cases 
                WHERE case_number LIKE ? 
                ORDER BY case_number DESC 
                LIMIT 1
            """, (f'CASE-{current_year}-%',))
            
            result = cursor.fetchone()
            if result:
                # Extract number from last case
                last_case = result[0]
                try:
                    last_number = int(last_case.split('-')[-1])
                    next_number = last_number + 1
                except:
                    next_number = 1
            else:
                next_number = 1
            
            return f"CASE-{current_year}-{next_number:04d}"
        
        case_number = generate_case_number()
        print(f"📋 Generated case number: {case_number}")
        
        # Prepare step7 data as JSON (same as app)
        step7_json_data = json.dumps(step7_data, indent=2, default=str)
        
        print(f"📄 JSON data length: {len(step7_json_data)} characters")
        
        # Insert into database (same query as app)
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
        
        print(f"✅ Case {case_number} submitted successfully!")
        print(f"🎉 Manual submission WORKED!")
        
        # Verify the case was inserted
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        cursor.execute("SELECT case_number, status FROM cases WHERE case_number = ?", (case_number,))
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if result:
            print(f"✅ Verification: Case {result[0]} exists with status '{result[1]}'")
        else:
            print(f"❌ Verification failed: Case not found")
        
    except Exception as e:
        print(f"❌ Error in manual submission: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_manual_submission()