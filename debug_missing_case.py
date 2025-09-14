#!/usr/bin/env python3
import json

with open('care_app_data/patient_data_7447df6e-6643-429f-818f-fff98aae61e4.json', 'r') as f:
    data = json.load(f)

step7 = data.get('step7', {})
form_data = step7.get('form_data', {})

print('Step7 form_data keys:')
for key in form_data.keys():
    print(f'  - {key}: {form_data[key]}')

print(f'\nSession ID: {data.get("session_id", "Unknown")}')
print(f'User: {data.get("user_profile", {}).get("username", "Unknown")}')

# Check if this looks like it should have been submitted
should_submit = (
    form_data.get('expert_review_submitted', False) and
    'submitted_for_expert_review' in form_data.get('completion_status', '')
)
print(f'\nShould have been submitted: {should_submit}')

# Check what the actual submission criteria is
ai_data = step7.get('ai_generated_data', {})
print(f'Has ai_generated_data: {bool(ai_data)}')
if ai_data:
    print('AI data keys:')
    for key in ai_data.keys():
        print(f'  - {key}')