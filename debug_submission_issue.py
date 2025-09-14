import json
import os

def debug_submission_issue():
    """Debug why automatic submission is failing"""
    
    # Load the actual patient data file
    file_path = r'c:\Users\flyhi\Desktop\CARE_2\care_ai_rohit16\care_app_data\patient_data_5dcf2bd4-0c05-433c-b0d0-b545e0c32452.json'
    
    print("🔍 Debugging automatic submission issue...")
    print(f"📂 Loading patient data from: {file_path}")
    
    with open(file_path, 'r') as f:
        patient_data = json.load(f)
    
    print(f"✅ Patient data loaded successfully")
    print(f"📊 Top-level keys: {list(patient_data.keys())}")
    
    # Check if step7 key exists
    has_step7_key = 'step7' in patient_data
    print(f"🔑 Has 'step7' key: {has_step7_key}")
    
    if has_step7_key:
        print(f"✅ Step7 data found!")
        step7_data = patient_data['step7']
        print(f"📋 Step7 keys: {list(step7_data.keys())}")
        print(f"📋 Step7 data preview: {json.dumps(step7_data, indent=2)[:500]}...")
    else:
        print("❌ No 'step7' key found in patient data!")
        print("🔍 Looking for step7-related data in other locations...")
        
        # Look for data with step7 references
        for key, value in patient_data.items():
            if 'step7' in str(key).lower() or (isinstance(value, dict) and 'step7' in str(value)):
                print(f"📍 Found step7 reference in '{key}': {type(value)}")
        
        # Check the data_summary section
        if 'data_summary' in patient_data:
            data_summary = patient_data['data_summary']
            print(f"📊 Data summary keys: {list(data_summary.keys())}")
            if 'step7' in data_summary:
                print(f"✅ Found step7 in data_summary: {data_summary['step7']}")
        
        # Check if there's a section that contains step7 form data
        # Based on the file structure, it looks like step7 data might be in a different format
        print("\n🔍 Searching for step7 completion data...")
        
        # Look for completed steps info
        if 'step_completed' in patient_data:
            step_completed = patient_data['step_completed']
            print(f"📈 Step completed: {step_completed}")
        
        # Look for the actual step7 completion data (should be around line 250)
        # This seems to be where the contact info and completion data is stored
        print("\n🔍 Looking for contact info and completion data (this might be the step7 data)...")
        
        # Search through all nested structures for contact info
        def find_contact_info(data, path=""):
            """Recursively search for contact information"""
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    if 'contact' in str(key).lower() or 'email' in str(key).lower() or 'phone' in str(key).lower():
                        print(f"📧 Found contact-related field at '{current_path}': {key} = {value}")
                    if isinstance(value, (dict, list)):
                        find_contact_info(value, current_path)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    current_path = f"{path}[{i}]"
                    if isinstance(item, (dict, list)):
                        find_contact_info(item, current_path)
        
        find_contact_info(patient_data)

    print("\n" + "="*50)
    print("🎯 CONCLUSION:")
    print("="*50)
    
    if has_step7_key:
        print("✅ The patient data HAS a 'step7' key")
        print("✅ Automatic submission should work")
    else:
        print("❌ The patient data DOES NOT have a 'step7' key")
        print("❌ This is why automatic submission is failing!")
        print("🔧 The step7 data appears to be stored in a different structure")
        print("🔧 The submission code needs to be updated to look in the right place")

if __name__ == "__main__":
    debug_submission_issue()