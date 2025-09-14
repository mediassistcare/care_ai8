#!/usr/bin/env python3
"""
Quick script to view SQLite database contents
"""

import sqlite3
import json
from datetime import datetime

def view_cases():
    """View all cases in the SQLite database"""
    print("🗄️ CARE AI Cases Database Contents")
    print("=" * 50)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        connection = sqlite3.connect('care_ai_cases.db')
        cursor = connection.cursor()
        
        # Get all cases
        cursor.execute("SELECT id, case_number, details, status, created_at, updated_at FROM cases ORDER BY created_at DESC")
        cases = cursor.fetchall()
        
        if not cases:
            print("📭 No cases found in database")
            print()
            print("💡 To add cases:")
            print("   1. Start the Flask app: python app_new.py")
            print("   2. Complete step7 with patient contact information")
            print("   3. Cases will be automatically submitted")
            return
            
        print(f"📊 Found {len(cases)} case(s):")
        print()
        
        for i, case in enumerate(cases, 1):
            case_id, case_number, details, status, created_at, updated_at = case
            
            print(f"📋 Case #{i}")
            print(f"   🆔 ID: {case_id}")
            print(f"   📧 Case Number: {case_number}")
            print(f"   📊 Status: {status}")
            print(f"   📅 Created: {created_at}")
            
            # Parse and display details
            try:
                case_details = json.loads(details)
                print(f"   📋 Details:")
                
                # Show patient info if available
                if 'patient_info' in case_details:
                    patient = case_details['patient_info']
                    print(f"      👤 Patient: {patient.get('name', 'N/A')}")
                    print(f"      📧 Email: {patient.get('email', 'N/A')}")
                    print(f"      📞 Phone: {patient.get('phone', 'N/A')}")
                
                # Show referring doctor if available
                if 'referring_doctor' in case_details:
                    doctor = case_details['referring_doctor']
                    print(f"      👩‍⚕️ Doctor: {doctor.get('name', 'N/A')}")
                    print(f"      📧 Doctor Email: {doctor.get('email', 'N/A')}")
                
                # Show other important fields
                if 'patient_contact_info' in case_details:
                    contact = case_details['patient_contact_info']
                    print(f"      📱 Contact Info: {list(contact.keys())}")
                    
                # Show step completion
                if 'step_completed' in case_details:
                    print(f"      ✅ Step Completed: {case_details['step_completed']}")
                    
            except json.JSONDecodeError:
                print(f"   ⚠️ Details: (JSON parse error)")
                
            print()
            
        cursor.close()
        connection.close()
        
        print("💡 To manage cases:")
        print("   - View this script: python view_cases.py")
        print("   - Admin portal: Access via Flask app admin interface")
        
    except Exception as e:
        print(f"❌ Error viewing cases: {e}")

if __name__ == "__main__":
    view_cases()