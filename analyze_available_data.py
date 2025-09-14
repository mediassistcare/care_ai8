#!/usr/bin/env python3
import sqlite3
import json

def show_available_patient_info():
    """Show what patient information is actually available in the case data"""
    try:
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT case_number, details FROM cases WHERE case_number = 'CASE-2025-0001'")
        result = cursor.fetchone()
        
        if result:
            case_number, details_json = result
            details = json.loads(details_json)
            
            print(f"Case: {case_number}")
            print("="*50)
            
            # Show available patient information
            print("AVAILABLE PATIENT INFORMATION:")
            
            # Check if ai_generated_data has patient info
            if 'ai_generated_data' in details:
                ai_data = details['ai_generated_data']
                if 'clinical_summary' in ai_data:
                    summary = ai_data['clinical_summary']
                    # Extract patient name from clinical summary
                    lines = summary.split('\n')
                    for line in lines:
                        if 'Name:' in line or 'Patient Information:' in line:
                            print(f"  Found in clinical summary: {line.strip()}")
                
                # Show other available fields
                print("\nOther fields in ai_generated_data:")
                for key in ai_data.keys():
                    print(f"  - {key}")
            
            # Check top-level fields
            print("\nTop-level fields available:")
            for key in details.keys():
                print(f"  - {key}: {type(details[key])}")
            
            # Show what we can realistically extract
            print("\n" + "="*50)
            print("REALISTIC EXTRACTION OPTIONS:")
            
            # Patient name from clinical summary
            if 'ai_generated_data' in details and 'clinical_summary' in details['ai_generated_data']:
                summary = details['ai_generated_data']['clinical_summary']
                # Try to extract name
                import re
                name_match = re.search(r'Name:\s*([^\n]+)', summary)
                if name_match:
                    patient_name = name_match.group(1).strip()
                    print(f"  Patient Name: {patient_name}")
            
            # Show form_data fields if any
            if 'form_data' in details:
                print(f"  Form data available: {list(details['form_data'].keys())}")
            
            print("\nRECOMMENDATION:")
            print("  Since contact information is not stored in the case details,")
            print("  we should either:")
            print("  1. Show 'Contact information not available' message")
            print("  2. Extract patient name from clinical summary if available")
            print("  3. Add contact fields to the data entry process")
            
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    show_available_patient_info()