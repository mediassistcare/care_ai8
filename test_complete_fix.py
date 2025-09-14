import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import sqlite3
import json
from app_new import build_patient_summary_fallback

def test_complete_extraction_fix():
    """Test the complete extraction fix including patient summary fallback"""
    
    case_number = 'CASE-2025-0004'
    print(f"🔧 Testing complete extraction fix for: {case_number}")
    
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
        
        # Test the patient summary with fallback
        patient_summary = (
            case_details.get('ai_generated_data', {}).get('patient_data_summary') or 
            build_patient_summary_fallback(case_details) or
            'Patient summary not available - please review individual sections'
        )
        
        print(f"\n📄 CLINICAL SUMMARY RESULT:")
        if clinical_summary == 'No clinical summary available':
            print(f"   ❌ Still empty")
        else:
            print(f"   ✅ SUCCESS ({len(clinical_summary)} chars)")
            print(f"   📝 Preview: {clinical_summary[:200]}...")
        
        print(f"\n👤 PATIENT SUMMARY RESULT:")
        if patient_summary == 'Patient summary not available - please review individual sections':
            print(f"   ❌ Still empty")
        else:
            print(f"   ✅ SUCCESS ({len(patient_summary)} chars)")
            print(f"   📝 Content:")
            for line in patient_summary.split('\\n'):
                print(f"      {line}")
        
        print(f"\n🎯 FINAL ASSESSMENT:")
        if (clinical_summary != 'No clinical summary available' and 
            patient_summary != 'Patient summary not available - please review individual sections'):
            print("✅ BOTH clinical and patient summaries will now display in panelist view!")
            print("🎉 Issue RESOLVED!")
        elif clinical_summary != 'No clinical summary available':
            print("✅ Clinical summary fixed")
            if patient_summary == 'Patient summary not available - please review individual sections':
                print("⚠️ Patient summary still needs work")
        else:
            print("❌ Still have issues to resolve")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_complete_extraction_fix()