#!/usr/bin/env python3
import sqlite3
import json

def check_all_cases():
    """Check all cases to find ones with actual patient data"""
    try:
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        
        # Get all cases to see which ones have real data
        cursor.execute('SELECT case_number, LENGTH(details), details FROM cases ORDER BY created_date DESC LIMIT 5')
        results = cursor.fetchall()
        
        for case_number, details_length, details_json in results:
            print(f'Case: {case_number}, Details length: {details_length} characters')
            if details_length > 100:  # Look for cases with substantial data
                try:
                    details = json.loads(details_json)
                    print(f'  Top-level keys: {list(details.keys())}')
                    if 'patient_data' in details:
                        patient_keys = list(details['patient_data'].keys())
                        print(f'  Has patient_data with keys: {patient_keys}')
                        
                        # Look for contact info in patient_data
                        for key in patient_keys:
                            if any(term in key.lower() for term in ['email', 'phone', 'contact']):
                                print(f'    Contact field: {key} = {details["patient_data"][key]}')
                    
                    # Also check for referring doctor info
                    for key in details.keys():
                        if 'doctor' in key.lower() or 'referring' in key.lower():
                            print(f'  Doctor field: {key} = {details[key]}')
                            
                except Exception as e:
                    print(f'  JSON parse error: {e}')
            print()
        
        conn.close()
        
    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    check_all_cases()