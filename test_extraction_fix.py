import sqlite3
import json

def test_updated_extraction():
    """Test the updated case data extraction logic"""
    
    case_number = 'CASE-2025-0004'
    print(f"🔧 Testing updated extraction logic for: {case_number}")
    
    try:
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        cursor.execute('SELECT case_number, status, details, created_at FROM cases WHERE case_number = ?', (case_number,))
        case_data = cursor.fetchone()
        conn.close()
        
        if not case_data:
            print(f"❌ Case {case_number} not found")
            return
        
        case_details = json.loads(case_data[2])
        
        # Test the new extraction logic (same as app)
        clinical_summary = (
            case_details.get('ai_generated_data', {}).get('clinical_summary') or 
            case_details.get('form_data', {}).get('clinical_summary_edited') or 
            case_details.get('ai_generated_data', {}).get('original_clinical_summary') or
            'No clinical summary available'
        )
        
        patient_summary = (
            case_details.get('ai_generated_data', {}).get('patient_data_summary') or 
            case_details.get('ai_generated_data', {}).get('patient_data_summary') or
            'Patient summary not available - please review individual sections'
        )
        
        print(f"\n📄 CLINICAL SUMMARY EXTRACTION:")
        if clinical_summary == 'No clinical summary available':
            print(f"   ❌ Still empty after extraction")
        else:
            print(f"   ✅ Successfully extracted ({len(clinical_summary)} chars)")
            print(f"   📝 Preview: {clinical_summary[:150]}...")
        
        print(f"\n👤 PATIENT SUMMARY EXTRACTION:")
        if patient_summary == 'Patient summary not available - please review individual sections':
            print(f"   ❌ Still empty after extraction")
        else:
            print(f"   ✅ Successfully extracted ({len(patient_summary)} chars)")
            print(f"   📝 Preview: {patient_summary[:150]}...")
        
        # Show which data sources are available
        print(f"\n🔍 AVAILABLE DATA SOURCES:")
        ai_clinical = case_details.get('ai_generated_data', {}).get('clinical_summary')
        form_clinical = case_details.get('form_data', {}).get('clinical_summary_edited')
        original_clinical = case_details.get('ai_generated_data', {}).get('original_clinical_summary')
        ai_patient = case_details.get('ai_generated_data', {}).get('patient_data_summary')
        
        print(f"   🤖 AI clinical_summary: {'✅ EXISTS' if ai_clinical else '❌ MISSING'}")
        print(f"   📝 Form clinical_summary_edited: {'✅ EXISTS' if form_clinical else '❌ MISSING'}")
        print(f"   📄 AI original_clinical_summary: {'✅ EXISTS' if original_clinical else '❌ MISSING'}")
        print(f"   👤 AI patient_data_summary: {'✅ EXISTS' if ai_patient else '❌ MISSING'}")
        
        if form_clinical and not ai_clinical:
            print(f"\n✅ SOLUTION: Using form_data.clinical_summary_edited as fallback!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_updated_extraction()