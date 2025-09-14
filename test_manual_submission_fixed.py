import json
import sqlite3
import uuid
from datetime import datetime

def test_manual_submission_fixed():
    """Test manual submission with fixed case number generation"""
    
    print("🔄 Testing manual case submission (FIXED)...")
    
    # Load the patient data
    file_path = r'c:\Users\flyhi\Desktop\CARE_2\care_ai_rohit16\care_app_data\patient_data_5dcf2bd4-0c05-433c-b0d0-b545e0c32452.json'
    
    with open(file_path, 'r') as f:
        patient_data = json.load(f)
    
    # Get step7 data
    step7_data = patient_data.get('step7')
    if not step7_data:
        print("❌ No step7 data found")
        return
    
    print("✅ Step7 data found")
    
    # Check step status
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
    
    # Check for duplicates
    session_id = patient_data.get('session_id')
    patient_email = form_data.get('patient_email', '')
    
    print(f"🆔 Session ID: {session_id}")
    print(f"📧 Patient Email: {patient_email}")
    
    try:
        # Database connection
        db_path = 'care_ai_cases.db'
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Check for duplicates
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
        
        # FIXED: Generate case number correctly
        def generate_case_number_fixed():
            """Generate unique case number (FIXED VERSION)"""
            current_year = datetime.now().year
            
            # Get all numeric case numbers for this year
            cursor.execute("""
                SELECT case_number FROM cases 
                WHERE case_number LIKE ? 
                AND case_number REGEXP 'CASE-[0-9]+-[0-9]+$'
                ORDER BY case_number DESC
            """, (f'CASE-{current_year}-%',))
            
            results = cursor.fetchall()
            print(f"📊 Found {len(results)} existing numeric cases for {current_year}")
            
            max_number = 0
            for result in results:
                case_number = result[0]
                try:
                    # Extract the number part after the last dash
                    number_part = case_number.split('-')[-1]
                    if number_part.isdigit():
                        number = int(number_part)
                        max_number = max(max_number, number)
                        print(f"   📋 {case_number} -> number: {number}")
                except:
                    print(f"   ⚠️ Could not parse: {case_number}")
            
            next_number = max_number + 1
            new_case_number = f"CASE-{current_year}-{next_number:04d}"
            print(f"🎯 Next case number: {new_case_number}")
            return new_case_number
        
        case_number = generate_case_number_fixed()
        print(f"📋 Generated case number: {case_number}")
        
        # Prepare step7 data as JSON
        step7_json_data = json.dumps(step7_data, indent=2, default=str)
        
        print(f"📄 JSON data length: {len(step7_json_data)} characters")
        
        # Insert into database
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
    test_manual_submission_fixed()