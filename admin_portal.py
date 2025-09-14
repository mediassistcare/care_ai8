#!/usr/bin/env python3
"""
Prompt Admin Portal
A standalone Flask application for managing AI prompts used by the Care Diagnostics application.
"""

import os
import shutil
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import json
from functools import wraps

app = Flask(__name__)
app.secret_key = 'prompt_admin_secret_key_2025'

# Configuration
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts')
DEFAULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts_defaults')
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts_backups')

# Authentication credentials
ADMIN_USERNAME = 'care'
ADMIN_PASSWORD = 'Care@2025'

def login_required(f):
    """Decorator to require login for protected routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def ensure_directories():
    """Ensure all required directories exist"""
    for directory in [PROMPTS_DIR, DEFAULTS_DIR, BACKUP_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)

def get_prompt_files():
    """Get list of all prompt files classified by UI pages/steps"""
    try:
        # Define prompt classification by UI pages/steps - CORRECTED based on actual app_new.py usage
        prompt_categories = {
            'Core System': {
                'description': 'Base system prompts used throughout the application',
                'ui_page': 'SYSTEM PROMPT',
                'prompts': ['medical_assistant_system.txt']
            },
            'Step 2.1: Identity Documents Processing': {
                'description': 'Document OCR and analysis - Aadhaar, Insurance, PDF processing in Step 2',
                'ui_page': '👤 Step 2: Patient Registration - Identity Documents',
                'prompts': [
                    'aadhaar_analysis.txt',
                    'aadhaar_system.txt',
                    'insurance_ocr_analysis.txt',
                    'insurance_ocr_system.txt',
                    'pdf_ocr_analysis.txt',
                    'pdf_ocr_system.txt'
                ]
            },
            'Step 2.2: EMR & Medical Records': {
                'description': 'Electronic Medical Records processing and analysis in Step 2',
                'ui_page': '👤 Step 2: Patient Registration - Medical Records',
                'prompts': [
                    'emr_analysis.txt',
                    'emr_system.txt'
                ]
            },
            'Step 3: Medical Photography & AI Analysis': {
                'description': 'Photo analysis for tongue, throat, and skin conditions in Step 3 vitals',
                'ui_page': '💓 Step 3: Comprehensive Vital Signs - Medical Photography',
                'prompts': [
                    'photo_analysis_system.txt',
                    'photo_tongue_analysis.txt',
                    'photo_throat_analysis.txt',
                    'photo_infection_analysis.txt',
                    'photo_laboratory_analysis.txt',
                    'photo_medical_image_analysis.txt',
                    'photo_signal_analysis.txt'
                ]
            },
            'Step 5: Symptom Analysis': {
                'description': 'Patient symptom description and AI-powered medical analysis',
                'ui_page': '💬 Step 5: Describe Your Symptoms',
                'prompts': [
                    'symptom_analysis.txt'
                ]
            },
            'Step 6: Diagnostic Tests & Reports': {
                'description': 'AI analysis of medical reports and diagnostic test recommendations',
                'ui_page': '🔍 Step 6: Detailed Symptom Analysis - Medical Reports',
                'prompts': [
                    'diagnostic_tests.txt',
                    'diagnostic_tests_system.txt',
                    'educational_lab_analysis.txt',
                    'educational_medical_image_analysis.txt',
                    'educational_pathology_analysis.txt',
                    'educational_signal_analysis.txt'
                ]
            },
            'Step 7.1: Differential Diagnosis': {
                'description': 'Interactive differential questions to narrow down diagnoses',
                'ui_page': '🔬 Step 7: ICD11 Generation - Differential Questions',
                'prompts': [
                    'differential_question.txt',
                    'differential_question_system.txt',
                    'answer_processing.txt',
                    'answer_processing_system.txt'
                ]
            },
            'Step 7.2: ICD11 Code Generation': {
                'description': 'Final ICD11 code generation and comprehensive diagnosis',
                'ui_page': '🔬 Step 7: ICD11 Generation - Final Diagnosis',
                'prompts': [
                    'icd11_generation.txt',
                    'icd11_generation_system.txt',
                    'icd10_diagnosis_system.txt',
                    'comprehensive_diagnosis.txt'
                ]
            },
            'Step 6-7: Clinical Summary & Follow-up': {
                'description': 'Clinical summaries and follow-up questions (referenced but not actively used in current flow)',
                'ui_page': '🔍 Step 6-7: Clinical Summary Generation',
                'prompts': [
                    'clinical_summary.txt',
                    'clinical_summary_system.txt',
                    'dynamic_questions.txt',
                    'dynamic_questions_system.txt',
                    'abnormal_vitals_followup.txt',
                    'followup_questions_system.txt'
                ]
            }
        }
        
        categorized_files = {}
        uncategorized_files = []
        
        if os.path.exists(PROMPTS_DIR):
            # Get all actual files in the directory
            actual_files = {}
            for filename in os.listdir(PROMPTS_DIR):
                if filename.endswith('.txt'):
                    filepath = os.path.join(PROMPTS_DIR, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    file_info = {
                        'name': filename,
                        'size': len(content),
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S'),
                        'lines': len(content.split('\n'))
                    }
                    actual_files[filename] = file_info
            
            # Categorize files
            for category, info in prompt_categories.items():
                categorized_files[category] = {
                    'description': info['description'],
                    'ui_page': info.get('ui_page', ''),
                    'files': []
                }
                
                for prompt_name in info['prompts']:
                    if prompt_name in actual_files:
                        categorized_files[category]['files'].append(actual_files[prompt_name])
                        del actual_files[prompt_name]
            
            # Add any remaining uncategorized files
            for filename in sorted(actual_files.keys()):
                uncategorized_files.append(actual_files[filename])
                
            if uncategorized_files:
                categorized_files['Uncategorized'] = {
                    'description': 'Prompts not yet categorized by UI step',
                    'files': uncategorized_files
                }
                
        return categorized_files
    except Exception as e:
        print(f"Error getting prompt files: {e}")
        return {}

def read_prompt_file(filename):
    """Read content of a prompt file"""
    try:
        filepath = os.path.join(PROMPTS_DIR, filename)
        if (os.path.exists(filepath)):
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"Error reading prompt file {filename}: {e}")
        return None

def save_prompt_file(filename, content):
    """Save content to a prompt file"""
    try:
        filepath = os.path.join(PROMPTS_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error saving prompt file {filename}: {e}")
        return False

def backup_current_prompts():
    """Create a backup of current prompts with timestamp"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f'backup_{timestamp}')
        
        if os.path.exists(PROMPTS_DIR):
            shutil.copytree(PROMPTS_DIR, backup_path)
            return backup_path
        return None
    except Exception as e:
        print(f"Error creating backup: {e}")
        return None

