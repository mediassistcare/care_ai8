import sqlite3
import json

def check_for_existing_case():
    """Check if there's already a case for this patient/session"""
    
    # Database connection
    db_path = 'care_ai_cases.db'
    
    # Patient details from the failed submission
    patient_email = 'hhh@gmail.com'
    session_id = '2025-09-14T19:56:10.716024'
    
    print(f"🔍 Checking for existing cases...")
    print(f"📧 Patient Email: {patient_email}")
    print(f"🆔 Session ID: {session_id}")
    
    try:
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Search for existing case with same patient email
        cursor.execute("""
            SELECT case_number, details FROM cases 
            WHERE details LIKE ?
        """, (f'%"patient_email": "{patient_email}"%',))
        
        email_matches = cursor.fetchall()
        
        print(f"\n📧 Cases with email '{patient_email}': {len(email_matches)}")
        for case_number, details in email_matches:
            print(f"   📋 Case: {case_number}")
            # Parse the details to check session_id
            try:
                details_json = json.loads(details)
                case_session_id = details_json.get('session_id', 'NOT_FOUND')
                print(f"   🆔 Session ID: {case_session_id}")
                if case_session_id == session_id:
                    print(f"   ✅ EXACT MATCH found for session!")
                else:
                    print(f"   ❌ Different session")
            except:
                print(f"   ❌ Could not parse details JSON")
        
        # Search for existing case with same session_id
        cursor.execute("""
            SELECT case_number, details FROM cases 
            WHERE details LIKE ?
        """, (f'%"session_id": "{session_id}"%',))
        
        session_matches = cursor.fetchall()
        
        print(f"\n🆔 Cases with session_id '{session_id}': {len(session_matches)}")
        for case_number, details in session_matches:
            print(f"   📋 Case: {case_number}")
        
        # If we found matches, show why the duplicate check triggered
        if email_matches or session_matches:
            print(f"\n⚠️ DUPLICATE DETECTED!")
            print(f"📧 Email matches: {len(email_matches)}")
            print(f"🆔 Session matches: {len(session_matches)}")
            print(f"🔧 This is why automatic submission was skipped!")
        else:
            print(f"\n✅ No duplicates found")
            print(f"❓ Submission should have worked - there's another issue!")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")

if __name__ == "__main__":
    check_for_existing_case()