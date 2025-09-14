import json
import os

def debug_step_status():
    """Debug the exact step_status and submission criteria"""
    
    # Load the actual patient data file
    file_path = r'c:\Users\flyhi\Desktop\CARE_2\care_ai_rohit16\care_app_data\patient_data_5dcf2bd4-0c05-433c-b0d0-b545e0c32452.json'
    
    print("🔍 Debugging step_status and submission criteria...")
    print(f"📂 Loading patient data from: {file_path}")
    
    with open(file_path, 'r') as f:
        patient_data = json.load(f)
    
    step7_data = patient_data['step7']
    form_data = step7_data.get('form_data', {})
    
    print("📋 STEP7 FORM DATA:")
    for key, value in form_data.items():
        print(f"   {key}: {value}")
    
    # Get the step_status
    step_status = form_data.get('step_status', 'NOT_FOUND')
    print(f"\n🎯 STEP STATUS: '{step_status}'")
    
    # Check submission criteria from the app code
    print(f"\n🔍 CHECKING SUBMISSION CRITERIA:")
    print(f"📊 step_status value: '{step_status}'")
    
    # Simulate the submission criteria check
    should_submit_case = (
        step_status and 
        ('completed' in step_status.lower() or 'finished' in step_status.lower()) and
        'in_progress' not in step_status.lower()
    )
    
    print(f"🔄 Should submit case: {should_submit_case}")
    
    # Break down the criteria
    print(f"\n📋 CRITERIA BREAKDOWN:")
    print(f"   ✅ step_status exists: {bool(step_status)}")
    print(f"   ✅ Contains 'completed': {'completed' in step_status.lower() if step_status else False}")
    print(f"   ✅ Contains 'finished': {'finished' in step_status.lower() if step_status else False}")
    print(f"   ✅ Does NOT contain 'in_progress': {'in_progress' not in step_status.lower() if step_status else False}")
    
    # Check for patient email (required for duplicate check)
    patient_email = form_data.get('patient_email', 'NOT_FOUND')
    print(f"\n📧 Patient email: '{patient_email}'")
    
    # Check session_id
    session_id = patient_data.get('session_id', 'NOT_FOUND')
    print(f"🆔 Session ID: '{session_id}'")
    
    print(f"\n" + "="*50)
    print("🎯 SUBMISSION ANALYSIS:")
    print("="*50)
    
    if should_submit_case:
        print("✅ Submission criteria ARE met")
        print("✅ Case SHOULD be automatically submitted")
        print("❓ If it's not submitting, there might be a different issue:")
        print("   • Database connection problem")
        print("   • Exception being caught silently") 
        print("   • Duplicate case already exists")
        print("   • Route not being called correctly")
    else:
        print("❌ Submission criteria are NOT met")
        print(f"❌ Case will NOT be automatically submitted")
        print(f"🔧 The step_status '{step_status}' doesn't meet submission criteria")

if __name__ == "__main__":
    debug_step_status()