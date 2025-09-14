#!/usr/bin/env python3
import sqlite3
import json
import sys

def examine_case_data():
    """Examine the actual structure of case data to understand contact fields"""
    try:
        # Connect to database
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        
        # Get a sample case
        cursor.execute("SELECT case_number, details FROM cases WHERE status = 'pending_review' LIMIT 1")
        result = cursor.fetchone()
        
        if result:
            case_number, details_json = result
            print(f"Examining case: {case_number}")
            print("="*50)
            
            # Parse JSON
            try:
                details = json.loads(details_json)
                print("Top-level keys in details:")
                for key in details.keys():
                    print(f"  - {key}")
                
                print("\n" + "="*50)
                
                # Look for contact-related fields
                contact_fields = ['patient_email', 'patient_phone', 'referring_doctor', 'doctor', 'contact']
                
                print("Searching for contact information:")
                for field in contact_fields:
                    if field in details:
                        print(f"Found '{field}': {details[field]}")
                
                # Check if contact info is nested somewhere
                print("\nChecking nested structures:")
                
                # Check patient_data if it exists
                if 'patient_data' in details:
                    print("Found patient_data:")
                    patient_data = details['patient_data']
                    for key, value in patient_data.items():
                        if any(contact_term in key.lower() for contact_term in ['email', 'phone', 'contact']):
                            print(f"  - {key}: {value}")
                
                # Check ai_generated_data if it exists
                if 'ai_generated_data' in details:
                    print("Found ai_generated_data:")
                    ai_data = details['ai_generated_data']
                    for key, value in ai_data.items():
                        if any(contact_term in key.lower() for contact_term in ['email', 'phone', 'contact', 'doctor', 'referring']):
                            print(f"  - {key}: {value}")
                
                # Print full structure for examination
                print("\n" + "="*50)
                print("FULL JSON STRUCTURE (first 2000 chars):")
                print(json.dumps(details, indent=2)[:2000] + "...")
                
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")
        else:
            print("No pending review cases found")
            
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    examine_case_data()