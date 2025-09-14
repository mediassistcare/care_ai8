#!/usr/bin/env python3
import json
import os
from datetime import datetime

# Get all patient data files
data_dir = "care_app_data"
files = []

for filename in os.listdir(data_dir):
    if filename.startswith('patient_data_') and filename.endswith('.json'):
        filepath = os.path.join(data_dir, filename)
        mtime = os.path.getmtime(filepath)
        files.append((filepath, mtime, filename))

# Sort by modification time (newest first)
files.sort(key=lambda x: x[1], reverse=True)

if files:
    latest_file, mtime, filename = files[0]
    print(f"Most recent patient data file: {filename}")
    print(f"Last modified: {datetime.fromtimestamp(mtime)}")
    
    with open(latest_file, 'r') as f:
        data = json.load(f)
    
    # Check completion status
    step_completed = data.get('step_completed', 0)
    print(f"Highest step completed: {step_completed}")
    
    # Check if step7 exists and is completed
    if 'step7' in data:
        step7 = data['step7']
        print(f"Step7 exists: Yes")
        print(f"Step7 completed: {step7.get('step_completed', False)}")
        
        # Check form data
        form_data = step7.get('form_data', {})
        print(f"Has contact info: {bool(form_data.get('patient_email'))}")
        
        if form_data.get('patient_email'):
            print(f"Patient email: {form_data.get('patient_email')}")
            print(f"Patient phone: {form_data.get('patient_phone')}")
            print(f"Referring doctor: {form_data.get('referring_doctor_name')}")
        
        # Check submission status
        submission_status = form_data.get('completion_status', 'Not set')
        print(f"Completion status: {submission_status}")
        
        # Check if it should have been submitted
        expert_review = form_data.get('expert_review_submitted', False)
        print(f"Expert review submitted: {expert_review}")
        
    else:
        print("Step7 does not exist")
        
else:
    print("No patient data files found")