def backup_prompt_file(filename):
    """Create a backup of a specific prompt file before editing"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'{filename}_{timestamp}.bak'
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        source_path = os.path.join(PROMPTS_DIR, filename)
        if os.path.exists(source_path):
            # Ensure backup directory exists
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(source_path, backup_path)
            return backup_path
        return None
    except Exception as e:
        print(f"Error creating backup for {filename}: {e}")
        return None

def write_prompt_file(filename, content):
    """Write content to a prompt file (alias for save_prompt_file)"""
    return save_prompt_file(filename, content)

def copy_defaults_to_prompts():
    """Copy default prompts to prompts directory (first time setup)"""
    try:
        if not os.path.exists(DEFAULTS_DIR):
            # If defaults don't exist, copy current prompts as defaults
            if os.path.exists(PROMPTS_DIR):
                shutil.copytree(PROMPTS_DIR, DEFAULTS_DIR)
                print("✅ Created default prompts from current prompts")
                return True
        return True
    except Exception as e:
        print(f"Error setting up defaults: {e}")
        return False

def restore_to_defaults():
    """Restore all prompts to their default state"""
    try:
        if not os.path.exists(DEFAULTS_DIR):
            return False, "Default prompts not found"
        
        # Create backup before restore
        backup_path = backup_current_prompts()
        
        # Remove current prompts
        if os.path.exists(PROMPTS_DIR):
            shutil.rmtree(PROMPTS_DIR)
        
        # Copy defaults to prompts
        shutil.copytree(DEFAULTS_DIR, PROMPTS_DIR)
        
        return True, f"Restored to defaults. Backup created at: {os.path.basename(backup_path) if backup_path else 'N/A'}"
    except Exception as e:
        return False, f"Error restoring defaults: {e}"

def restore_file_to_default(filename):
    """Restore a specific prompt file to its default state"""
    try:
        if not filename.endswith('.txt'):
            return False, "Invalid file type"
        
        default_filepath = os.path.join(DEFAULTS_DIR, filename)
        current_filepath = os.path.join(PROMPTS_DIR, filename)
        
        # Check if default file exists
        if not os.path.exists(default_filepath):
            return False, f"Default file not found: {filename}"
        
        # Create backup of current file if it exists
        backup_path = None
        if os.path.exists(current_filepath):
            backup_path = backup_prompt_file(filename)
        
        # Copy default file to current location
        shutil.copy2(default_filepath, current_filepath)
        
        backup_info = f" Backup created: {os.path.basename(backup_path)}" if backup_path else ""
        return True, f"Restored {filename} to default.{backup_info}"
        
    except Exception as e:
        print(f"Error restoring file {filename} to default: {e}")
        return False, f"Error restoring {filename}: {str(e)}"

def get_file_comparison(filename):
    """Compare current file with default to show differences"""
    try:
        if not filename.endswith('.txt'):
            return None
        
        current_filepath = os.path.join(PROMPTS_DIR, filename)
        default_filepath = os.path.join(DEFAULTS_DIR, filename)
        
        current_content = ""
        default_content = ""
        
        if os.path.exists(current_filepath):
            with open(current_filepath, 'r', encoding='utf-8') as f:
                current_content = f.read()
        
        if os.path.exists(default_filepath):
            with open(default_filepath, 'r', encoding='utf-8') as f:
                default_content = f.read()
        
        return {
            'filename': filename,
            'current_content': current_content,
            'default_content': default_content,
            'has_changes': current_content != default_content,
            'current_size': len(current_content),
            'default_size': len(default_content),
            'current_lines': len(current_content.split('\n')) if current_content else 0,
            'default_lines': len(default_content.split('\n')) if default_content else 0
        }
        
    except Exception as e:
        print(f"Error comparing file {filename}: {e}")
        return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for admin portal"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            session['login_time'] = datetime.now().isoformat()
            flash('Successfully logged in!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    """Logout from admin portal"""
    session.clear()
    flash('Successfully logged out', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Main dashboard showing all prompt files categorized by UI steps"""
    ensure_directories()
    copy_defaults_to_prompts()  # Ensure defaults exist
    
    categorized_files = get_prompt_files()
    
    # Debug: Print ui_page information
    print("\n🔍 DEBUG: Checking ui_page data...")
    for category, info in categorized_files.items():
        ui_page = info.get('ui_page', 'MISSING')
        print(f"Category: {category} | UI Page: {ui_page}")
    print("🔍 DEBUG: End of ui_page data\n")
    
    # Get summary statistics
    total_files = 0
    total_size = 0
    total_lines = 0
    
    for category, info in categorized_files.items():
        category_files = info.get('files', [])
        total_files += len(category_files)
        total_size += sum(f['size'] for f in category_files)
        total_lines += sum(f['lines'] for f in category_files)
    
    stats = {
        'total_files': total_files,
        'total_size': total_size,
        'total_lines': total_lines,
        'total_categories': len(categorized_files),
        'avg_size': total_size // total_files if total_files > 0 else 0
    }
    
    return render_template('admin_index.html', categorized_files=categorized_files, stats=stats)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
