#!/usr/bin/env python3
import sqlite3
import json

def examine_real_case():
    """Examine the real case data structure"""
    try:
        conn = sqlite3.connect('care_ai_cases.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT details FROM cases WHERE case_number = 'CASE-2025-0001'")
        result = cursor.fetchone()
        
        if result:
            details = json.loads(result[0])
            print('Top-level keys:')
            for key in details.keys():
                print(f'  - {key}')
            
            print('\nLooking for contact information...')
            
            # Check all keys recursively for contact info
            def find_contact_fields(obj, path=''):
                contact_info = []
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        current_path = f'{path}.{key}' if path else key
                        if any(term in key.lower() for term in ['email', 'phone', 'contact', 'doctor']):
                            contact_info.append((current_path, value))
                        if isinstance(value, (dict, list)):
                            contact_info.extend(find_contact_fields(value, current_path))
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        current_path = f'{path}[{i}]'
                        if isinstance(item, (dict, list)):
                            contact_info.extend(find_contact_fields(item, current_path))
                return contact_info
            
            contact_fields = find_contact_fields(details)
            
            if contact_fields:
                print('Found contact-related fields:')
                for path, value in contact_fields:
                    print(f'  {path}: {value}')
            else:
                print('No contact fields found')
                
            # Also show a sample of the structure
            print('\n' + '='*50)
            print('SAMPLE JSON STRUCTURE:')
            print(json.dumps(details, indent=2)[:1500] + '...')
            
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    examine_real_case()