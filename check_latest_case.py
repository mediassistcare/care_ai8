import sqlite3
import json

def check_case_summaries(case_number):
    """Check clinical and patient summary data for a specific case"""
    
    print(f"🔍 Checking case summaries for: {case_number}")
    
    try:
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        cursor.execute('SELECT details FROM cases WHERE case_number = ?', (case_number,))
        result = cursor.fetchone()
        
        if not result:
            print(f"❌ Case {case_number} not found")
            return
        
        data = json.loads(result[0])
        form_data = data.get('form_data', {})
        ai_data = data.get('ai_generated_data', {})
        
        print(f"\n📋 CASE {case_number} DATA ANALYSIS:")
        print("="*60)
        
        # Check clinical summary in form_data
        clinical_summary_edited = form_data.get('clinical_summary_edited', '')
        print(f"📄 Form Data - Clinical Summary Edited:")
        if clinical_summary_edited:
            print(f"   ✅ EXISTS ({len(clinical_summary_edited)} chars)")
            print(f"   📝 Preview: {clinical_summary_edited[:200]}...")
        else:
            print(f"   ❌ MISSING or EMPTY")
        
        print()
        
        # Check AI clinical summary
        ai_clinical_summary = ai_data.get('clinical_summary', '')
        print(f"🤖 AI Data - Clinical Summary:")
        if ai_clinical_summary:
            print(f"   ✅ EXISTS ({len(ai_clinical_summary)} chars)")
            print(f"   📝 Preview: {ai_clinical_summary[:200]}...")
        else:
            print(f"   ❌ MISSING or EMPTY")
        
        print()
        
        # Check AI patient data summary
        patient_data_summary = ai_data.get('patient_data_summary', '')
        print(f"👤 AI Data - Patient Data Summary:")
        if patient_data_summary:
            print(f"   ✅ EXISTS ({len(patient_data_summary)} chars)")
            print(f"   📝 Preview: {patient_data_summary[:200]}...")
        else:
            print(f"   ❌ MISSING or EMPTY")
        
        print()
        
        # Check other important fields that might be displayed
        print(f"🔍 OTHER IMPORTANT FIELDS:")
        
        # Original clinical summary
        original_summary = ai_data.get('original_clinical_summary', '')
        print(f"   📄 Original Clinical Summary: {'✅ EXISTS' if original_summary else '❌ MISSING'} ({len(original_summary)} chars)")
        
        # ICD codes
        icd_codes = ai_data.get('icd_codes_generated', [])
        print(f"   🏥 ICD Codes Generated: {'✅ EXISTS' if icd_codes else '❌ MISSING'} ({len(icd_codes)} codes)")
        
        # Lab tests
        lab_tests = ai_data.get('diagnostic_tests_recommended', [])
        print(f"   🔬 Diagnostic Tests: {'✅ EXISTS' if lab_tests else '❌ MISSING'} ({len(lab_tests)} tests)")
        
        # System analysis
        system_analysis = ai_data.get('system_analysis', {})
        print(f"   📊 System Analysis: {'✅ EXISTS' if system_analysis else '❌ MISSING'}")
        
        conn.close()
        
        print(f"\n🎯 SUMMARY:")
        if not clinical_summary_edited and not ai_clinical_summary:
            print("❌ No clinical summary data found - this will show as empty in panelist view")
        
        if not patient_data_summary:
            print("❌ No patient data summary found - this will show as empty in panelist view")
            
        if clinical_summary_edited or ai_clinical_summary or patient_data_summary:
            print("✅ Some summary data exists - checking template extraction logic")
        
    except Exception as e:
        print(f"❌ Error checking case: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_case_summaries('CASE-2025-0004')