@login_required
def edit_prompt(filename):
    """Edit a specific prompt file"""
    if not filename.endswith('.txt'):
        flash('Invalid file type', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Handle form submission (save changes)
        new_content = request.form.get('content', '')
        
        # Create backup before saving
        backup_path = backup_prompt_file(filename)
        if backup_path:
            flash(f'Backup created: {os.path.basename(backup_path)}', 'info')
        
        # Save the file
        success = write_prompt_file(filename, new_content)
        if success:
            flash(f'Successfully saved {filename}', 'success')
            return redirect(url_for('index'))
        else:
            flash(f'Error saving {filename}', 'error')
    
    # Handle GET request (show edit form)
    content = read_prompt_file(filename)
    if content is None:
        flash(f'File {filename} not found', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_edit.html', filename=filename, content=content)

@app.route('/save/<filename>', methods=['POST'])
@login_required
def save_prompt(filename):
    """Save changes to a prompt file"""
    if not filename.endswith('.txt'):
        return jsonify({'success': False, 'message': 'Invalid file type'})
    
    content = request.form.get('content', '')
    
    if save_prompt_file(filename, content):
        flash(f'Successfully saved {filename}', 'success')
        return jsonify({'success': True, 'message': f'Successfully saved {filename}'})
    else:
        return jsonify({'success': False, 'message': f'Failed to save {filename}'})

@app.route('/view/<filename>')
@login_required
def view_prompt(filename):
    """View a prompt file in read-only mode"""
    if not filename.endswith('.txt'):
        flash('Invalid file type', 'error')
        return redirect(url_for('index'))
    
    content = read_prompt_file(filename)
    if content is None:
        flash(f'File {filename} not found', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_view.html', filename=filename, content=content)

@app.route('/restore', methods=['POST'])
@login_required
def restore_defaults():
    """Restore all prompts to default state"""
    success, message = restore_to_defaults()
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('index'))

@app.route('/backup', methods=['POST'])
@login_required
def create_backup():
    """Create a manual backup of current prompts"""
    backup_path = backup_current_prompts()
    
    if backup_path:
        flash(f'Backup created: {os.path.basename(backup_path)}', 'success')
    else:
        flash('Failed to create backup', 'error')
    
    return redirect(url_for('index'))

@app.route('/restore/<filename>', methods=['POST'])
@login_required
def restore_file_default(filename):
    """Restore a specific prompt file to its default state"""
    if not filename.endswith('.txt'):
        flash('Invalid file type', 'error')
        return redirect(url_for('index'))
    
    success, message = restore_file_to_default(filename)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('index'))

@app.route('/compare/<filename>')
@login_required
def compare_with_default(filename):
    """Compare current file with default version"""
    if not filename.endswith('.txt'):
        flash('Invalid file type', 'error')
        return redirect(url_for('index'))
    
    comparison = get_file_comparison(filename)
    if comparison is None:
        flash(f'Error comparing {filename}', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_compare.html', comparison=comparison)

@app.route('/api/restore/<filename>', methods=['POST'])
@login_required
def api_restore_file(filename):
    """API endpoint to restore a specific file to default"""
    if not filename.endswith('.txt'):
        return jsonify({'success': False, 'message': 'Invalid file type'})
    
    success, message = restore_file_to_default(filename)
    return jsonify({'success': success, 'message': message})

@app.route('/api/compare/<filename>')
@login_required
def api_compare_file(filename):
    """API endpoint to compare file with default"""
    if not filename.endswith('.txt'):
        return jsonify({'success': False, 'message': 'Invalid file type'})
    
    comparison = get_file_comparison(filename)
    if comparison is not None:
        return jsonify({'success': True, 'comparison': comparison})
    else:
        return jsonify({'success': False, 'message': 'Error comparing file'})

@app.route('/api/prompt/<filename>')
@login_required
def api_get_prompt(filename):
    """API endpoint to get prompt content"""
    content = read_prompt_file(filename)
    if content is not None:
        return jsonify({'success': True, 'content': content})
    else:
        return jsonify({'success': False, 'message': 'File not found'})

@app.route('/api/prompt/<filename>', methods=['PUT'])
@login_required
def api_save_prompt(filename):
    """API endpoint to save prompt content"""
    data = request.get_json()
    content = data.get('content', '')
    
    if save_prompt_file(filename, content):
        return jsonify({'success': True, 'message': 'File saved successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to save file'})

@app.route('/api/files')
@login_required
def api_get_files():
    """API endpoint to get list of all prompt files"""
    files = get_prompt_files()
    return jsonify({'success': True, 'files': files})

if __name__ == '__main__':
    print("🚀 Starting Prompt Admin Portal...")
    print("📁 Prompts Directory:", PROMPTS_DIR)
    print("💾 Defaults Directory:", DEFAULTS_DIR)
    print("🔄 Backups Directory:", BACKUP_DIR)
    print("🌐 Admin Portal URL: http://0.0.0.0:5002")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5002, debug=True)
