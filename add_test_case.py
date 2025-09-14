#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime

def add_test_case_with_contacts():
    """Add a test case with contact information to verify the display"""
    try:
        # Sample case data with contact information
        test_case_data = {
            "step_name": "ICD11 Code Generation & Analysis",
            "form_data": {
                "icd_generation_completed": True,
                "codes_generated": 6,
                "patient_email": "patient.test@gmail.com",
                "patient_phone": "9876543210",
                "referring_doctor_id": "7",
                "referring_doctor_name": "Dr. Sarah Johnson",
                "referring_doctor_phone": "7777777777",
                "referring_doctor_email": "sarah.johnson@medical.com",
                "referring_doctor_details": {
                    "id": 7,
                    "first_name": "Sarah",
                    "last_name": "Johnson",
                    "phone_number": "7777777777",
                    "email_address": "sarah.johnson@medical.com",
                    "area_of_expertise": "Cardiology",
                    "qualification": "MD, FACC"
                },
                "expert_review_submitted": True,
                "submission_timestamp": datetime.now().isoformat(),
                "completion_status": "submitted_for_expert_review",
                "total_icd_codes": 3,
                "total_lab_tests": 5,
                "differential_questions_answered": 2
            },
            "ai_generated_data": {
                "clinical_summary": "Patient Clinical Summary\nPatient Information:\n- Name: John Doe\n- Age: 45\n- Gender: Male\n\nVital Signs:\n- Temperature: 99.2°F\n- Blood Pressure: 140/90 mmHg\n- Heart Rate: 85 bpm\n- Oxygen Saturation: 97%\n\nPresenting Complaints:\n- Chest pain\n- Shortness of breath\n- Fatigue\n\nClinical Findings:\n- Patient presents with chest discomfort that occurs with exertion\n- No signs of acute distress at rest\n- Blood pressure is elevated\n- Regular heart rhythm noted\n\nRecommendations:\n- ECG monitoring\n- Cardiac enzyme tests\n- Stress testing consideration",
                "icd_codes_generated": [
                    {
                        "code": "I25.9",
                        "title": "Chronic ischemic heart disease, unspecified",
                        "description": "A condition affecting the heart's blood supply",
                        "confidence": 85
                    },
                    {
                        "code": "I10",
                        "title": "Essential hypertension",
                        "description": "High blood pressure without known cause",
                        "confidence": 92
                    }
                ],
                "recommended_lab_tests": [
                    {
                        "test_name": "Troponin I",
                        "category": "Cardiac Markers",
                        "urgency": "immediate",
                        "cost_tier": "medium",
                        "reasoning": "To rule out myocardial infarction",
                        "expected_findings": "Elevated levels would indicate cardiac muscle damage"
                    },
                    {
                        "test_name": "ECG",
                        "category": "Cardiac Diagnostics",
                        "urgency": "immediate",
                        "cost_tier": "low",
                        "reasoning": "To assess cardiac rhythm and ischemic changes",
                        "expected_findings": "May show ST-segment changes or arrhythmias"
                    }
                ],
                "elimination_history": [
                    {
                        "eliminated_diagnosis": "Pneumonia",
                        "reason": "No respiratory symptoms or fever"
                    }
                ],
                "patient_data_summary": "45-year-old male with chest pain and hypertension"
            },
            "files_uploaded": {},
            "timestamp": datetime.now().isoformat(),
            "data_source": "user_input_and_ai_analysis",
            "step_completed": True
        }
        
        # Connect to database
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        
        # Insert test case
        case_number = "CASE-2025-CONTACTS"
        details_json = json.dumps(test_case_data, indent=2)
        
        cursor.execute("""
            INSERT OR REPLACE INTO cases (case_number, details, status, feedback) 
            VALUES (?, ?, ?, ?)
        """, (case_number, details_json, 'pending_review', ''))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Test case created successfully: {case_number}")
        print("Contact information included:")
        print(f"  Patient Email: {test_case_data['form_data']['patient_email']}")
        print(f"  Patient Phone: {test_case_data['form_data']['patient_phone']}")
        print(f"  Doctor Name: {test_case_data['form_data']['referring_doctor_name']}")
        print(f"  Doctor Email: {test_case_data['form_data']['referring_doctor_email']}")
        print(f"  Doctor Expertise: {test_case_data['form_data']['referring_doctor_details']['area_of_expertise']}")
        
    except Exception as e:
        print(f"Error creating test case: {e}")

if __name__ == "__main__":
    add_test_case_with_contacts()