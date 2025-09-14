#!/usr/bin/env python3
"""
Test case submission for the most recent patient data
"""

import sys
import os
import json
import sqlite3
from datetime import datetime

# Add the main directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_case_submission():
    """Test case submission using the latest patient data"""
    print("🧪 Testing Case Submission")
    print("=" * 50)
    
    try:
        # Import from app_new.py
        from app_new import generate_case_number, get_sqlite_connection, load_patient_data, get_referring_doctor_by_id
        
        # Load the latest patient data
        print("📁 Loading patient data...")
        patient_data = load_patient_data()
        
        if not patient_data:
            print("❌ No patient data found")
            return False
            
        # Check step7 data
        step7_data = patient_data.get('step7', {})
        if not step7_data:
            print("❌ No step7 data found")
            return False
            
        print(f"✅ Patient data loaded for session: {patient_data.get('session_id', 'unknown')}")
        
        # Check if step7 is completed
        if not step7_data.get('step_completed', False):
            print("⚠️ Step 7 not marked as completed")
        
        # Extract patient contact info
        form_data = step7_data.get('form_data', {})
        patient_contact = {
            'email': form_data.get('patient_email', ''),
            'phone': form_data.get('patient_phone', ''),
            'referring_doctor_id': form_data.get('referring_doctor_id', ''),
            'referring_doctor_name': form_data.get('referring_doctor_name', ''),
            'referring_doctor_email': form_data.get('referring_doctor_email', '')
        }
        
        print(f"📧 Patient email: {patient_contact['email']}")
        print(f"📞 Patient phone: {patient_contact['phone']}")
        print(f"👩‍⚕️ Referring doctor: {patient_contact['referring_doctor_name']}")
        print(f"📧 Doctor email: {patient_contact['referring_doctor_email']}")
        
        if not patient_contact['email'] or not patient_contact['phone']:
            print("❌ Missing patient contact information")
            return False
            
        # Generate case number
        case_number = generate_case_number()
        print(f"📋 Generated case number: {case_number}")
        
        # Prepare case data for database
        case_data = {
            'patient_info': {
                'name': patient_data.get('step1', {}).get('form_data', {}).get('full_name', 'Unknown'),
                'email': patient_contact['email'],
                'phone': patient_contact['phone']
            },
            'referring_doctor': {
                'id': patient_contact['referring_doctor_id'],
                'name': patient_contact['referring_doctor_name'],
                'email': patient_contact['referring_doctor_email']
            },
            'clinical_data': {
                'icd_codes': step7_data.get('ai_generated_data', {}).get('icd_codes_generated', []),
                'lab_tests': step7_data.get('ai_generated_data', {}).get('recommended_lab_tests', []),
                'clinical_summary': step7_data.get('form_data', {}).get('clinical_summary_edited', ''),
                'completion_timestamp': datetime.now().isoformat()
            },
            'submission_info': {
                'step7_completed': True,
                'submission_timestamp': datetime.now().isoformat(),
                'system_generated': True
            }
        }
        
        # Insert into SQLite database
        connection = get_sqlite_connection()
        if not connection:
            print("❌ Could not connect to SQLite database")
            return False
            
        cursor = connection.cursor()
        
        insert_query = """
            INSERT INTO cases (case_number, details, status, feedback) 
            VALUES (?, ?, ?, ?)
        """
        
        cursor.execute(insert_query, (
            case_number,
            json.dumps(case_data, indent=2),
            'pending_review',
            ''
        ))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print(f"✅ Case {case_number} submitted successfully!")
        print(f"📊 Status: pending_review")
        print(f"👤 Patient: {case_data['patient_info']['name']}")
        print(f"📧 Patient email: {case_data['patient_info']['email']}")
        print(f"👩‍⚕️ Doctor: {case_data['referring_doctor']['name']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in case submission: {e}")
        return False

if __name__ == "__main__":
    success = test_case_submission()
    if success:
        print("\n💡 Case submission successful! Check the database with: python view_cases.py")
    else:
        print("\n⚠️ Case submission failed. Check the logs above for details.")