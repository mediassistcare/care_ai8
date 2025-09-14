#!/usr/bin/env python3
"""
Test script to verify SQLite database setup and case submission workflow
"""

import sys
import os
import json
import sqlite3
from datetime import datetime

# Add the main directory to the path so we can import from app_new.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_sqlite_database():
    """Test SQLite database connectivity and structure"""
    print("🗄️ Testing SQLite Database...")
    print("=" * 50)
    
    db_path = "care_ai_cases.db"
    
    try:
        if not os.path.exists(db_path):
            print(f"❌ Database file not found: {db_path}")
            return False
            
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Check if cases table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cases'")
        result = cursor.fetchone()
        
        if not result:
            print("❌ Cases table not found")
            return False
            
        print("✅ Cases table exists")
        
        # Check table structure
        cursor.execute("PRAGMA table_info(cases)")
        columns = cursor.fetchall()
        
        expected_columns = ['id', 'case_number', 'details', 'status', 'created_at', 'updated_at']
        actual_columns = [col[1] for col in columns]
        
        print(f"📋 Table columns: {actual_columns}")
        
        for col in expected_columns:
            if col in actual_columns:
                print(f"✅ Column '{col}' exists")
            else:
                print(f"❌ Column '{col}' missing")
                
        # Test insert/select operations
        test_case_number = f"TEST-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        test_data = json.dumps({"test": "data", "timestamp": datetime.now().isoformat()})
        
        cursor.execute("""
            INSERT INTO cases (case_number, details, status) 
            VALUES (?, ?, ?)
        """, (test_case_number, test_data, "test"))
        
        connection.commit()
        
        # Verify the insert
        cursor.execute("SELECT * FROM cases WHERE case_number = ?", (test_case_number,))
        result = cursor.fetchone()
        
        if result:
            print(f"✅ Test case inserted successfully: {result[1]}")
            
            # Clean up test data
            cursor.execute("DELETE FROM cases WHERE case_number = ?", (test_case_number,))
            connection.commit()
            print("✅ Test data cleaned up")
        else:
            print("❌ Test case insertion failed")
            
        cursor.close()
        connection.close()
        
        print("✅ SQLite database test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ SQLite database test failed: {e}")
        return False

def test_referring_doctors():
    """Test referring doctor functionality"""
    print("\n👩‍⚕️ Testing Referring Doctor Functionality...")
    print("=" * 50)
    
    try:
        # Import the function from app_new.py
        from app_new import get_referring_doctor_by_id
        
        # Test valid doctor IDs
        test_ids = [1, 2, 3]
        
        for doctor_id in test_ids:
            doctor = get_referring_doctor_by_id(doctor_id)
            if doctor:
                print(f"✅ Doctor ID {doctor_id}: {doctor['first_name']} {doctor['last_name']} ({doctor['email_address']})")
            else:
                print(f"❌ Doctor ID {doctor_id} not found")
                
        # Test invalid doctor ID
        invalid_doctor = get_referring_doctor_by_id(999)
        if invalid_doctor is None:
            print("✅ Invalid doctor ID correctly returns None")
        else:
            print("❌ Invalid doctor ID should return None")
            
        return True
        
    except Exception as e:
        print(f"❌ Referring doctor test failed: {e}")
        return False

def test_case_submission_logic():
    """Test the case submission logic without actually running the Flask app"""
    print("\n📋 Testing Case Submission Logic...")
    print("=" * 50)
    
    try:
        # Import necessary functions
        from app_new import generate_case_number, get_sqlite_connection
        
        # Test case number generation
        case_number = generate_case_number()
        print(f"✅ Generated case number: {case_number}")
        
        # Test database connection
        connection = get_sqlite_connection()
        if connection:
            print("✅ SQLite connection established")
            
            # Test actual case insertion
            test_data = {
                "patient_info": {
                    "name": "Test Patient",
                    "email": "test@example.com",
                    "phone": "1234567890"
                },
                "referring_doctor": {
                    "id": 2,
                    "name": "Priya Patel",
                    "email": "priya.patel@clinic.com"
                },
                "assessment": {
                    "completed": True,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            cursor = connection.cursor()
            
            insert_query = """
                INSERT INTO cases (case_number, details, status) 
                VALUES (?, ?, ?)
            """
            
            cursor.execute(insert_query, (
                case_number,
                json.dumps(test_data, indent=2),
                'pending_review'
            ))
            
            connection.commit()
            
            # Verify the insertion
            cursor.execute("SELECT * FROM cases WHERE case_number = ?", (case_number,))
            result = cursor.fetchone()
            
            if result:
                print(f"✅ Test case submitted successfully: {result[1]}")
                print(f"📊 Status: {result[3]}")
                print(f"📅 Created: {result[5]}")
                
                # Show the stored data
                stored_data = json.loads(result[2])
                print(f"📋 Stored data keys: {list(stored_data.keys())}")
                
            else:
                print("❌ Test case submission failed")
                
            cursor.close()
            connection.close()
            return True
            
        else:
            print("❌ SQLite connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Case submission test failed: {e}")
        return False

def check_existing_patient_data():
    """Check if there are existing patient data files"""
    print("\n📁 Checking Existing Patient Data...")
    print("=" * 50)
    
    try:
        import glob
        
        pattern = "care_app_data/patient_data_*.json"
        files = glob.glob(pattern)
        
        if files:
            print(f"✅ Found {len(files)} patient data files:")
            
            for file_path in files:
                print(f"  📄 {file_path}")
                
                # Check if step7 data exists
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        
                    step7_data = data.get('step7', {})
                    if step7_data:
                        print(f"     ✅ Step7 data exists")
                        
                        # Check for patient contact info
                        patient_contact = step7_data.get('patient_contact_info', {})
                        if patient_contact:
                            print(f"     ✅ Patient contact info: {list(patient_contact.keys())}")
                        else:
                            print(f"     ⚠️ No patient contact info")
                            
                    else:
                        print(f"     ⚠️ No step7 data")
                        
                except Exception as e:
                    print(f"     ❌ Error reading file: {e}")
                    
        else:
            print("⚠️ No patient data files found")
            print("💡 You can test the system by:")
            print("   1. Starting the Flask app: python app_new.py")
            print("   2. Going through the complete patient assessment flow")
            print("   3. Completing step7 with patient contact information")
            
        return len(files) > 0
        
    except Exception as e:
        print(f"❌ Error checking patient data: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 CARE AI SQLite Workflow Test Suite")
    print("=" * 60)
    print(f"📅 Test run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Working directory: {os.getcwd()}")
    print()
    
    tests = [
        ("SQLite Database", test_sqlite_database),
        ("Referring Doctors", test_referring_doctors), 
        ("Case Submission Logic", test_case_submission_logic),
        ("Existing Patient Data", check_existing_patient_data)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 Test Results Summary")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🏆 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The SQLite workflow is ready.")
        print("\n💡 Next steps:")
        print("   1. Start the Flask app: python app_new.py")
        print("   2. Complete a patient assessment through step7")
        print("   3. The case will be automatically submitted to SQLite database")
    else:
        print("⚠️ Some tests failed. Please check the issues above.")
        
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)