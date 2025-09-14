import sqlite3
import json

def build_patient_summary_fallback():
    """Build a patient summary from available data when AI summary is missing"""
    
    case_number = 'CASE-2025-0004'
    print(f"🔧 Building patient summary fallback for: {case_number}")
    
    try:
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        cursor.execute('SELECT details FROM cases WHERE case_number = ?', (case_number,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            print(f"❌ Case {case_number} not found")
            return
        
        case_details = json.loads(result[0])
        
        # Look for patient data in form_data and other sections
        form_data = case_details.get('form_data', {})
        
        print(f"🔍 AVAILABLE PATIENT DATA:")
        
        # Basic patient info
        patient_email = form_data.get('patient_email', 'Not provided')
        patient_phone = form_data.get('patient_phone', 'Not provided')
        print(f"   📧 Email: {patient_email}")
        print(f"   📞 Phone: {patient_phone}")
        
        # Look for additional data in step sections
        print(f"\n🔍 CHECKING STEP DATA FOR PATIENT INFO:")
        
        # Check if the raw details contain step data
        for key, value in case_details.items():
            if key.startswith('step') and isinstance(value, dict):
                step_form_data = value.get('form_data', {})
                if step_form_data:
                    print(f"   📋 {key}: {list(step_form_data.keys())}")
                    
                    # Check for patient name, age, gender, etc.
                    name = step_form_data.get('full_name') or step_form_data.get('patient_name')
                    gender = step_form_data.get('gender')
                    dob = step_form_data.get('date_of_birth')
                    
                    if name:
                        print(f"      👤 Name: {name}")
                    if gender:
                        print(f"      ⚥ Gender: {gender}")
                    if dob:
                        print(f"      📅 DOB: {dob}")
        
        # Build a basic patient summary
        def build_basic_patient_summary(case_details):
            """Build a basic patient summary from available data"""
            summary_parts = []
            
            # Get patient basic info
            form_data = case_details.get('form_data', {})
            
            # Try to find patient info in step data
            patient_name = None
            patient_gender = None
            patient_dob = None
            patient_vitals = []
            
            # Look through step data
            for key, value in case_details.items():
                if key.startswith('step') and isinstance(value, dict):
                    step_form = value.get('form_data', {})
                    
                    # Get basic demographics
                    if not patient_name:
                        patient_name = step_form.get('full_name') or step_form.get('patient_name')
                    if not patient_gender:
                        patient_gender = step_form.get('gender')
                    if not patient_dob:
                        patient_dob = step_form.get('date_of_birth')
                    
                    # Get vitals
                    if step_form.get('temperature'):
                        temp_unit = step_form.get('temperature_unit', '')
                        patient_vitals.append(f"Temperature: {step_form['temperature']}°{temp_unit.upper()}")
                    if step_form.get('oxygen_saturation'):
                        patient_vitals.append(f"Oxygen Saturation: {step_form['oxygen_saturation']}%")
                    if step_form.get('blood_pressure'):
                        patient_vitals.append(f"Blood Pressure: {step_form['blood_pressure']}")
            
            # Build summary
            if patient_name:
                summary_parts.append(f"Patient: {patient_name}")
            if patient_gender:
                summary_parts.append(f"Gender: {patient_gender.title()}")
            if patient_dob:
                summary_parts.append(f"Date of Birth: {patient_dob}")
            
            # Add contact info
            patient_email = form_data.get('patient_email')
            patient_phone = form_data.get('patient_phone')
            if patient_email and patient_email != 'Not provided':
                summary_parts.append(f"Email: {patient_email}")
            if patient_phone and patient_phone != 'Not provided':
                summary_parts.append(f"Phone: {patient_phone}")
            
            # Add vitals
            if patient_vitals:
                summary_parts.append("Vital Signs:")
                for vital in patient_vitals:
                    summary_parts.append(f"  • {vital}")
            
            # Add referring doctor info
            doctor_name = form_data.get('referring_doctor_name')
            if doctor_name and doctor_name != 'Not available':
                summary_parts.append(f"Referring Doctor: {doctor_name}")
            
            if summary_parts:
                return "\\n".join(summary_parts)
            else:
                return "Basic patient information not available in case data"
        
        fallback_summary = build_basic_patient_summary(case_details)
        print(f"\\n📝 GENERATED FALLBACK PATIENT SUMMARY:")
        print(f"{fallback_summary}")
        
        return fallback_summary
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    build_patient_summary_fallback()