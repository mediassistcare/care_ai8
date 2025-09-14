#!/usr/bin/env python3
import json
import os
from datetime import datetime

# Check the new patient data file
filepath = 'care_app_data/patient_data_5dcf2bd4-0c05-433c-b0d0-b545e0c32452.json'

if os.path.exists(filepath):
    mtime = os.path.getmtime(filepath)
    print(f'File exists: {filepath}')
    print(f'Last modified: {datetime.fromtimestamp(mtime)}')
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    step_completed = data.get('step_completed', 0)
    print(f'Highest step completed: {step_completed}')
    
    if 'step7' in data:
        step7 = data['step7']
        form_data = step7.get('form_data', {})
        print(f'Step7 exists: Yes')
        print(f'Step7 completed: {step7.get("step_completed", False)}')
        print(f'Expert review submitted: {form_data.get("expert_review_submitted", False)}')
        print(f'Completion status: {form_data.get("completion_status", "Not set")}')
        print(f'Step status: {form_data.get("step_status", "Not set")}')
        print(f'Has contact info: {bool(form_data.get("patient_email"))}')
        
        if form_data.get("patient_email"):
            print(f'Patient email: {form_data.get("patient_email")}')
            print(f'Patient phone: {form_data.get("patient_phone")}')
            print(f'Referring doctor: {form_data.get("referring_doctor_name")}')
    else:
        print('Step7 does not exist')
else:
    print('File does not exist')