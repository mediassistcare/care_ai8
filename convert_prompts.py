#!/usr/bin/env python3
"""
Script to automatically replace all hardcoded prompts in app_new.py with calls to external prompt files.
This script will modify app_new.py to use the prompt_loader module instead of hardcoded prompts.

Run this script after creating all prompt files to automatically update your app_new.py
"""

import re
import os

def replace_prompts_in_file():
    """Replace all hardcoded prompts in app_new.py with calls to load_prompt()"""
    
    app_file = "app_new.py"
    backup_file = "app_new_backup.py"
    
    print("🔄 Starting prompt replacement process...")
    
    # Create backup
    print(f"📋 Creating backup: {backup_file}")
    with open(app_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # List of prompt replacements
    replacements = [
        # EMR prompts
        {
            'old_pattern': r'prompt = f"""[\s\S]*?Analyze the uploaded Electronic Medical Record.*?Use clear, concise language with medical terminology where appropriate\.\s*"""',
            'new_code': 'prompt = load_prompt("emr_analysis")',
            'name': 'EMR Analysis'
        },
        {
            'old_pattern': r'"content": "You are a medical AI assistant specialized in analyzing Electronic Medical Records.*?Provide accurate, concise medical insights from uploaded documents\."',
            'new_code': '"content": load_prompt("emr_system")',
            'name': 'EMR System'
        },
        
        # Aadhaar prompts
        {
            'old_pattern': r'prompt = """[\s\S]*?Analyze the uploaded Aadhaar card image.*?"error": "Clear description of the issue"\s*}\s*"""',
            'new_code': 'prompt = load_prompt("aadhaar_analysis")',
            'name': 'Aadhaar Analysis'
        },
        {
            'old_pattern': r'"content": "You are an expert document analysis AI specialized in extracting information from Indian Aadhaar cards.*?You can read text from images with high accuracy and extract personal information reliably\."',
            'new_code': '"content": load_prompt("aadhaar_system")',
            'name': 'Aadhaar System'
        },
        
        # OCR prompts
        {
            'old_pattern': r'ocr_prompt = f"""[\s\S]*?Extract ALL visible text from this PDF page image.*?OUTPUT FORMAT: Return only the extracted text in reading order, no analysis or summary\.\s*"""',
            'new_code': 'ocr_prompt = load_prompt("pdf_ocr_analysis")',
            'name': 'PDF OCR Analysis'
        },
        {
            'old_pattern': r'"content": "You are an expert OCR system\. Extract ALL visible text from images with 100% accuracy in exact chronological order\. No summarization, just complete text extraction\."',
            'new_code': '"content": load_prompt("pdf_ocr_system")',
            'name': 'PDF OCR System'
        },
        
        # Insurance prompts
        {
            'old_pattern': r'prompt = """[\s\S]*?Extract ALL visible text from this insurance document image.*?OUTPUT REQUIREMENT: Return ONLY the complete extracted text.*?\.\s*"""',
            'new_code': 'prompt = load_prompt("insurance_ocr_analysis")',
            'name': 'Insurance OCR Analysis'
        },
        {
            'old_pattern': r'"content": "You are an expert OCR system specialized in comprehensive text extraction from insurance documents.*?Extract ALL visible text with 100% accuracy in chronological order\. No summarization allowed\."',
            'new_code': '"content": load_prompt("insurance_ocr_system")',
            'name': 'Insurance OCR System'
        },
        
        # Photo analysis system prompt
        {
            'old_pattern': r'"content": "You are an expert medical AI specialized in analyzing medical photographs and clinical images\. Provide accurate visual assessments for diagnostic support\."',
            'new_code': '"content": load_prompt("photo_analysis_system")',
            'name': 'Photo Analysis System'
        },
        
        # Other system prompts
        {
            'old_pattern': r'"content": "You are an expert physician specializing in diagnostic medicine, laboratory medicine, and medical imaging\. Focus on evidence-based test selection and clinical decision-making\."',
            'new_code': '"content": load_prompt("diagnostic_tests_system")',
            'name': 'Diagnostic Tests System'
        },
        {
            'old_pattern': r'"content": "You are an expert physician specializing in differential diagnosis and ICD coding\. Focus on creating precise, medically accurate questions\. Return only valid JSON\."',
            'new_code': '"content": load_prompt("differential_question_system")',
            'name': 'Differential Question System'
        },
        {
            'old_pattern': r'"content": "You are an expert physician specializing in differential diagnosis\. You must eliminate exactly one ICD code from the provided list\. Return only valid JSON\."',
            'new_code': '"content": load_prompt("answer_processing_system")',
            'name': 'Answer Processing System'
        },
        {
            'old_pattern': r'"content": "You are an expert medical coder specializing in WHO ICD-11 classification\. Provide accurate, evidence-based diagnostic codes\."',
            'new_code': '"content": load_prompt("icd11_generation_system")',
            'name': 'ICD-11 Generation System'
        },
        {
            'old_pattern': r'"content": """You are an expert physician with extensive experience in diagnostic medicine and ICD-10 coding\.[\s\S]*?Always respond with valid JSON format containing disease codes, not symptom codes\."""',
            'new_code': '"content": load_prompt("icd10_diagnosis_system")',
            'name': 'ICD-10 Diagnosis System'
        },
        {
            'old_pattern': r'"content": "You are a clinical physician with expertise in medical documentation\.[\s\S]*?focus ONLY on documenting findings without providing any treatment recommendations or medical advice\."',
            'new_code': '"content": load_prompt("clinical_summary_system")',
            'name': 'Clinical Summary System'
        },
        {
            'old_pattern': r'"content": "You are a medical expert who understands both medical conditions and what patients actually experience\.[\s\S]*?You ask about real, observable experiences rather than medical measurements\."',
            'new_code': '"content": load_prompt("dynamic_questions_system")',
            'name': 'Dynamic Questions System'
        },
        {
            'old_pattern': r'"content": "You are an experienced physician generating targeted follow-up questions for abnormal medical findings\. Always respond with valid JSON array format\."',
            'new_code': '"content": load_prompt("followup_questions_system")',
            'name': 'Follow-up Questions System'
        }
    ]
    
    # Apply replacements
    modified_content = content
    replacement_count = 0
    
    for replacement in replacements:
        old_pattern = replacement['old_pattern']
        new_code = replacement['new_code']
        name = replacement['name']
        
        # Use regex to find and replace
        if re.search(old_pattern, modified_content, re.MULTILINE | re.DOTALL):
            modified_content = re.sub(old_pattern, new_code, modified_content, flags=re.MULTILINE | re.DOTALL)
            print(f"✅ Replaced: {name}")
            replacement_count += 1
        else:
            print(f"⚠️  Not found: {name}")
    
    # Handle the complex photo prompts dictionary
    photo_prompts_pattern = r"prompts = \{[\s\S]*?'signal': f\"\"\"[\s\S]*?\"\"\"\s*\}"
    
    photo_prompts_replacement = '''# Load photo analysis prompts dynamically
        def get_photo_prompt(category, photo_type, report_type=None):
            """Get the appropriate photo analysis prompt"""
            if category in ['laboratory', 'medical_image', 'signal']:
                prompt_name = f"photo_{category}_analysis"
            else:
                prompt_map = {
                    'tongue': 'photo_tongue_analysis',
                    'throat': 'photo_throat_analysis',
                    'infection': 'photo_infection_analysis'
                }
                prompt_name = prompt_map.get(photo_type, 'photo_infection_analysis')
            
            prompt_content = load_prompt(prompt_name)
            
            # Replace report_type placeholder if needed
            if report_type and '{report_type}' in prompt_content:
                prompt_content = prompt_content.replace('{report_type}', report_type.upper())
            elif '{report_type}' in prompt_content:
                prompt_content = prompt_content.replace('{report_type}', 'UNKNOWN')
                
            return prompt_content
        
        # Get the appropriate prompt
        if category in ['laboratory', 'medical_image', 'signal']:
            base_prompt = get_photo_prompt(category, photo_type, report_type)
        else:
            base_prompt = get_photo_prompt(category, photo_type, report_type)'''
    
    if re.search(photo_prompts_pattern, modified_content, re.MULTILINE | re.DOTALL):
        # Also need to replace the prompt selection logic
        prompt_selection_pattern = r"# Determine which prompt to use[\s\S]*?base_prompt = prompts\.get\(photo_type, prompts\['infection'\]\)"
        
        modified_content = re.sub(photo_prompts_pattern, photo_prompts_replacement, modified_content, flags=re.MULTILINE | re.DOTALL)
        modified_content = re.sub(prompt_selection_pattern, "", modified_content, flags=re.MULTILINE | re.DOTALL)
        print("✅ Replaced: Photo Analysis Prompts Dictionary")
        replacement_count += 1
    
    # Write the modified content
    with open(app_file, 'w', encoding='utf-8') as f:
        f.write(modified_content)
    
    print(f"\n🎉 Replacement complete!")
    print(f"📊 Total replacements made: {replacement_count}")
    print(f"💾 Original file backed up as: {backup_file}")
    print(f"✨ Modified file: {app_file}")
    
    print("\n📝 Next steps:")
    print("1. Test your application to ensure all prompts load correctly")
    print("2. If everything works, you can delete the backup file")
    print("3. If there are issues, restore from the backup file")

if __name__ == "__main__":
    replace_prompts_in_file()
