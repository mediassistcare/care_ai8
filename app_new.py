from flask import Flask, render_template, request, jsonify, session, redirect
from openai import OpenAI
import json
import base64
from datetime import datetime
import os
import tempfile
import uuid
import glob
from dotenv import load_dotenv
from prompt_loader import load_prompt, get_photo_analysis_prompt
from functools import wraps
import sqlite3
import mysql.connector
from mysql.connector import Error

# Load environment variables
load_dotenv()

# Debug: Check what API key is loaded
api_key_from_env = os.getenv('OPENAI_API_KEY')
print(f"DEBUG: API key from .env: {api_key_from_env[:15] if api_key_from_env else 'None'}...")

app = Flask(__name__)
app.secret_key = 'your-secure-secret-key-2024'  # Change this to a secure secret key

# Configure OpenAI client
openai_client = OpenAI(api_key=api_key_from_env)

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'care_ai'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'port': int(os.getenv('DB_PORT', 3306))
}

# SQLite database path
SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'care_ai_cases.db')

def get_sqlite_connection():
    """Create and return a SQLite database connection"""
    try:
        connection = sqlite3.connect(SQLITE_DB_PATH)
        connection.row_factory = sqlite3.Row  # Enable dict-like access
        return connection
    except Exception as e:
        print(f"❌ SQLite connection error: {e}")
        return None

def get_db_connection():
    """Create and return a database connection (tries SQLite first, then MySQL)"""
    # Try SQLite first
    sqlite_conn = get_sqlite_connection()
    if sqlite_conn:
        return sqlite_conn
    
    # Fallback to MySQL if available
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"❌ Database connection error: {e}")
        return None

def build_patient_summary_fallback(case_details):
    """Build a basic patient summary from available case data when AI summary is missing"""
    try:
        summary_parts = []
        form_data = case_details.get('form_data', {})
        
        # Get contact information
        patient_email = form_data.get('patient_email')
        patient_phone = form_data.get('patient_phone')
        referring_doctor = form_data.get('referring_doctor_name')
        
        # Add contact info if available
        if patient_email and patient_email not in ['Not provided', '']:
            summary_parts.append(f"Email: {patient_email}")
        if patient_phone and patient_phone not in ['Not provided', '']:
            summary_parts.append(f"Phone: {patient_phone}")
        if referring_doctor and referring_doctor not in ['Not available', '']:
            summary_parts.append(f"Referring Doctor: {referring_doctor}")
        
        # Try to extract basic clinical info from clinical summary if available
        clinical_summary = form_data.get('clinical_summary_edited', '')
        if clinical_summary:
            # Extract patient name if it appears in clinical summary
            lines = clinical_summary.split('\n')
            for line in lines[:10]:  # Check first 10 lines
                if 'Name:' in line:
                    summary_parts.insert(0, line.strip())
                elif 'Gender:' in line:
                    summary_parts.append(line.strip())
                elif 'Age:' in line:
                    summary_parts.append(line.strip())
        
        # Add completion status
        step_status = form_data.get('step_status', '')
        if step_status:
            summary_parts.append(f"Assessment Status: {step_status.replace('_', ' ').title()}")
        
        if summary_parts:
            return '\n'.join(summary_parts)
        else:
            return "Basic patient contact information available in case details"
            
    except Exception as e:
        print(f"❌ Error building patient summary fallback: {e}")
        return "Error building patient summary"

def generate_case_number():
    """Generate a unique case number in format CASE-YYYY-NNNN"""
    try:
        connection = get_sqlite_connection()
        if connection:
            cursor = connection.cursor()
            
            # Get current year
            current_year = datetime.now().year
            
            # Get ALL case numbers for current year (not just the first one)
            query = "SELECT case_number FROM cases WHERE case_number LIKE ?"
            pattern = f"CASE-{current_year}-%"
            cursor.execute(query, (pattern,))
            results = cursor.fetchall()
            
            # Find the highest numeric case number
            max_number = 0
            for result in results:
                case_number = result[0]
                try:
                    # Try to extract numeric part (CASE-YYYY-NNNN format)
                    parts = case_number.split('-')
                    if len(parts) >= 3:
                        last_part = parts[-1]
                        if last_part.isdigit():
                            number = int(last_part)
                            max_number = max(max_number, number)
                except (ValueError, IndexError):
                    # Skip non-numeric case numbers (like test data)
                    continue
            
            # Generate next number
            new_number = max_number + 1
            case_number = f"CASE-{current_year}-{new_number:04d}"
            
            cursor.close()
            connection.close()
            
            return case_number
            
    except Exception as e:
        print(f"❌ Error generating case number: {e}")
        # Fallback to UUID-based case number
        return f"CASE-{datetime.now().year}-{str(uuid.uuid4())[:8].upper()}"
    
    # Fallback if no database connection
    return f"CASE-{datetime.now().year}-{str(uuid.uuid4())[:8].upper()}"

# Authentication decorator
def login_required(f):
    """Decorator to ensure user is logged in before accessing any route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# File storage functions for patient data
APP_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'care_app_data')
os.makedirs(APP_DATA_DIR, exist_ok=True)

def get_session_file_path():
    """Get the file path for storing session data"""
    session_id = session.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
    return os.path.join(APP_DATA_DIR, f'patient_data_{session_id}.json')

def save_patient_data(patient_data):
    """Save patient data to temporary file"""
    try:
        file_path = get_session_file_path()
        with open(file_path, 'w') as f:
            json.dump(patient_data, f, indent=2)
        print(f"DEBUG: Saved patient data to {file_path}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to save patient data: {str(e)}")
        return False

def load_patient_data():
    """Load patient data from temporary file"""
    try:
        file_path = get_session_file_path()
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
            print(f"DEBUG: Loaded patient data from {file_path}")
            return data
        else:
            print(f"DEBUG: No patient data file found at {file_path}")
            return {}
    except Exception as e:
        print(f"ERROR: Failed to load patient data: {str(e)}")
        return {}

def clear_patient_data():
    """Clear patient data file"""
    try:
        file_path = get_session_file_path()
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"DEBUG: Cleared patient data file {file_path}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to clear patient data: {str(e)}")
        return False

def clear_all_patient_data():
    """Clear patient data files older than 12 hours from the care_app_data folder"""
    try:
        import glob
        import time
        
        # Find all patient data files
        pattern = os.path.join(APP_DATA_DIR, 'patient_data_*.json')
        files = glob.glob(pattern)
        
        # Calculate 12 hours ago in seconds
        twelve_hours_ago = time.time() - (12 * 60 * 60)  # 12 hours * 60 minutes * 60 seconds
        
        cleared_count = 0
        skipped_count = 0
        
        for file_path in files:
            try:
                # Get file modification time
                file_mod_time = os.path.getmtime(file_path)
                
                # Check if file is older than 12 hours
                if file_mod_time < twelve_hours_ago:
                    os.remove(file_path)
                    print(f"DEBUG: Removed old file {file_path} (age: {(time.time() - file_mod_time) / 3600:.1f} hours)")
                    cleared_count += 1
                else:
                    print(f"DEBUG: Skipped recent file {file_path} (age: {(time.time() - file_mod_time) / 3600:.1f} hours)")
                    skipped_count += 1
                    
            except Exception as e:
                print(f"ERROR: Failed to process file {file_path}: {str(e)}")
        
        print(f"✅ Cleared {cleared_count} old patient data files (older than 12 hours)")
        print(f"ℹ️ Kept {skipped_count} recent files (less than 12 hours old)")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: Failed to clear all patient data: {str(e)}")
        return False

# User profile management functions
# User profile management functions (now integrated into patient_data)
def cleanup_old_user_profile_files():
    """Remove old separate user_profile files since we've integrated into patient_data"""
    try:
        pattern = os.path.join(APP_DATA_DIR, 'user_profile_*.json')
        files = glob.glob(pattern)
        for file_path in files:
            try:
                os.remove(file_path)
                print(f"DEBUG: Removed old user profile file: {file_path}")
            except Exception as e:
                print(f"WARNING: Could not remove old user profile file {file_path}: {str(e)}")
    except Exception as e:
        print(f"ERROR: Failed to cleanup old user profile files: {str(e)}")

def save_user_profile_to_patient_data(profile_updates):
    """Save user profile updates into the patient_data structure"""
    try:
        patient_data = load_patient_data()
        if not patient_data:
            initialize_session()
            patient_data = session.get('patient_data', {})
        
        # Ensure user_profile exists
        if 'user_profile' not in patient_data:
            patient_data['user_profile'] = {
                'login_history': [],
                'last_updated': datetime.now().isoformat(),
                'login_count': 0
            }
        
        # Update the user profile section
        patient_data['user_profile'].update(profile_updates)
        patient_data['user_profile']['last_updated'] = datetime.now().isoformat()
        
        # Save the updated patient data
        return save_patient_data(patient_data)
    except Exception as e:
        print(f"ERROR: Failed to save user profile to patient data: {str(e)}")
        return False

def load_user_profile_from_patient_data():
    """Load user profile data from patient_data structure"""
    try:
        patient_data = load_patient_data()
        if patient_data and 'user_profile' in patient_data:
            return patient_data['user_profile']
        else:
            return {
                'login_history': [],
                'last_updated': datetime.now().isoformat(),
                'login_count': 0
            }
    except Exception as e:
        print(f"ERROR: Failed to load user profile from patient data: {str(e)}")
        return {}

def update_user_profile_in_patient_data(updates):
    """Update specific fields in user profile within patient_data"""
    try:
        profile = load_user_profile_from_patient_data()
        profile.update(updates)
        profile['last_updated'] = datetime.now().isoformat()
        return save_user_profile_to_patient_data(profile)
    except Exception as e:
        print(f"ERROR: Failed to update user profile in patient data: {str(e)}")
        return False

def get_current_user_info():
    """Get current user information from session and patient_data"""
    user_info = {
        'username': session.get('username', 'Anonymous'),
        'user_type': session.get('user_type', 'medical_operator'),
        'preferred_language': session.get('preferred_language', 'english'),
        'session_id': session.get('session_id'),
        'login_time': session.get('login_time')
    }
    
    # Try to get additional info from patient_data file
    patient_data = load_patient_data()
    if patient_data and 'user_profile' in patient_data:
        profile = patient_data['user_profile']
        user_info.update({
            'created_at': patient_data.get('created_at'),
            'last_updated': profile.get('last_updated'),
            'login_count': profile.get('login_count', 0)
        })
    
    return user_info

# Error handlers for AJAX requests
@app.errorhandler(404)
def not_found_error(error):
    # Handle favicon requests and other 404s gracefully
    if request.path == '/favicon.ico':
        return '', 204  # No content response for favicon
    if request.is_json or request.path.startswith('/save') or request.path.startswith('/generate'):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404
    return redirect('/')  # Redirect to home page instead of using missing 404.html

@app.errorhandler(500)
def internal_error(error):
    if request.is_json or request.path.startswith('/save') or request.path.startswith('/generate'):
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    if request.is_json or request.path.startswith('/save') or request.path.startswith('/generate'):
        return jsonify({'success': False, 'error': str(e)}), 500
    # For non-AJAX requests, let Flask handle it normally
    raise e

def initialize_session():
    """Initialize comprehensive medical session"""
    try:
        if 'patient_data' not in session:
            print("Initializing new patient session")
            session['patient_data'] = {
                'case_category': {},         # Step 1: Case category (accident/illness)
                'registration': {},          # Step 2: Patient registration
                'vitals': {},               # Step 3: Vital signs
                'follow_up_questions': {},  # Step 4: Removed - was LLM-generated follow-up
                'complaints': {},           # Step 5: Open-ended complaints
                'complaint_analysis': {},   # Step 6: LLM complaint analysis
                'diagnosis': {},            # Step 7: Final ICD diagnosis
                'session_id': datetime.now().isoformat(),
                'username': session.get('username', 'Anonymous'),
                'user_type': session.get('user_type', 'medical_operator'),
                'preferred_language': session.get('preferred_language', 'english'),
                'step_completed': 0,
                'created_at': datetime.now().isoformat(),
                'data_timestamps': {},       # Track when each step's data was last modified
                'llm_timestamps': {},        # Track when LLM responses were generated
                'user_profile': {            # User profile information
                    'login_history': [],
                    'last_updated': datetime.now().isoformat(),
                    'login_count': 0
                }
            }
        else:
            print("Using existing patient session")
            # Update user information in existing session if it's changed
            session['patient_data']['username'] = session.get('username', 'Anonymous')
            session['patient_data']['user_type'] = session.get('user_type', 'medical_operator')
            session['patient_data']['preferred_language'] = session.get('preferred_language', 'english')
            
            # Ensure user_profile exists in existing data
            if 'user_profile' not in session['patient_data']:
                session['patient_data']['user_profile'] = {
                    'login_history': [],
                    'last_updated': datetime.now().isoformat(),
                    'login_count': 0
                }
    except Exception as e:
        print(f"Error in initialize_session: {str(e)}")
        session['patient_data'] = {
            'registration': {},
            'vitals': {},
            'follow_up_questions': {},
            'complaints': {},
            'complaint_analysis': {},
            'diagnosis': {},
            'session_id': datetime.now().isoformat(),
            'username': session.get('username', 'Anonymous'),
            'step_completed': 0,
            'created_at': datetime.now().isoformat(),
            'data_timestamps': {},
            'llm_timestamps': {}
        }

def validate_session_step(required_step):
    """Validate if user has completed required steps using file storage"""
    try:
        print(f"DEBUG: Validating session for required step {required_step}")
        patient_data = load_patient_data()
        if not patient_data:
            print(f"ERROR: Session validation failed: no patient data found")
            print(f"DEBUG: Session ID: {session.get('session_id', 'No session ID')}")
            return False
        
        current_step = patient_data.get('step_completed', 0)
        result = current_step >= required_step
        print(f"DEBUG: Session validation for step {required_step}: {result} (current step: {current_step})")
        print(f"DEBUG: Patient data keys: {list(patient_data.keys())}")
        return result
    except Exception as e:
        print(f"ERROR: Error in validate_session_step: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def needs_llm_regeneration(step_number):
    """Check if LLM regeneration is needed based on data changes"""
    if 'patient_data' not in session:
        return True
    
    data_timestamps = session['patient_data'].get('data_timestamps', {})
    llm_timestamps = session['patient_data'].get('llm_timestamps', {})
    
    # Always regenerate if no LLM response exists for this step
    if step_number not in llm_timestamps:
        return True
    
    llm_time = llm_timestamps.get(step_number)
    
    # Check if any prerequisite step data has changed since LLM response was generated
    prerequisite_steps = {
        4: [1, 2, 3],        # Step 4: REMOVED - was depend on case category, registration and vitals
        5: [1, 2, 3, 4],     # Step 5 depends on case category, registration, vitals, and follow-up
        6: [1, 2, 3, 4, 5],  # Step 6 depends on all previous steps
        7: [1, 2, 3, 4, 5, 6] # Step 7 depends on all previous steps
    }
    
    for prereq_step in prerequisite_steps.get(step_number, []):
        if prereq_step in data_timestamps:
            data_time = data_timestamps[prereq_step]
            if data_time > llm_time:
                print(f"LLM regeneration needed for step {step_number}: prerequisite step {prereq_step} data changed")
                return True
    
    return False

def update_data_timestamp(step_number):
    """Update timestamp when step data is modified using file storage"""
    try:
        patient_data = load_patient_data()
        if not patient_data:
            patient_data = {'created_at': datetime.now().isoformat()}
        
        if 'data_timestamps' not in patient_data:
            patient_data['data_timestamps'] = {}
        
        # Ensure step_number is always stored as string for JSON serialization
        patient_data['data_timestamps'][str(step_number)] = datetime.now().isoformat()
        save_patient_data(patient_data)
        print(f"Updated data timestamp for step {step_number}")
    except Exception as e:
        print(f"Error updating data timestamp for step {step_number}: {str(e)}")

def update_llm_timestamp(step_number):
    """Update timestamp when LLM response is generated using file storage"""
    try:
        patient_data = load_patient_data()
        if not patient_data:
            patient_data = {'created_at': datetime.now().isoformat()}
        
        if 'llm_timestamps' not in patient_data:
            patient_data['llm_timestamps'] = {}
        
        # Ensure step_number is always stored as string for JSON serialization
        patient_data['llm_timestamps'][str(step_number)] = datetime.now().isoformat()
        save_patient_data(patient_data)
        print(f"Updated LLM timestamp for step {step_number}")
    except Exception as e:
        print(f"Error updating LLM timestamp for step {step_number}: {str(e)}")

def call_gpt4(prompt, context_data=None):
    """Call GPT-4 API with medical expertise"""
    try:
        # Load system prompt from external file
        system_prompt = load_prompt("medical_assistant_system")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        if context_data:
            context_text = f"Patient Context: {json.dumps(context_data, indent=2)}"
            messages.append({"role": "user", "content": context_text})
        
        # Set the API key if not already set
        # Get API key
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("WARNING: OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
            raise Exception("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
        
        print(f"DEBUG: Using API key: {api_key[:15]}...{api_key[-4:]}")
        print(f"Making API call to GPT-4 with {len(messages)} messages")
        
        # Create a fresh OpenAI client to ensure we're using the correct API key
        from openai import OpenAI
        fresh_client = OpenAI(api_key=api_key)
        
        # Use the new OpenAI API format (v1.0.0+)
        response = fresh_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=messages,
            max_tokens=2000,
            temperature=0.3
        )
        
        result = response.choices[0].message.content
        print(f"GPT-4 response received successfully: {len(result)} characters")
        return result
        
    except Exception as e:
        print(f"Error calling GPT-4: {str(e)}")
        raise e

def calculate_bmi(height, weight, height_unit='cm', weight_unit='kg'):
    """Calculate BMI from height and weight"""
    try:
        height_val = float(height)
        weight_val = float(weight)
        
        # Convert to metric if needed
        if height_unit == 'inches':
            height_val = height_val * 2.54
        if weight_unit == 'lbs':
            weight_val = weight_val * 0.453592
            
        # Calculate BMI
        height_m = height_val / 100
        bmi = weight_val / (height_m ** 2)
        return round(bmi, 1)
    except:
        return None

def generate_fallback_analysis(patient_data):
    """Generate fallback analysis when GPT-4 fails"""
    complaint_text = ""
    if patient_data.get('complaints'):
        complaint_text = patient_data['complaints'].get('raw_text', '')
    
    # Extract basic labels from complaint text
    basic_labels = []
    common_symptoms = ['pain', 'fever', 'headache', 'nausea', 'vomiting', 'fatigue', 'dizziness', 'cough', 'chest pain', 'abdominal pain']
    
    for symptom in common_symptoms:
        if symptom.lower() in complaint_text.lower():
            basic_labels.append({
                "label": symptom.capitalize(),
                "primary": symptom in ['pain', 'fever', 'headache'],
                "extracted_from": "Patient complaint text",
                "clinical_significance": f"{symptom.capitalize()} requires clinical evaluation"
            })
    
    if not basic_labels:
        basic_labels.append({
            "label": "General symptoms",
            "primary": True,
            "extracted_from": "Patient complaint text",
            "clinical_significance": "Patient-reported symptoms require medical assessment"
        })
    
    # Generate questions with proper radio button options
    questions = []
    for i, label in enumerate(basic_labels[:8]):  # Limit to 8 questions
        if 'pain' in label['label'].lower():
            questions.append({
                "question": f"How would you describe the intensity of your {label['label'].lower()}?",
                "purpose": "Assess pain severity for clinical evaluation",
                "category": "symptom_analysis",
                "options": [
                    {"value": "mild", "text": "Mild (1-3 out of 10)", "clinical_significance": "Low intensity pain"},
                    {"value": "moderate", "text": "Moderate (4-6 out of 10)", "clinical_significance": "Moderate pain affecting daily activities"},
                    {"value": "severe", "text": "Severe (7-8 out of 10)", "clinical_significance": "High intensity pain requiring attention"},
                    {"value": "extreme", "text": "Extreme (9-10 out of 10)", "clinical_significance": "Severe pain requiring immediate care"}
                ]
            })
        elif 'fever' in label['label'].lower():
            questions.append({
                "question": "How long have you had fever symptoms?",
                "purpose": "Determine fever duration for diagnosis",
                "category": "symptom_analysis",
                "options": [
                    {"value": "hours", "text": "A few hours", "clinical_significance": "Acute onset fever"},
                    {"value": "1-2days", "text": "1-2 days", "clinical_significance": "Recent onset fever"},
                    {"value": "3-7days", "text": "3-7 days", "clinical_significance": "Ongoing fever requiring evaluation"},
                    {"value": "week_plus", "text": "More than a week", "clinical_significance": "Prolonged fever needs investigation"}
                ]
            })
        else:
            questions.append({
                "question": f"How often do you experience {label['label'].lower()}?",
                "purpose": "Assess symptom frequency",
                "category": "symptom_analysis",
                "options": [
                    {"value": "constant", "text": "Constantly", "clinical_significance": "Persistent symptom"},
                    {"value": "frequent", "text": "Several times a day", "clinical_significance": "Frequent occurrence"},
                    {"value": "occasional", "text": "Occasionally", "clinical_significance": "Intermittent symptom"},
                    {"value": "rare", "text": "Rarely", "clinical_significance": "Infrequent occurrence"}
                ]
            })
    
    return {
        "complaint_labels": basic_labels,
        "features_for_labels": [
            {
                "label": label["label"],
                "features": [
                    {
                        "feature": "Presence",
                        "value": "Present",
                        "clinical_relevance": "Patient reports this symptom"
                    },
                    {
                        "feature": "Severity",
                        "value": "To be determined",
                        "clinical_relevance": "Severity assessment needed"
                    }
                ]
            } for label in basic_labels
        ],
        "feature_label_matrix": [
            {
                "feature": "Patient-reported symptoms",
                "associated_labels": [label["label"] for label in basic_labels],
                "strength": "moderate",
                "diagnostic_value": "Self-reported symptoms provide initial assessment direction"
            }
        ],
        "correlated_labels": [
            {
                "primary_label": basic_labels[0]["label"] if basic_labels else "General symptoms",
                "correlated_label": basic_labels[1]["label"] if len(basic_labels) > 1 else "Associated symptoms",
                "correlation_type": "commonly_associated",
                "clinical_significance": "Symptoms often present together in various conditions",
                "example": "Multiple symptoms may indicate systemic condition requiring evaluation"
            }
        ],
        "correlated_questions": questions,
        "medical_imaging_recommendations": [
            {
                "imaging_type": "Blood test",
                "reason": "Basic laboratory workup for symptom evaluation",
                "urgency": "routine",
                "uploadable": True,
                "target_labels": [label["label"] for label in basic_labels]
            },
            {
                "imaging_type": "X-ray",
                "reason": "Imaging if physical symptoms suggest structural issues",
                "urgency": "routine",
                "uploadable": True,
                "target_labels": [label["label"] for label in basic_labels if 'pain' in label["label"].lower()]
            }
        ]
    }

def generate_fallback_icd_diagnosis(patient_data):
    """Generate fallback ICD diagnosis when GPT-4 fails"""
    
    # Get basic patient info for diagnosis context
    registration = patient_data.get('registration', {})
    age = registration.get('calculated_age') or registration.get('age', 'Unknown')
    gender = registration.get('gender', 'Unknown')
    vitals = patient_data.get('vitals', {})
    complaints = patient_data.get('complaints', {})
    
    # Basic ICD codes based on common presentations
    fallback_diagnoses = [
        {
            "rank": 1,
            "icd_code": "Z00.00",
            "disease_name": "Encounter for general adult medical examination without abnormal findings",
            "common_name": "General health checkup",
            "confidence_percentage": 70,
            "evidence_score": "MEDIUM",
            "supporting_data": ["Patient presenting for medical assessment"],
            "icd_category": "General Medical",
            "clinical_reasoning": "Default diagnosis for general medical evaluation without specific abnormal findings"
        },
        {
            "rank": 2,
            "icd_code": "R50.9",
            "disease_name": "Fever, unspecified",
            "common_name": "Fever of unknown origin",
            "confidence_percentage": 50,
            "evidence_score": "LOW",
            "supporting_data": ["General symptom assessment"],
            "icd_category": "Symptoms and Signs",
            "clinical_reasoning": "Common presenting symptom requiring evaluation"
        },
        {
            "rank": 3,
            "icd_code": "R06.02",
            "disease_name": "Shortness of breath",
            "common_name": "Difficulty breathing",
            "confidence_percentage": 45,
            "evidence_score": "LOW",
            "supporting_data": ["Respiratory symptom evaluation"],
            "icd_category": "Respiratory",
            "clinical_reasoning": "Common respiratory complaint"
        }
    ]
    
    # Adjust based on actual patient data if available
    if complaints.get('raw_text'):
        complaint_text = complaints['raw_text'].lower()
        if 'pain' in complaint_text:
            fallback_diagnoses.insert(1, {
                "rank": 2,
                "icd_code": "R52",
                "disease_name": "Pain, unspecified",
                "common_name": "General pain",
                "confidence_percentage": 60,
                "evidence_score": "MEDIUM",
                "supporting_data": ["Patient reports pain symptoms"],
                "icd_category": "Symptoms and Signs",
                "clinical_reasoning": "Patient-reported pain requiring evaluation"
            })
    
    return {
        "icd_diagnoses": fallback_diagnoses[:10],  # Max 10 diagnoses
        "primary_icd": {
            "icd_code": fallback_diagnoses[0]["icd_code"],
            "disease_name": fallback_diagnoses[0]["disease_name"],
            "confidence": f"{fallback_diagnoses[0]['confidence_percentage']}%",
            "rationale": "Most appropriate diagnosis based on available information"
        },
        "system_analysis": {
            "total_data_points": "Limited data available for analysis",
            "key_indicators": ["Basic patient presentation", "General medical assessment"],
            "excluded_codes": ["Specific disease codes pending additional evaluation"],
            "diagnostic_certainty": "Low - requires additional clinical assessment"
        },
        "icd_coding_notes": {
            "coding_methodology": "Conservative approach using general diagnostic codes",
            "differential_approach": "Broad differential pending additional information",
            "limitations": "Limited patient data available for specific diagnosis"
        }
    }

def save_step_based_patient_data(step_number, form_data, ai_data=None, files_data=None, custom_medical_images=None):
    """
    Save all patient data in a highly organized step-based structure
    Each step has its own section with all values saved (user input, AI-generated, dynamic)
    One-to-one mapping between steps and data for easy reference
    
    OVERWRITE LOGIC:
    - If a field is provided in new data, it replaces the existing value
    - If a field is not provided (None, empty string, or missing), it's removed from storage
    - This ensures clean data without stale values
    """
    try:
        # Load existing data or create new with proper structure
        patient_data = load_patient_data() or {}
        
        # Initialize with metadata if new file
        if not patient_data:
            patient_data = {
                'session_info': {
                    'session_id': session.get('session_id', str(uuid.uuid4())),
                    'username': session.get('username', 'Anonymous'),
                    'created_at': datetime.now().isoformat(),
                    'last_updated': datetime.now().isoformat()
                },
                'step1': {},
                'step2': {},
                'step3': {},
                'step4': {},
                'step5': {},
                'step6': {},
                'step7': {},
                'step_completion_status': {}
            }
        
        # Ensure session_info exists even in existing files (backward compatibility)
        if 'session_info' not in patient_data:
            patient_data['session_info'] = {
                'session_id': session.get('session_id', str(uuid.uuid4())),
                'username': session.get('username', 'Anonymous'),
                'created_at': patient_data.get('created_at', datetime.now().isoformat()),
                'last_updated': datetime.now().isoformat()
            }
        
        # Migrate old data structure to new step-based structure (backward compatibility)
        if 'case_category' in patient_data and 'step1' not in patient_data:
            print("🔄 Migrating old data structure to new step-based format...")
            # Move old data to appropriate steps
            old_case_category = patient_data.pop('case_category', {})
            old_registration = patient_data.pop('registration', {})
            old_vitals = patient_data.pop('vitals', {})
            old_follow_up = patient_data.pop('follow_up_questions', {})
            old_complaints = patient_data.pop('complaints', {})
            old_analysis = patient_data.pop('complaint_analysis', {})
            old_diagnosis = patient_data.pop('diagnosis', {})
            
            # Preserve other fields in session_info
            for key in ['username', 'user_type', 'preferred_language', 'step_completed', 'data_timestamps', 'llm_timestamps']:
                if key in patient_data:
                    if key in ['username', 'user_type', 'preferred_language']:
                        patient_data['session_info'][key] = patient_data.pop(key)
                    else:
                        patient_data[key] = patient_data.get(key)
        
        # Ensure all step sections exist
        for step_num in range(1, 8):
            if f'step{step_num}' not in patient_data:
                patient_data[f'step{step_num}'] = {}
        
        if 'step_completion_status' not in patient_data:
            patient_data['step_completion_status'] = {}
        
        # Clean function to remove any existing suffixes before saving
        def clean_value(value):
            """Remove -A and -O suffixes if they exist"""
            if isinstance(value, str) and (value.endswith('-A') or value.endswith('-O')):
                return value[:-2]
            return value
        
        def is_valid_value(value, field_name=None):
            """Check if a value should be saved (not None, not empty string, not just whitespace, not 'none' values for certain fields)"""
            print(f"🔍 is_valid_value called: field='{field_name}', value='{value}'")
            
            if value is None:
                print(f"❌ REJECTED: {field_name} - value is None")
                return False
            if isinstance(value, str):
                # Convert to lowercase for comparison
                clean_value = value.strip().lower()
                print(f"🔤 Cleaned value: '{clean_value}'")
                
                # Don't save empty strings or whitespace
                if not clean_value:
                    print(f"❌ REJECTED: {field_name} - empty string")
                    return False
                
                # Field-specific filtering for medical conditions that use "none"/"no" to indicate absence
                # Note: For fields like lung_congestion, "none" is a valid selection meaning "no congestion"
                text_input_medical_fields = [
                    'infection_type', 'medical_condition', 'symptoms',
                    'complications', 'allergies', 'current_medications', 'ecg_findings'
                ]
                
                if field_name and field_name in text_input_medical_fields:
                    print(f"🏥 Text medical field detected: {field_name}")
                    # For text input medical condition fields, "none", "no", "normal" etc. mean "no condition present"
                    if clean_value in ['none', 'no', 'normal', 'n/a', 'na', 'not applicable', 'nil', 'nothing']:
                        print(f"❌ REJECTED: {field_name} - medical condition 'none' value: '{clean_value}'")
                        return False
                
                # Special handling for ECG availability
                if field_name == 'ecg_available' and clean_value == 'no':
                    print(f"✅ ACCEPTED: {field_name} - ECG 'no' is valid")
                    # For ECG availability, "no" is a valid response meaning "ECG not available"
                    return True
                    
            if isinstance(value, dict) and not value:
                print(f"❌ REJECTED: {field_name} - empty dict")
                return False
            if isinstance(value, list) and not value:
                print(f"❌ REJECTED: {field_name} - empty list")
                return False
            
            print(f"✅ ACCEPTED: {field_name} - value passed all checks")
            return True
        
        # Clean and filter form data - only save valid values
        cleaned_form_data = {}
        for key, value in form_data.items():
            print(f"🔍 FILTERING: {key} = '{value}'")
            if is_valid_value(value, key):
                cleaned_form_data[key] = clean_value(value)
                print(f"✅ KEPT: {key} = '{clean_value(value)}'")
            else:
                print(f"❌ REMOVED: {key} = '{value}' (filtered out by is_valid_value)")
        
        print(f"📝 FINAL CLEANED DATA: {cleaned_form_data}")
        
        # Clean and filter AI data - only save valid values
        cleaned_ai_data = {}
        if ai_data:
            print(f"🔍 DEBUG: Processing ai_data with keys: {list(ai_data.keys())}")
            for key, value in ai_data.items():
                print(f"🔍 DEBUG: Processing ai_data field: {key} = {value}")
                if is_valid_value(value, key):
                    cleaned_ai_data[key] = clean_value(value)
                    print(f"✅ DEBUG: Kept ai_data field: {key}")
                else:
                    print(f"❌ DEBUG: Rejected ai_data field: {key}")
        else:
            print(f"⚠️ DEBUG: No ai_data provided to save")
        
        # Clean and filter files data - only save valid values
        cleaned_files_data = {}
        if files_data:
            for key, value in files_data.items():
                if is_valid_value(value, key):
                    cleaned_files_data[key] = value
        
        print(f"📝 OVERWRITE MODE - Step {step_number} data being completely replaced")
        print(f"   Form fields being saved: {list(cleaned_form_data.keys())}")
        print(f"   AI fields being saved: {list(cleaned_ai_data.keys())}")
        print(f"   File fields being saved: {list(cleaned_files_data.keys())}")
        
        # Update session metadata
        patient_data['session_info']['last_updated'] = datetime.now().isoformat()
        patient_data['session_info']['username'] = session.get('username', 'Anonymous')
        if f'step{step_number}' not in patient_data['session_info']:
            patient_data['session_info'][f'highest_step_completed'] = max(
                patient_data['session_info'].get('highest_step_completed', 0), 
                step_number
            )
        
        # STEP 1: Case Category and Basic Info
        if step_number == 1:
            # Completely replace step1 data with new data (overwrite mode)
            patient_data['step1'] = {
                'step_name': 'Case Category Selection',
                'form_data': cleaned_form_data,
                'ai_generated_data': cleaned_ai_data,
                'files_uploaded': cleaned_files_data,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'user_input',
                'step_completed': True
            }
            print(f"✅ Step 1 data completely overwritten")
        
        # STEP 2: Patient Registration
        elif step_number == 2:
            # Completely replace step2 data with new data (overwrite mode)
            patient_data['step2'] = {
                'step_name': 'Patient Registration',
                'form_data': cleaned_form_data,
                'ai_generated_data': cleaned_ai_data,
                'files_uploaded': cleaned_files_data,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'user_input_and_extraction',
                'step_completed': True
            }
            print(f"✅ Step 2 data completely overwritten")
        
        # STEP 3: Vital Signs and Medical Photos
        elif step_number == 3:
            # Process custom medical images
            cleaned_custom_images = []
            if custom_medical_images:
                for img_data in custom_medical_images:
                    if isinstance(img_data, dict) and img_data.get('filename'):
                        cleaned_custom_images.append(img_data)
                print(f"📸 Processed {len(cleaned_custom_images)} custom medical images")
            
            # Completely replace step3 data with new data (overwrite mode)
            patient_data['step3'] = {
                'step_name': 'Vital Signs & Medical Photos',
                'form_data': cleaned_form_data,
                'ai_generated_data': cleaned_ai_data,
                'files_uploaded': cleaned_files_data,
                'custom_medical_images': cleaned_custom_images,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'user_input_and_analysis',
                'step_completed': True
            }
            print(f"✅ Step 3 data completely overwritten with {len(cleaned_custom_images)} custom medical images")
        
        # STEP 4: Medical Records, Contact & Medications
        elif step_number == 4:
            # Completely replace step4 data with new data (overwrite mode)
            patient_data['step4'] = {
                'step_name': 'Medical Records & Contact Information',
                'form_data': cleaned_form_data,
                'ai_generated_data': cleaned_ai_data,
                'files_uploaded': cleaned_files_data,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'user_input_and_analysis',
                'step_completed': True
            }
            print(f"✅ Step 4 data completely overwritten")
        
        # STEP 5: Complaints and Symptoms
        elif step_number == 5:
            # Completely replace step5 data with new data (overwrite mode)
            patient_data['step5'] = {
                'step_name': 'Complaints & Symptoms',
                'form_data': cleaned_form_data,
                'ai_generated_data': cleaned_ai_data,
                'files_uploaded': cleaned_files_data,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'user_input_and_ai_analysis',
                'step_completed': True
            }
            print(f"✅ Step 5 data completely overwritten")
        
        # STEP 6: Analysis and Diagnosis
        elif step_number == 6:
            # Completely replace step6 data with new data (overwrite mode)
            patient_data['step6'] = {
                'step_name': 'Analysis & Diagnosis',
                'form_data': cleaned_form_data,
                'ai_generated_data': cleaned_ai_data,
                'files_uploaded': cleaned_files_data,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'ai_analysis',
                'step_completed': True
            }
            print(f"✅ Step 6 data completely overwritten")
        
        # STEP 7: ICD11 Code Generation and Analysis
        elif step_number == 7:
            # For step7, merge form_data to preserve patient contact information
            existing_step7 = patient_data.get('step7', {})
            existing_form_data = existing_step7.get('form_data', {})
            
            # Merge existing form data with new form data
            merged_form_data = existing_form_data.copy()
            merged_form_data.update(cleaned_form_data)
            
            print(f"🔄 Step 7 - Merging form data:")
            print(f"   Existing: {list(existing_form_data.keys())}")
            print(f"   New: {list(cleaned_form_data.keys())}")
            print(f"   Merged: {list(merged_form_data.keys())}")
            
            patient_data['step7'] = {
                'step_name': 'ICD11 Code Generation & Analysis',
                'form_data': merged_form_data,
                'ai_generated_data': cleaned_ai_data,
                'files_uploaded': cleaned_files_data,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'icd_generation',
                'step_completed': True
            }
            print(f"✅ Step 7 data merged successfully")
        
        # Update step completion status
        step_key = f'step{step_number}'
        patient_data['step_completion_status'][step_key] = {
            'completed': True,
            'timestamp': datetime.now().isoformat(),
            'form_fields_count': len(cleaned_form_data),
            'ai_fields_count': len(cleaned_ai_data),
            'files_count': len(cleaned_files_data)
        }
        
        # Update the step_completed field that validate_session_step checks
        current_step_completed = patient_data.get('step_completed', 0)
        patient_data['step_completed'] = max(current_step_completed, step_number)
        print(f"✅ Updated step_completed to {patient_data['step_completed']}")
        
        # Save to file with overwrite protection
        success = save_patient_data(patient_data)
        if success:
            print(f"✅ Step-based data saved successfully for step {step_number}")
            print(f"   📋 Form fields: {len(cleaned_form_data)}")
            print(f"   🤖 AI fields: {len(cleaned_ai_data)}")
            print(f"   📎 Files: {len(cleaned_files_data)}")
            return True
        else:
            print(f"❌ Failed to save step-based data for step {step_number}")
            return False
            
    except Exception as e:
        print(f"❌ Error in save_step_based_patient_data: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def get_step_data(step_number):
    """
    Retrieve data for a specific step from the step-based structure
    """
    try:
        patient_data = load_patient_data()
        if not patient_data:
            return {}
        
        step_key = f'step{step_number}'
        if step_key in patient_data:
            return patient_data[step_key]
        
        return {}
    except Exception as e:
        print(f"Error retrieving step {step_number} data: {str(e)}")
        return {}

def get_all_patient_data():
    """
    Retrieve all patient data in organized step-based format
    """
    try:
        patient_data = load_patient_data()
        if not patient_data:
            return {}
        
        organized_data = {
            'session_info': patient_data.get('session_info', {}),
            'steps': {},
            'completion_status': patient_data.get('step_completion_status', {})
        }
        
        # Collect all step data (1-6 only, step 7 removed)
        for step_num in range(1, 7):
            step_key = f'step{step_num}'
            if step_key in patient_data:
                organized_data['steps'][step_key] = patient_data[step_key]
        
        return organized_data
    except Exception as e:
        print(f"Error retrieving all patient data: {str(e)}")
        return {}

def save_comprehensive_patient_data(step_number, form_data, ai_data=None, files_data=None):
    """
    Legacy function that now calls the new step-based save function
    """
    return save_step_based_patient_data(step_number, form_data, ai_data, files_data)

# Routes
@app.route('/')
def home():
    # Always redirect to login page - clear any existing sessions first
    session.clear()
    return redirect('/login')

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    # POST request - process login
    username = request.form.get('username', '').strip()
    user_type = request.form.get('user_type', '').strip()
    preferred_language = request.form.get('preferred_language', '').strip()
    
    # Validation
    if not username:
        return render_template('login.html', error_message='Please enter a username')
    
    if len(username) < 2:
        return render_template('login.html', error_message='Username must be at least 2 characters long')
    
    if not user_type:
        return render_template('login.html', error_message='Please select your role')
    
    if user_type not in ['medical_operator', 'referring_doctor', 'panelist_doctor']:
        return render_template('login.html', error_message='Invalid user type selected')
    
    if not preferred_language:
        return render_template('login.html', error_message='Please select your preferred language')
    
    if preferred_language not in ['english', 'french', 'hindi', 'tamil']:
        return render_template('login.html', error_message='Invalid language selected')
    
    # Store user information in session
    session['username'] = username
    session['user_type'] = user_type
    session['preferred_language'] = preferred_language
    session['login_time'] = datetime.now().isoformat()
    session.permanent = True
    
    # Initialize session to create patient_data structure
    initialize_session()
    
    # Clean up any old separate user profile files
    cleanup_old_user_profile_files()
    
    # Load existing profile to preserve login history
    existing_profile = load_user_profile_from_patient_data()
    login_history = existing_profile.get('login_history', [])
    login_history.append(datetime.now().isoformat())
    
    # Save user profile to patient_data structure
    profile_data = {
        'username': username,
        'user_type': user_type,
        'preferred_language': preferred_language,
        'session_id': session.get('session_id'),
        'created_at': existing_profile.get('created_at', datetime.now().isoformat()),
        'last_updated': datetime.now().isoformat(),
        'login_history': login_history,
        'login_count': len(login_history)
    }
    
    save_user_profile_to_patient_data(profile_data)
    
    print(f"✅ User logged in successfully:")
    print(f"   - Username: {username}")
    print(f"   - Role: {user_type}")
    print(f"   - Language: {preferred_language}")
    print(f"   - Session ID: {session.get('session_id')}")
    print(f"   - Profile integrated into patient data file")
    
    # Redirect panelist doctors to their specialized dashboard
    if user_type == 'panelist_doctor':
        return redirect('/p_step1')
    else:
        return redirect('/dashboard')

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard after login"""
    initialize_session()
    return render_template('index.html')

@app.route('/p_step1')
@login_required
def panelist_dashboard():
    """Panelist doctor dashboard showing pending review cases"""
    # Check if user is actually a panelist doctor
    if session.get('user_type') != 'panelist_doctor':
        return redirect('/dashboard')
    
    try:
        connection = get_sqlite_connection()
        if connection:
            cursor = connection.cursor()
            
            # Fetch all cases with pending_review status including created date
            cursor.execute("""
                SELECT case_number, status, details, created_at 
                FROM cases 
                WHERE status = 'pending_review'
                ORDER BY created_at DESC
            """)
            
            cases = cursor.fetchall()
            connection.close()
            
            # Process cases for display with masked details
            processed_cases = []
            for case in cases:
                # Format the created_at date for display
                created_date = case[3] if case[3] else 'Unknown'
                if created_date != 'Unknown':
                    # Parse and format the date (SQLite returns ISO format)
                    try:
                        from datetime import datetime
                        if 'T' in created_date:
                            dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                        else:
                            dt = datetime.strptime(created_date, '%Y-%m-%d %H:%M:%S')
                        created_date = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        created_date = str(case[3])[:16]  # Fallback to first 16 chars
                
                processed_cases.append({
                    'case_number': case[0],
                    'status': case[1],
                    'masked_details': 'X' * 10,  # Show only XXXXXXXXXX as requested
                    'created_date': created_date
                })
            
            return render_template('p_step1.html', cases=processed_cases)
        else:
            # If no database connection, show empty list
            return render_template('p_step1.html', cases=[], error="Database connection failed")
            
    except Exception as e:
        print(f"❌ Error fetching cases for panelist: {e}")
        return render_template('p_step1.html', cases=[], error="Failed to load cases")

@app.route('/p_step2/<case_number>')
@login_required
def view_case_details(case_number):
    """View detailed case information for panelist doctors"""
    # Check if user is actually a panelist doctor
    if session.get('user_type') != 'panelist_doctor':
        return redirect('/dashboard')
    
    try:
        connection = get_sqlite_connection()
        if connection:
            cursor = connection.cursor()
            
            # Fetch the specific case
            cursor.execute("""
                SELECT case_number, status, details, created_at 
                FROM cases 
                WHERE case_number = ?
            """, (case_number,))
            
            case_data = cursor.fetchone()
            connection.close()
            
            if not case_data:
                return render_template('p_step2.html', error="Case not found", case_number=case_number)
            
            # Parse the case details
            try:
                import json
                case_details = json.loads(case_data[2])
                
                # Format the created date
                created_date = case_data[3] if case_data[3] else 'Unknown'
                if created_date != 'Unknown':
                    try:
                        from datetime import datetime
                        if 'T' in created_date:
                            dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                        else:
                            dt = datetime.strptime(created_date, '%Y-%m-%d %H:%M:%S')
                        created_date = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        created_date = str(case_data[3])[:16]
                
                # Extract structured data for display
                case_info = {
                    'case_number': case_data[0],
                    'status': case_data[1],
                    'created_date': created_date,
                    'raw_details': case_details,
                    # Clinical summary - try AI generated first, then fall back to form data
                    'clinical_summary': (
                        case_details.get('ai_generated_data', {}).get('clinical_summary') or 
                        case_details.get('form_data', {}).get('clinical_summary_edited') or 
                        case_details.get('ai_generated_data', {}).get('original_clinical_summary') or
                        'No clinical summary available'
                    ),
                    'icd_codes': case_details.get('ai_generated_data', {}).get('icd_codes_generated', []),
                    'elimination_history': case_details.get('ai_generated_data', {}).get('elimination_history', []),
                    'lab_tests': case_details.get('ai_generated_data', {}).get('recommended_lab_tests', []),
                    # Patient summary - try AI generated first, then build from available data
                    'patient_summary': (
                        case_details.get('ai_generated_data', {}).get('patient_data_summary') or 
                        build_patient_summary_fallback(case_details) or
                        'Patient summary not available - please review individual sections'
                    ),
                    'differential_questions': case_details.get('ai_generated_data', {}).get('differential_questions', []),
                    # Contact information - check both form_data and top-level
                    'patient_email': case_details.get('form_data', {}).get('patient_email') or case_details.get('patient_email', 'Not provided'),
                    'patient_phone': case_details.get('form_data', {}).get('patient_phone') or case_details.get('patient_phone', 'Not provided'),
                    'referring_doctor_id': case_details.get('form_data', {}).get('referring_doctor_id') or case_details.get('referring_doctor_id', 'Not available'),
                    'referring_doctor_name': case_details.get('form_data', {}).get('referring_doctor_name') or case_details.get('referring_doctor_name', 'Not available'),
                    'referring_doctor_phone': case_details.get('form_data', {}).get('referring_doctor_phone') or case_details.get('referring_doctor_phone', 'Not provided'),
                    'referring_doctor_email': case_details.get('form_data', {}).get('referring_doctor_email') or case_details.get('referring_doctor_email', 'Not provided'),
                    'referring_doctor_details': case_details.get('form_data', {}).get('referring_doctor_details') or case_details.get('referring_doctor_details', {})
                }
                
                return render_template('p_step2.html', case=case_info)
                
            except json.JSONDecodeError as e:
                print(f"❌ Error parsing case details JSON: {e}")
                return render_template('p_step2.html', error="Failed to parse case details", case_number=case_number)
        else:
            return render_template('p_step2.html', error="Database connection failed", case_number=case_number)
            
    except Exception as e:
        print(f"❌ Error fetching case details: {e}")
        return render_template('p_step2.html', error="Failed to load case details", case_number=case_number)

@app.route('/logout', methods=['POST'])
def logout():
    username = session.get('username', 'Unknown')
    session.clear()
    print(f"✅ User logged out: {username}")
    return redirect('/login')

# Session management routes
@app.route('/get_session_info')
@login_required
def get_session_info():
    initialize_session()
    patient_data = session.get('patient_data', {})
    return jsonify({
        'success': True,
        'step_completed': patient_data.get('step_completed', 0),
        'session_id': patient_data.get('session_id', '')
    })

@app.route('/clear_session', methods=['POST'])
def clear_session():
    session.clear()
    return jsonify({'success': True, 'message': 'Session cleared successfully'})

# Step 1: Case Category Selection
@app.route('/step1')
@login_required
def step1():
    # Clear all previous patient data when starting a new assessment
    clear_all_patient_data()
    initialize_session()
    return render_template('step1.html')

@app.route('/save_case_category', methods=['POST'])
@login_required
def save_case_category():
    try:
        print("✅ Starting save_case_category")
        print(f"   Session before initialize: {session.get('session_id', 'NO SESSION')}")
        
        initialize_session()
        
        print(f"   Session after initialize: {session.get('session_id', 'NO SESSION')}")
        
        # Get request data
        data = request.get_json()
        print(f"   Request data: {data}")
        
        case_category = data.get('case_category')
        case_description = data.get('case_description', '')
        
        print(f"   Case category: {case_category}")
        print(f"   Case description: {case_description}")
        
        if not case_category or case_category not in ['accident', 'illness']:
            print(f"❌ Invalid case category: {case_category}")
            return jsonify({'success': False, 'error': 'Invalid case category selected'})
        
        # Prepare form data for step-based saving
        form_data = {
            'case_category': case_category,
            'case_description': case_description if case_description else ''
        }
        
        print(f"   Form data prepared: {form_data}")
        
        # Use new step-based save function
        print("   Calling save_step_based_patient_data...")
        success = save_step_based_patient_data(
            step_number=1,
            form_data=form_data,
            ai_data={},
            files_data={}
        )
        
        print(f"   Save result: {success}")
        
        if not success:
            print("❌ save_step_based_patient_data returned False")
            return jsonify({'success': False, 'error': 'Failed to save case category data'})
        
        # Keep minimal data in session for navigation
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 1
        session.modified = True
        
        print(f"✅ Case category saved successfully: {case_category}")
        return jsonify({'success': True, 'message': 'Case category saved successfully'})
        
    except Exception as e:
        print(f"❌ Error in save_case_category: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to save case category: {str(e)}'})

def invalidate_downstream_steps(from_step):
    """Clear data from downstream steps when earlier step is modified"""
    try:
        patient_data = session.get('patient_data', {})
        
        if from_step <= 1:
            # Clear all downstream data from step 2 onwards
            patient_data['registration'] = {}
            patient_data['vitals'] = {}
            patient_data['follow_up_questions'] = {}
            patient_data['complaints'] = {}
            patient_data['complaint_analysis'] = {}
            patient_data['diagnosis'] = {}
        elif from_step <= 2:
            # Clear from step 3 onwards
            patient_data['vitals'] = {}
            patient_data['follow_up_questions'] = {}
            patient_data['complaints'] = {}
            patient_data['complaint_analysis'] = {}
            patient_data['diagnosis'] = {}
        elif from_step <= 3:
            # Clear from step 5 onwards (step 4 removed)
            patient_data['follow_up_questions'] = {}
            patient_data['complaints'] = {}
            patient_data['complaint_analysis'] = {}
            patient_data['diagnosis'] = {}
        elif from_step <= 4:
            # Clear from step 5 onwards
            patient_data['complaints'] = {}
            patient_data['complaint_analysis'] = {}
            patient_data['diagnosis'] = {}
        elif from_step <= 5:
            # Clear from step 6 onwards
            patient_data['complaint_analysis'] = {}
            patient_data['diagnosis'] = {}
        elif from_step <= 6:
            # Clear diagnosis only
            patient_data['diagnosis'] = {}
        
        # Reset step completed to current step
        patient_data['step_completed'] = from_step
        session.modified = True
        print(f"Invalidated downstream steps from step {from_step}")
    except Exception as e:
        print(f"Error invalidating downstream steps from step {from_step}: {str(e)}")

# Step 2: Patient Registration
@app.route('/step2')
@login_required
def step2():
    if not validate_session_step(1):
        return redirect('/')
    return render_template('step2.html')

# Global mapping for Action (A) and Outcome (O) categories for Step 2
STEP2_FIELD_CATEGORIES = {
    # Action fields (for documentation and doctor identification)
    'full_name': 'A',
    'address': 'A',
    'phone': 'A',
    'email': 'A',
    'language': 'A',
    'emergency_name': 'A',
    'emergency_relation': 'A',
    'emergency_phone': 'A',
    'marital_status': 'A',
    'education_level': 'A',
    'employment_status': 'A',
    'economic_status': 'A',
    'income_source': 'A',
    'family_history': 'A',
    'emr_existing': 'A',
    'emr_register': 'A',
    'insurance_doc': 'A',
    'vaccine_doc': 'A',
    'health_card': 'A',
    'aadhar_front': 'A',
    'aadhar_back': 'A',
    'aadhar_combined': 'A',
    
    # Outcome fields (required for diagnosis)
    'date_of_birth': 'O',  # For age calculation
    'calculated_age': 'O',
    'gender': 'O',
    'occupation': 'O',
    'occupation_detail': 'O',
    'diabetes': 'O',
    'hypertension': 'O',
    'asthma': 'O',
    'heart_disease': 'O'
}

def categorize_step2_data(form_data):
    """Categorize Step 2 data into Action and Outcome categories"""
    action_data = {}
    outcome_data = {}
    
    for field_name, value in form_data.items():
        category = STEP2_FIELD_CATEGORIES.get(field_name, 'A')  # Default to Action
        
        if category == 'A':
            action_data[field_name] = value
        else:
            outcome_data[field_name] = value
    
    return action_data, outcome_data

@app.route('/save_registration', methods=['POST'])
def save_registration():
    try:
        print("✅ Starting save_registration")
        initialize_session()
        
        # Validate that Step 1 (case category) is completed
        if not validate_session_step(1):
            return jsonify({'success': False, 'error': 'Please complete case category selection first'})
        
        # Check if this is a modification of existing data
        patient_data = load_patient_data()
        existing_step2 = get_step_data(2)
        is_modification = bool(existing_step2)
        
        # Collect all form data
        form_data = {}
        form_fields = [
            'full_name', 'date_of_birth', 'gender', 'address', 'phone', 'email',
            'language', 'emergency_name', 'emergency_relation', 'emergency_phone',
            'occupation', 'occupation_detail', 'marital_status', 'education_level',
            'employment_status', 'economic_status', 'income_source',
            'diabetes', 'hypertension', 'asthma', 'heart_disease', 'family_history',
            'calculated_age', 'lab_reports', 'medical_images', 'signaling_reports', 'other_medical_reports',
            'emr_existing', 'emr_register', 'currently_pregnant', 'pregnancy_month', 
            'recent_childbirth'
        ]
        
        for field in form_fields:
            value = request.form.get(field, '')
            if value:  # Only store non-empty values
                form_data[field] = value.strip()
        
        # Handle file uploads
        files_data = {}
        file_fields = ['aadhar_front', 'aadhar_back', 'aadhar_combined', 'insurance_doc', 'vaccine_doc', 'health_card']
        for field in file_fields:
            if field in request.files:
                file = request.files[field]
                if file and file.filename:
                    files_data[field] = {
                        'filename': file.filename,
                        'upload_timestamp': datetime.now().isoformat(),
                        'field_name': field,
                        'content_type': getattr(file, 'content_type', 'unknown')
                    }
                    print(f"📎 File uploaded for {field}: {file.filename}")
        
        # Collect AI data (like Aadhaar extraction, EMR analysis)
        ai_data = {}
        if 'aadhaar_extraction' in session.get('patient_data', {}).get('registration', {}):
            ai_data['aadhaar_extraction'] = session['patient_data']['registration']['aadhaar_extraction']
        if 'emr_insights' in session.get('patient_data', {}).get('registration', {}):
            ai_data['emr_insights'] = session['patient_data']['registration']['emr_insights']
        
        print(f"📋 Registration data collected: {len(form_data)} form fields")
        print(f"📎 Files uploaded: {len(files_data)}")
        print(f"🤖 AI data collected: {len(ai_data)}")
        
        # Use new step-based save function
        success = save_step_based_patient_data(
            step_number=2,
            form_data=form_data,
            ai_data=ai_data,
            files_data=files_data
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save registration data'})
        
        # If this is a modification, invalidate downstream steps
        if is_modification:
            invalidate_downstream_steps(2)
        
        # Keep minimal data in session for navigation
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 2
        session.modified = True
        
        print("✅ Registration saved successfully")
        return jsonify({
            'success': True, 
            'message': 'Registration completed successfully',
            'form_fields': len(form_data),
            'files_uploaded': len(files_data),
            'ai_data_fields': len(ai_data)
        })
        
    except Exception as e:
        print(f"❌ Error in save_registration: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to save registration: {str(e)}'})

# Helper function to get diagnosis-relevant data from Step 1
def get_step1_diagnosis_data():
    """Extract only diagnosis-relevant (Outcome) data from Step 1"""
    if 'patient_data' not in session or 'registration' not in session['patient_data']:
        return {}
    
    registration = session['patient_data']['registration']
    return registration.get('outcome_data', {})

@app.route('/analyze_emr', methods=['POST'])
def analyze_emr():
    """Analyze uploaded EMR document using LLM"""
    try:
        if 'emr_file' not in request.files:
            return jsonify({'success': False, 'error': 'No EMR file uploaded'})
        
        file = request.files['emr_file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Read file content
        file_content = file.read()
        file_type = file.content_type
        
        # Encode file content for API
        if file_type.startswith('image/'):
            # For images, use base64 encoding
            encoded_content = base64.b64encode(file_content).decode('utf-8')
            content_type = "image"
        elif file_type == 'application/pdf':
            # For PDFs, use base64 encoding (OpenAI can handle PDF analysis)
            encoded_content = base64.b64encode(file_content).decode('utf-8')
            content_type = "pdf"
        else:
            return jsonify({'success': False, 'error': 'Unsupported file type'})
        
        # Prepare LLM prompt for EMR analysis
        prompt = load_prompt("emr_analysis")

        # Make API call to OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "system", 
                    "content": load_prompt("emr_system")
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url" if content_type == "image" else "text",
                            "image_url": {
                                "url": f"data:{file_type};base64,{encoded_content}"
                            } if content_type == "image" else {"text": f"PDF Content (Base64): {encoded_content[:1000]}..."}
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        insights = response.choices[0].message.content.strip()
        
        # Store abbreviated EMR insights to reduce session size
        if 'patient_data' not in session:
            session['patient_data'] = {}
        if 'registration' not in session['patient_data']:
            session['patient_data']['registration'] = {}
        
        # Store only abbreviated insights to avoid session size issues
        abbreviated_insights = insights[:300] + "..." if len(insights) > 300 else insights
        session['patient_data']['registration']['emr_insights'] = abbreviated_insights
        
        return jsonify({
            'success': True,
            'insights': insights
        })
        
    except Exception as e:
        print(f"EMR analysis error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error analyzing EMR: {str(e)}'
        })

@app.route('/process_aadhaar', methods=['POST'])
def process_aadhaar():
    """Process uploaded Aadhaar card image and extract data using LLM"""
    try:
        if 'aadhaar_image' not in request.files:
            return jsonify({'success': False, 'error': 'No Aadhaar image uploaded'})
        
        file = request.files['aadhaar_image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Read file content
        file_content = file.read()
        file_type = file.content_type
        
        # Validate file type (only images)
        if not file_type.startswith('image/'):
            return jsonify({'success': False, 'error': 'Please upload a valid image file (JPG, PNG, etc.)'})
        
        # Encode image content for API
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        
        # Prepare LLM prompt for Aadhaar analysis
        prompt = load_prompt("aadhaar_analysis")

        # Make API call to OpenAI for Aadhaar analysis
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "system", 
                    "content": load_prompt("aadhaar_system")
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{file_type};base64,{encoded_content}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800,
            temperature=0.1  # Low temperature for more accurate extraction
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse the JSON response
        if result.startswith('```json'):
            result = result[7:-3]
        elif result.startswith('```'):
            result = result[3:-3]
        
        result = result.strip()
        
        try:
            # Extract JSON from response
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise Exception("No valid JSON found in response")
            
            json_content = result[json_start:json_end]
            extraction_result = json.loads(json_content)
            
            if extraction_result.get('success'):
                # Store Aadhaar data in session
                if 'patient_data' not in session:
                    session['patient_data'] = {}
                if 'registration' not in session['patient_data']:
                    session['patient_data']['registration'] = {}
                
                session['patient_data']['registration']['aadhaar_extraction'] = extraction_result['extracted_data']
                session.modified = True
                
                return jsonify(extraction_result)
            else:
                return jsonify({
                    'success': False,
                    'error': extraction_result.get('error', 'Failed to extract data from Aadhaar card')
                })
                
        except json.JSONDecodeError as e:
            print(f"JSON parsing error in Aadhaar extraction: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Failed to parse extraction results. Please try with a clearer image.'
            })
        
    except Exception as e:
        print(f"Aadhaar processing error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error processing Aadhaar card: {str(e)}'
        })

@app.route('/process_insurance_pdf', methods=['POST'])
def process_insurance_pdf():
    """Process uploaded insurance PDF document and extract ALL text using best model"""
    try:
        if 'insurance_document' not in request.files:
            return jsonify({'success': False, 'error': 'No insurance document uploaded'})
        
        file = request.files['insurance_document']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Read file content
        file_content = file.read()
        file_type = file.content_type
        
        # Validate file type (PDF or images)
        if not (file_type == 'application/pdf' or file_type.startswith('image/')):
            return jsonify({'success': False, 'error': 'Please upload a valid PDF file or image'})
        
        # Handle PDF files with comprehensive text extraction
        if file_type == 'application/pdf':
            try:
                import PyPDF2
                import io
                
                # Extract text from PDF using PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                extracted_text = ""
                
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    page_text = page.extract_text()
                    if page_text.strip():
                        extracted_text += f"=== PAGE {page_num} ===\n{page_text}\n\n"
                
                # Also try to extract images from PDF and analyze them with GPT-4o
                embedded_image_text = ""
                try:
                    # Convert PDF pages to images for comprehensive OCR using GPT-4o
                    # This ensures we get text from embedded images too
                    import fitz  # PyMuPDF for better PDF handling
                    
                    pdf_document = fitz.open(stream=file_content, filetype="pdf")
                    
                    for page_num in range(len(pdf_document)):
                        page = pdf_document.load_page(page_num)
                        # Convert page to image
                        mat = fitz.Matrix(2.0, 2.0)  # High resolution
                        pix = page.get_pixmap(matrix=mat)
                        img_data = pix.tobytes("png")
                        
                        # Encode image for GPT-4o
                        encoded_image = base64.b64encode(img_data).decode('utf-8')
                        
                        # Use GPT-4o for comprehensive OCR
                        ocr_prompt = load_prompt("pdf_ocr_analysis")
                        
                        ocr_response = openai_client.chat.completions.create(
                            model="gpt-4.1-nano",  # Best model for comprehensive OCR
                            messages=[
                                {
                                    "role": "system",
                                    "content": load_prompt("pdf_ocr_system")
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": ocr_prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{encoded_image}"
                                            }
                                        }
                                    ]
                                }
                            ],
                            max_tokens=2000,
                            temperature=0.0  # Minimum temperature for maximum accuracy
                        )
                        
                        page_ocr_text = ocr_response.choices[0].message.content.strip()
                        if page_ocr_text:
                            embedded_image_text += f"=== PAGE {page_num + 1} (COMPREHENSIVE OCR) ===\n{page_ocr_text}\n\n"
                    
                    pdf_document.close()
                    
                except ImportError:
                    # Fallback if PyMuPDF not available
                    print("PyMuPDF not available, using basic PyPDF2 extraction only")
                except Exception as e:
                    print(f"Error in comprehensive PDF OCR: {str(e)}")
                
                # Combine extracted text
                final_text = ""
                if extracted_text.strip():
                    final_text += "=== BASIC TEXT EXTRACTION ===\n" + extracted_text
                if embedded_image_text.strip():
                    final_text += "=== COMPREHENSIVE OCR EXTRACTION ===\n" + embedded_image_text
                
                if not final_text.strip():
                    return jsonify({'success': False, 'error': 'Could not extract any text from PDF. Please try with an image version.'})
                
                # Store extracted text in patient data
                patient_data = load_patient_data()
                if 'registration' not in patient_data:
                    patient_data['registration'] = {}
                
                patient_data['registration']['insurance_extracted_text'] = {
                    'text': final_text,
                    'extraction_method': 'comprehensive_pdf_ocr',
                    'file_type': 'PDF',
                    'extracted_at': datetime.now().isoformat(),
                    'file_name': file.filename
                }
                
                save_patient_data(patient_data)
                
                return jsonify({
                    'success': True,
                    'extracted_text': final_text,
                    'extraction_method': 'comprehensive_pdf_ocr',
                    'file_type': 'PDF'
                })

            except ImportError:
                return jsonify({'success': False, 'error': 'PDF processing not available. Please upload an image version of your insurance document.'})
            except Exception as e:
                return jsonify({'success': False, 'error': f'Error reading PDF: {str(e)}'})
                
        else:
            # Handle image files with comprehensive OCR
            encoded_content = base64.b64encode(file_content).decode('utf-8')
            
            prompt = load_prompt("insurance_ocr_analysis")

            response = openai_client.chat.completions.create(
                model="gpt-4.1-nano",  # Best model for comprehensive OCR
                messages=[
                    {
                        "role": "system", 
                        "content": load_prompt("insurance_ocr_system")
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{file_type};base64,{encoded_content}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.0  # Minimum temperature for maximum accuracy
            )
        
            result = response.choices[0].message.content.strip()
            
            # Store extracted text in patient data
            patient_data = load_patient_data()
            if 'registration' not in patient_data:
                patient_data['registration'] = {}
            
            patient_data['registration']['insurance_extracted_text'] = {
                'text': result,
                'extraction_method': 'comprehensive_image_ocr',
                'file_type': 'Image',
                'extracted_at': datetime.now().isoformat(),
                'file_name': file.filename
            }
            
            save_patient_data(patient_data)
            
            return jsonify({
                'success': True,
                'extracted_text': result,
                'extraction_method': 'comprehensive_image_ocr',
                'file_type': 'Image'
            })
        
    except Exception as e:
        print(f"Insurance processing error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error processing insurance document: {str(e)}'
        })

@app.route('/get_insurance_text', methods=['GET'])
def get_insurance_text():
    """Retrieve saved insurance extracted text"""
    try:
        patient_data = load_patient_data()
        
        if 'registration' in patient_data and 'insurance_extracted_text' in patient_data['registration']:
            return jsonify({
                'success': True,
                'data': patient_data['registration']['insurance_extracted_text']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No insurance text data found'
            })
            
    except Exception as e:
        print(f"Error retrieving insurance text: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error retrieving insurance text: {str(e)}'
        })

@app.route('/analyze_medical_photo', methods=['POST'])
def analyze_medical_photo():
    """Analyze uploaded medical photos (tongue, throat, skin/infection) using LLM"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image uploaded'})
        
        file = request.files['image']
        photo_type = request.form.get('photo_type', 'unknown')
        category = request.form.get('category', photo_type)  # Support Step 3 categories
        report_type = request.form.get('report_type', '')   # Support Step 3 report types
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Read and encode file content
        file_content = file.read()
        file_type = file.content_type
        
        # Validate file type (only images)
        if not file_type.startswith('image/'):
            return jsonify({'success': False, 'error': 'Please upload a valid image file'})
        
        # Encode image content for API
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        
        # Get the appropriate photo analysis prompt from external files
        if category in ['laboratory', 'medical_image', 'signal']:
            base_prompt = get_photo_analysis_prompt(category, report_type)
        else:
            base_prompt = get_photo_analysis_prompt(photo_type, report_type)
        
        full_prompt = f"""
        {base_prompt}
        
        RESPONSE FORMAT (JSON):
        {{
            "success": true,
            "insights": {{
                "general_findings": "Overall description of what is observed",
                "specific_observations": ["List of specific medical observations"],
                "confidence_level": "High/Medium/Low",
                "recommendations": "Medical recommendations and next steps",
                "concerns": ["List any concerning findings requiring attention"],
                "normal_features": ["List normal/healthy features observed"],
                "follow_up_needed": "Yes/No with explanation"
            }}
        }}
        
        IMPORTANT:
        - Provide medical observations only, not definitive diagnoses
        - Use professional medical terminology
        - Be specific about visual characteristics
        - Indicate confidence level in observations
        - Highlight any concerning features
        - Suggest appropriate medical follow-up when needed
        """

        # Make API call to OpenAI for medical photo analysis
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "system", 
                    "content": load_prompt("photo_analysis_system")
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": full_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{file_type};base64,{encoded_content}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000,
            temperature=0.3  # Lower temperature for more consistent medical analysis
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse the JSON response
        if result.startswith('```json'):
            result = result[7:-3]
        elif result.startswith('```'):
            result = result[3:-3]
        
        result = result.strip()
        
        try:
            # Extract JSON from response
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise Exception("No valid JSON found in response")
            
            json_content = result[json_start:json_end]
            analysis_result = json.loads(json_content)
            
            if analysis_result.get('success'):
                # Store medical photo analysis in session
                if 'patient_data' not in session:
                    session['patient_data'] = {}
                
                # Handle Step 3 categories differently from Step 2
                if category in ['laboratory', 'medical_image', 'signal']:
                    # Step 3: Store minimal data to avoid session size issues
                    if 'medical_reports_analysis' not in session['patient_data']:
                        session['patient_data']['medical_reports_analysis'] = []
                    
                    # Store only essential metadata, not full analysis to reduce session size
                    session['patient_data']['medical_reports_analysis'].append({
                        'file_name': file.filename,
                        'category': category,
                        'report_type': report_type,
                        'analyzed': True,  # Just track that it was analyzed
                        'analyzed_at': datetime.now().isoformat()
                    })
                else:
                    # Step 2: Store abbreviated vitals analysis
                    if 'vitals' not in session['patient_data']:
                        session['patient_data']['vitals'] = {}
                    # Store only key points, not full analysis
                    insights = analysis_result['insights']
                    abbreviated_insights = insights[:200] + "..." if len(insights) > 200 else insights
                    session['patient_data']['vitals'][f'{photo_type}_photo_analysis'] = abbreviated_insights
                
                session.modified = True
                
                return jsonify(analysis_result)
            else:
                return jsonify({
                    'success': False,
                    'error': analysis_result.get('error', 'Failed to analyze medical photo')
                })
                
        except json.JSONDecodeError as e:
            print(f"JSON parsing error in medical photo analysis: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Failed to parse analysis results. Please try with a clearer image.'
            })
        
    except Exception as e:
        print(f"Medical photo analysis error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error analyzing medical photo: {str(e)}'
        })

@app.route('/analyze_medical_photo_custom', methods=['POST'])
def analyze_medical_photo_custom():
    """Analyze uploaded medical photos with custom prompts and model selection"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image uploaded'})
        
        file = request.files['image']
        custom_prompt = request.form.get('custom_prompt', '')
        selected_model = request.form.get('selected_model', 'gpt-4o-mini')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not custom_prompt.strip():
            return jsonify({'success': False, 'error': 'Please provide an analysis prompt'})
        
        # Validate selected model
        available_models = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo']
        if selected_model not in available_models:
            selected_model = 'gpt-4o-mini'  # Fallback to default
        
        # Read and encode file content
        file_content = file.read()
        file_type = file.content_type
        
        # Validate file type (only images)
        if not file_type.startswith('image/'):
            return jsonify({'success': False, 'error': 'Please upload a valid image file'})
        
        # Validate file size (10MB limit)
        if len(file_content) > 10 * 1024 * 1024:
            return jsonify({'success': False, 'error': 'File size must be less than 10MB'})
        
        # Encode image content for API
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        
        # Create comprehensive medical analysis prompt
        full_prompt = f"""
        You are an expert medical AI assistant analyzing a medical image. The user has provided the following specific analysis request:

        USER REQUEST: {custom_prompt}

        Please provide a comprehensive medical analysis of this image focusing on the user's specific request while also noting any other medically relevant observations.

        RESPONSE FORMAT (JSON):
        {{
            "success": true,
            "insights": {{
                "general_findings": "Overall description of what is observed in the image",
                "specific_observations": ["List of specific medical observations relevant to the user's request"],
                "confidence_level": "High/Medium/Low",
                "recommendations": "Medical recommendations and suggested next steps",
                "concerns": ["List any concerning findings requiring immediate medical attention"],
                "normal_features": ["List normal/healthy features observed"],
                "follow_up_needed": "Yes/No with explanation of why",
                "additional_notes": "Any additional medically relevant observations not specifically requested"
            }}
        }}

        IMPORTANT GUIDELINES:
        - Focus primarily on the user's specific request
        - Provide detailed medical observations, not definitive diagnoses
        - Use professional medical terminology when appropriate
        - Be specific about visual characteristics (size, color, texture, location, etc.)
        - Indicate your confidence level in the observations
        - Highlight any concerning features that may require medical attention
        - Suggest appropriate medical follow-up when necessary
        - Include any other medically relevant observations even if not specifically requested
        - If the image quality is poor or unclear, mention this in your assessment
        """

        print(f"Custom medical photo analysis - Model: {selected_model}, Prompt length: {len(custom_prompt)}")

        # Make API call to OpenAI with selected model
        response = openai_client.chat.completions.create(
            model=selected_model,
            messages=[
                {
                    "role": "system", 
                    "content": """You are an expert medical AI assistant specializing in medical image analysis. 
                    You provide detailed, professional medical observations while being careful not to provide 
                    definitive diagnoses. You focus on what can be visually observed and suggest appropriate 
                    medical follow-up when necessary."""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": full_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{file_type};base64,{encoded_content}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1500,  # Increased for more detailed analysis
            temperature=0.2   # Lower temperature for more consistent medical analysis
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse the JSON response
        if result.startswith('```json'):
            result = result[7:-3]
        elif result.startswith('```'):
            result = result[3:-3]
        
        result = result.strip()
        
        try:
            # Extract JSON from response
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise Exception("No valid JSON found in response")
            
            json_content = result[json_start:json_end]
            analysis_result = json.loads(json_content)
            
            if analysis_result.get('success'):
                # Analysis completed successfully - return results
                # Note: Data will be saved when the step3 form is submitted
                print(f"✅ Custom medical photo analysis completed successfully with {selected_model}")
                return jsonify(analysis_result)
            else:
                return jsonify({
                    'success': False,
                    'error': analysis_result.get('error', 'Failed to analyze medical photo')
                })
                
        except json.JSONDecodeError as e:
            print(f"JSON parsing error in custom medical photo analysis: {str(e)}")
            print(f"Raw response: {result[:500]}...")  # Debug: show first 500 chars
            return jsonify({
                'success': False,
                'error': 'Failed to parse analysis results. The AI response was not in the expected format. Please try again.'
            })
        
    except Exception as e:
        print(f"Custom medical photo analysis error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error analyzing medical photo: {str(e)}'
        })

@app.route('/get_available_models', methods=['GET'])
def get_available_models():
    """Get list of available AI models for medical analysis"""
    try:
        # Get models from environment variable
        available_models_str = os.getenv('AVAILABLE_MODELS', 'gpt-4o,gpt-4o-mini,gpt-4-turbo,gpt-3.5-turbo')
        print(f"DEBUG: Raw AVAILABLE_MODELS from env: '{available_models_str}'")
        available_models = [model.strip() for model in available_models_str.split(',')]
        print(f"DEBUG: Parsed available_models: {available_models}")
        
        # Get default model from environment
        default_model = os.getenv('MODEL', 'gpt-4o-mini')
        print(f"DEBUG: Default model from env: '{default_model}'")
        
        return jsonify({
            'success': True,
            'models': available_models,
            'default_model': default_model
        })
    except Exception as e:
        print(f"Error getting available models: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to load available models',
            'models': ['gpt-4.1-nano'],  # Fallback
            'default_model': 'gpt-4.1-nano'
        })

@app.route('/upload_medical_image', methods=['POST'])
def upload_medical_image():
    """Handle medical image upload from step6 - redirects to analyze_medical_photo with proper parameters"""
    try:
        if 'medical_image' not in request.files:
            return jsonify({'success': False, 'error': 'No image uploaded'})
        
        file = request.files['medical_image']
        image_type = request.form.get('image_type', 'unknown')
        description = request.form.get('description', '')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Read and encode file content
        file_content = file.read()
        file_type = file.content_type
        
        # Validate file type (only images)
        if not file_type.startswith('image/'):
            return jsonify({'success': False, 'error': 'Please upload a valid image file'})
        
        # Encode to base64 for storage/processing
        import base64
        file_data = base64.b64encode(file_content).decode('utf-8')
        
        # Store the uploaded image info in session
        if 'patient_data' not in session:
            session['patient_data'] = {}
        if 'uploaded_images' not in session['patient_data']:
            session['patient_data']['uploaded_images'] = []
        
        session['patient_data']['uploaded_images'].append({
            'filename': file.filename,
            'type': image_type,
            'description': description,
            'upload_timestamp': datetime.now().isoformat(),
            'file_data': file_data,
            'mime_type': file_type
        })
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': f'{image_type.title()} image uploaded successfully',
            'filename': file.filename
        })
        
    except Exception as e:
        print(f"Error in upload_medical_image: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error uploading medical image: {str(e)}'
        })

@app.route('/save_weight_height', methods=['POST'])
@login_required
def save_weight_height():
    """Save weight and height data before proceeding to step 3"""
    try:
        print("✅ Starting save_weight_height")
        
        # Get the JSON data
        data = request.get_json()
        weight = data.get('weight')
        weight_unit = data.get('weight_unit', 'kg')
        height = data.get('height', '')
        height_unit = data.get('height_unit', 'cm')
        
        print(f"   Weight: {weight} {weight_unit}")
        print(f"   Height: {height} {height_unit}")
        
        # Validate weight (mandatory)
        if not weight or weight <= 0:
            return jsonify({
                'success': False,
                'error': 'Weight is required and must be greater than 0'
            })
        
        # Convert weight to kg for standardization
        weight_kg = weight
        if weight_unit == 'lbs':
            weight_kg = weight * 0.453592
        
        # Convert height to cm for standardization
        height_cm = None
        if height:
            if height_unit == 'cm':
                height_cm = float(height)
            elif height_unit == 'inches':
                height_cm = float(height) * 2.54
            elif height_unit == 'ft_in':
                # Parse feet'inches" format
                if "'" in str(height) and '"' in str(height):
                    parts = str(height).replace('"', '').split("'")
                    if len(parts) == 2:
                        feet = float(parts[0]) if parts[0] else 0
                        inches = float(parts[1]) if parts[1] else 0
                        height_cm = (feet * 12 + inches) * 2.54
        
        # Prepare weight/height data for storage
        weight_height_data = {
            'weight': weight,
            'weight_unit': weight_unit,
            'weight_kg': round(weight_kg, 2),
            'height': height,
            'height_unit': height_unit,
            'height_cm': round(height_cm, 2) if height_cm else None,
            'collected_at': datetime.now().isoformat()
        }
        
        print(f"   Standardized - Weight: {weight_kg} kg, Height: {height_cm} cm")
        
        # Save to step3 data (since it's part of vitals assessment)
        success = save_step_based_patient_data(
            step_number=3,
            form_data=weight_height_data,
            ai_data={},
            files_data={}
        )
        
        if success:
            print(f"✅ Weight/height saved successfully")
            return jsonify({
                'success': True,
                'message': 'Weight and height saved successfully',
                'data': weight_height_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save weight/height data'
            })
            
    except Exception as e:
        print(f"❌ Error in save_weight_height: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to save weight/height: {str(e)}'
        })

def calculate_age_from_dob(date_of_birth):
    """Calculate age from date of birth string"""
    try:
        if not date_of_birth:
            return None
        
        # Parse different date formats
        try:
            from dateutil import parser
            birth_date = parser.parse(date_of_birth)
        except ImportError:
            # Fallback to basic datetime parsing if dateutil not available
            birth_date = datetime.strptime(date_of_birth, '%Y-%m-%d')
        
        today = datetime.now()
        
        age = today.year - birth_date.year
        if today.month < birth_date.month or (today.month == birth_date.month and today.day < birth_date.day):
            age -= 1
            
        return age
    except Exception as e:
        print(f"Error calculating age: {str(e)}")
        return None

def calculate_personalized_vital_ranges():
    """Calculate personalized vital sign ranges based on age, gender, weight, and height"""
    try:
        # Get patient data
        all_data = get_all_patient_data()
        
        # Extract demographic data from step2
        step2_data = {}
        if 'steps' in all_data and 'step2' in all_data['steps']:
            step2_data = all_data['steps']['step2'].get('form_data', {})
        
        # Extract weight/height from step3
        step3_data = {}
        if 'steps' in all_data and 'step3' in all_data['steps']:
            step3_data = all_data['steps']['step3'].get('form_data', {})
        
        # Get patient info
        age = None
        date_of_birth = step2_data.get('date_of_birth')
        if date_of_birth:
            age = calculate_age_from_dob(date_of_birth)
        
        gender = step2_data.get('gender', '').lower()
        weight_kg = step3_data.get('weight_kg')
        height_cm = step3_data.get('height_cm')
        
        print(f"🔍 Calculating ranges for: Age={age}, Gender={gender}, Weight={weight_kg}kg, Height={height_cm}cm")
        
        # Default ranges (adult)
        ranges = {
            'temperature': {'min': 36.1, 'max': 37.5, 'unit': '°C'},
            'pulse_rate': {'min': 60, 'max': 100, 'unit': 'bpm'},
            'respiratory_rate': {'min': 12, 'max': 20, 'unit': 'bpm'},
            'systolic_bp': {'min': 90, 'max': 120, 'unit': 'mmHg'},
            'diastolic_bp': {'min': 60, 'max': 80, 'unit': 'mmHg'},
            'oxygen_saturation': {'min': 95, 'max': 100, 'unit': '%'},
            'blood_glucose': {'min': 70, 'max': 140, 'unit': 'mg/dL'},
            'bmi': {'min': 18.5, 'max': 24.9, 'unit': 'kg/m²'}
        }
        
        # Age-based adjustments
        if age:
            if age < 1:  # Infant
                ranges['pulse_rate'] = {'min': 100, 'max': 160, 'unit': 'bpm'}
                ranges['respiratory_rate'] = {'min': 30, 'max': 60, 'unit': 'bpm'}
                ranges['systolic_bp'] = {'min': 65, 'max': 85, 'unit': 'mmHg'}
                ranges['diastolic_bp'] = {'min': 45, 'max': 55, 'unit': 'mmHg'}
            elif age < 3:  # Toddler
                ranges['pulse_rate'] = {'min': 90, 'max': 150, 'unit': 'bpm'}
                ranges['respiratory_rate'] = {'min': 24, 'max': 40, 'unit': 'bpm'}
                ranges['systolic_bp'] = {'min': 70, 'max': 90, 'unit': 'mmHg'}
                ranges['diastolic_bp'] = {'min': 50, 'max': 65, 'unit': 'mmHg'}
            elif age < 12:  # Child
                ranges['pulse_rate'] = {'min': 80, 'max': 120, 'unit': 'bpm'}
                ranges['respiratory_rate'] = {'min': 18, 'max': 30, 'unit': 'bpm'}
                ranges['systolic_bp'] = {'min': 80, 'max': 110, 'unit': 'mmHg'}
                ranges['diastolic_bp'] = {'min': 50, 'max': 70, 'unit': 'mmHg'}
            elif age < 18:  # Adolescent
                ranges['pulse_rate'] = {'min': 70, 'max': 110, 'unit': 'bpm'}
                ranges['respiratory_rate'] = {'min': 12, 'max': 22, 'unit': 'bpm'}
                ranges['systolic_bp'] = {'min': 85, 'max': 115, 'unit': 'mmHg'}
                ranges['diastolic_bp'] = {'min': 55, 'max': 75, 'unit': 'mmHg'}
            elif age >= 65:  # Elderly
                ranges['pulse_rate'] = {'min': 60, 'max': 90, 'unit': 'bpm'}
                ranges['systolic_bp'] = {'min': 95, 'max': 140, 'unit': 'mmHg'}
                ranges['diastolic_bp'] = {'min': 60, 'max': 90, 'unit': 'mmHg'}
        
        # Gender-based adjustments
        if gender == 'female':
            # Slightly higher pulse rate for females
            ranges['pulse_rate']['min'] += 5
            ranges['pulse_rate']['max'] += 5
        
        # Weight-based adjustments
        if weight_kg:
            # Adjust for obesity (affects BP and pulse)
            if height_cm:
                bmi = weight_kg / ((height_cm / 100) ** 2)
                ranges['bmi']['current'] = round(bmi, 1)
                
                if bmi >= 30:  # Obese
                    ranges['systolic_bp']['max'] += 10
                    ranges['diastolic_bp']['max'] += 5
                    ranges['pulse_rate']['max'] += 10
                elif bmi < 18.5:  # Underweight
                    ranges['systolic_bp']['min'] -= 5
                    ranges['pulse_rate']['min'] -= 5
        
        # Add interpretive notes
        for vital, range_data in ranges.items():
            if vital != 'bmi':
                range_data['display'] = f"Normal: {range_data['min']}-{range_data['max']} {range_data['unit']}"
            else:
                range_data['display'] = f"Normal BMI: {range_data['min']}-{range_data['max']} {range_data['unit']}"
                if 'current' in range_data:
                    if range_data['current'] < 18.5:
                        range_data['status'] = 'Underweight'
                    elif range_data['current'] < 25:
                        range_data['status'] = 'Normal'
                    elif range_data['current'] < 30:
                        range_data['status'] = 'Overweight'
                    else:
                        range_data['status'] = 'Obese'
        
        print(f"✅ Calculated personalized ranges: {ranges}")
        return ranges
        
    except Exception as e:
        print(f"❌ Error calculating vital ranges: {str(e)}")
        # Return default ranges on error
        return {
            'temperature': {'min': 36.1, 'max': 37.5, 'unit': '°C', 'display': 'Normal: 36.1-37.5°C'},
            'pulse_rate': {'min': 60, 'max': 100, 'unit': 'bpm', 'display': 'Normal: 60-100 bpm'},
            'respiratory_rate': {'min': 12, 'max': 20, 'unit': 'bpm', 'display': 'Normal: 12-20 bpm'},
            'systolic_bp': {'min': 90, 'max': 120, 'unit': 'mmHg', 'display': 'Normal: 90-120 mmHg'},
            'diastolic_bp': {'min': 60, 'max': 80, 'unit': 'mmHg', 'display': 'Normal: 60-80 mmHg'},
            'oxygen_saturation': {'min': 95, 'max': 100, 'unit': '%', 'display': 'Normal: 95-100%'},
            'blood_glucose': {'min': 70, 'max': 140, 'unit': 'mg/dL', 'display': 'Normal: 70-140 mg/dL'},
            'bmi': {'min': 18.5, 'max': 24.9, 'unit': 'kg/m²', 'display': 'Normal BMI: 18.5-24.9 kg/m²'}
        }

# Step 3: Vital Signs
@app.route('/step3')
@login_required
def step3():
    if not validate_session_step(2):
        return redirect('/')
    
    # Load existing step3 data if available for editing
    all_data = get_all_patient_data()
    step3_data = {}
    if 'steps' in all_data and 'step3' in all_data['steps']:
        step3_data = all_data['steps']['step3'].get('form_data', {})
        print(f"✅ Loading existing step3 data for editing: {len(step3_data)} fields")
    
    # Calculate personalized vital ranges based on patient data
    vital_ranges = calculate_personalized_vital_ranges()
    
    return render_template('step3.html', step3_data=step3_data, vital_ranges=vital_ranges)

# Step 4: Medical Records & Contact
@app.route('/step4')
@login_required
def step4():
    if not validate_session_step(3):
        return redirect('/')
    
    # Get patient data for display using new structure
    all_data = get_all_patient_data()
    patient_name = "Patient"
    patient_age = "Unknown"
    patient_gender = "Unknown"
    
    # Try to get patient info from step2
    if 'steps' in all_data and 'step2' in all_data['steps']:
        step2_data = all_data['steps']['step2'].get('form_data', {})
        patient_name = step2_data.get('full_name', 'Patient')
        patient_age = step2_data.get('calculated_age', 'Unknown')
        patient_gender = step2_data.get('gender', 'Unknown')
    
    # Load existing step4 data if available for editing
    step4_data = {}
    if 'steps' in all_data and 'step4' in all_data['steps']:
        step4_data = all_data['steps']['step4'].get('form_data', {})
    
    return render_template('step4.html', 
                         patient_name=patient_name,
                         patient_age=patient_age,
                         patient_gender=patient_gender,
                         step4_data=step4_data)

@app.route('/save_vitals', methods=['POST'])
def save_vitals():
    try:
        print("✅ Starting save_vitals function")
        print(f"📋 Form data keys: {list(request.form.keys())}")
        
        if not validate_session_step(2):
            print("❌ Validation failed for step 2")
            return jsonify({'success': False, 'error': 'Please complete registration first'})
        
        print("✅ Validation passed for step 2")
        
        # Check if this is a modification of existing data
        existing_step3 = get_step_data(3)
        is_modification = bool(existing_step3)
        print(f"🔄 Is modification: {is_modification}")
        
        # Collect all form data
        form_data = {}
        for key, value in request.form.items():
            print(f"🔍 RAW FORM DATA: {key} = '{value}' (type: {type(value)})")
            if value and str(value).strip():  # Only include non-empty values
                form_data[key] = value.strip()
                print(f"📝 INCLUDED: {key} = '{value.strip()}'")
            else:
                print(f"🚫 EXCLUDED: {key} = '{value}' (empty or None)")
        
        print(f"📋 Collected form data with {len(form_data)} fields")
        print(f"📋 Form data contents: {form_data}")
        
        # Handle file uploads for vitals (medical photos)
        files_data = {}
        photo_fields = ['tongue_photo', 'throat_photo', 'infection_photo']
        for field in photo_fields:
            if field in request.files:
                file = request.files[field]
                if file and file.filename:
                    files_data[field] = {
                        'filename': file.filename,
                        'upload_timestamp': datetime.now().isoformat(),
                        'file_size': len(file.read()),
                        'content_type': file.content_type,
                        'photo_type': field.replace('_photo', '')
                    }
                    file.seek(0)  # Reset file pointer
                    print(f"📸 Medical photo uploaded: {file.filename} ({field})")
        
        # Collect AI-generated insights from photo analysis
        ai_data = {}
        ai_fields = ['tongue_ai_insights', 'throat_ai_insights', 'infection_ai_insights']
        for field in ai_fields:
            if field in form_data:
                ai_data[field] = form_data[field]
                # Remove from form_data to avoid duplication
                del form_data[field]
        
        # Handle custom medical images with AI insights from multi-upload section
        custom_medical_images = []
        
        # First, check for new upload history format
        total_uploads = int(form_data.get('total_medical_uploads', 0))
        print(f"🔍 Processing {total_uploads} medical uploads from form data")
        
        for i in range(1, total_uploads + 1):
            prefix = f'medical_upload_{i}'
            upload_id = form_data.get(f'{prefix}_id', '')
            filename = form_data.get(f'{prefix}_filename', '')
            category = form_data.get(f'{prefix}_category', '')
            model = form_data.get(f'{prefix}_model', '')
            timestamp = form_data.get(f'{prefix}_timestamp', '')
            size = form_data.get(f'{prefix}_size', '')
            insights_str = form_data.get(f'{prefix}_insights', '')
            
            if filename and insights_str:
                try:
                    # Parse insights JSON
                    insights = json.loads(insights_str) if insights_str.startswith('{') else insights_str
                    
                    upload_data = {
                        'upload_id': upload_id,
                        'filename': filename,
                        'category': category,
                        'model_used': model,
                        'upload_timestamp': timestamp,
                        'file_size': size,
                        'ai_insights': insights
                    }
                    
                    custom_medical_images.append(upload_data)
                    print(f"📄 Processed upload: {filename} (Category: {category}, Model: {model})")
                    
                    # Remove from form_data to avoid duplication
                    for field_key in list(form_data.keys()):
                        if field_key.startswith(prefix):
                            del form_data[field_key]
                            
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse insights for {filename}: {str(e)}")
                    continue
        
        # Also handle legacy format for backwards compatibility
        upload_counter = 1
        while True:
            image_field = f'medical_image_{upload_counter}'
            prompt_field = f'prompt_{upload_counter}'
            model_field = f'model_{upload_counter}'
            insights_field = f'ai_insights_{upload_counter}'
            
            # Check if this upload exists
            if image_field in request.files and request.files[image_field].filename:
                file = request.files[image_field]
                prompt = form_data.get(prompt_field, '')
                model = form_data.get(model_field, 'gpt-4.1-nano')
                insights = form_data.get(insights_field, '')
                
                custom_image_data = {
                    'upload_id': upload_counter,
                    'filename': file.filename,
                    'file_size': len(file.read()),
                    'content_type': file.content_type,
                    'user_prompt': prompt,
                    'model_used': model,
                    'upload_timestamp': datetime.now().isoformat(),
                    'ai_insights': insights
                }
                
                custom_medical_images.append(custom_image_data)
                file.seek(0)  # Reset file pointer
                print(f"📸 Legacy custom medical image uploaded: {file.filename} (Upload #{upload_counter})")
                
                # Remove these fields from form_data to avoid duplication
                for field_to_remove in [prompt_field, model_field, insights_field]:
                    if field_to_remove in form_data:
                        del form_data[field_to_remove]
            else:
                break  # No more uploads found
            
            upload_counter += 1
        
        # Clean up upload-related fields from form_data
        if 'total_medical_uploads' in form_data:
            del form_data['total_medical_uploads']
        
        # Also include any custom medical images stored in session from the analysis process (for backwards compatibility)
        session_custom_images = []
        if 'patient_data' in session and 'custom_medical_images' in session['patient_data']:
            session_custom_images = session['patient_data']['custom_medical_images']
            print(f"📱 Found {len(session_custom_images)} custom medical images in session (legacy)")
        
        print(f"🤖 AI insights collected: {len(ai_data)} fields")
        print(f"📎 Files uploaded: {len(files_data)}")
        print(f"🖼️ Custom medical images: {len(custom_medical_images)} from form, {len(session_custom_images)} from session")
        
        # Use new step-based save function
        print("🔄 About to call save_step_based_patient_data...")
        try:
            success = save_step_based_patient_data(
                step_number=3,
                form_data=form_data,
                ai_data=ai_data,
                files_data=files_data,
                custom_medical_images=custom_medical_images + session_custom_images
            )
            print(f"💾 save_step_based_patient_data returned: {success}")
        except Exception as save_error:
            print(f"💥 Exception in save_step_based_patient_data: {str(save_error)}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Save error: {str(save_error)}'})

        if not success:
            print("❌ Step-based save failed")
            return jsonify({'success': False, 'error': 'Failed to save vitals data'})
        
        print("✅ Step-based save succeeded")
        
        # Clear custom medical images from session after successful save (if any existed)
        if 'patient_data' in session and 'custom_medical_images' in session['patient_data']:
            del session['patient_data']['custom_medical_images']
            print("🗑️ Cleared legacy custom medical images from session after save")
        
        # If this is a modification, invalidate downstream steps
        if is_modification:
            invalidate_downstream_steps(3)
        
        # Keep minimal data in session for navigation
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 3
        session.modified = True
        
        print("✅ Returning success response with redirect to step4")
        
        return jsonify({
            'success': True, 
            'message': 'Vitals saved successfully',
            'redirect_url': '/step4',
            'form_fields': len(form_data),
            'ai_insights': len(ai_data),
            'photos_uploaded': len(files_data),
            'custom_medical_images': len(custom_medical_images + session_custom_images)
        })
        
    except Exception as e:
        print(f"❌ ERROR in save_vitals: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to save vitals: {str(e)}'})

@app.route('/save_step4', methods=['POST'])
def save_step4():
    try:
        print("✅ Starting save_step4")
        
        if not validate_session_step(3):
            return jsonify({'success': False, 'error': 'Please complete vitals first'})
        
        # Check if this is a modification of existing data
        existing_step4 = get_step_data(4)
        is_modification = bool(existing_step4)
        print(f"🔄 Is modification: {is_modification}")
        
        # Collect all form data
        form_data = {}
        for key, value in request.form.items():
            if value and str(value).strip():  # Only include non-empty values
                form_data[key] = value.strip()
        
        print(f"📋 Form data collected: {len(form_data)} fields")
        
        # Handle file uploads for medical documents
        files_data = {}
        file_mappings = {
            'lab_report_file': 'lab_report',
            'medical_image_file': 'medical_imaging',
            'pathology_report_file': 'pathology_report',
            'signaling_report_file': 'signaling_report'
        }
        
        for form_field, report_type in file_mappings.items():
            if form_field in request.files:
                file = request.files[form_field]
                if file and file.filename:
                    files_data[report_type] = {
                        'filename': file.filename,
                        'upload_timestamp': datetime.now().isoformat(),
                        'file_size': len(file.read()),
                        'content_type': file.content_type,
                        'report_type': form_data.get(f'{report_type}_type', ''),
                        'category': report_type
                    }
                    file.seek(0)  # Reset file pointer
                    print(f"📄 Medical document uploaded: {file.filename} ({report_type})")
        
        # Collect AI-generated insights
        ai_data = {}
        ai_fields = [
            'lab_ai_insights', 'image_ai_insights', 'pathology_ai_insights', 
            'signaling_ai_insights', 'generated_questions'
        ]
        
        for field in ai_fields:
            if field in form_data:
                ai_data[field] = form_data[field]
                # Remove from form_data to avoid duplication
                del form_data[field]
        
        # Collect follow-up question answers
        followup_answers = {}
        for key in list(form_data.keys()):
            if key.startswith('followup_answer_'):
                question_id = key.replace('followup_answer_', '')
                followup_answers[question_id] = {
                    'answer': form_data[key],
                    'answered_at': datetime.now().isoformat()
                }
                del form_data[key]  # Remove from form_data
        
        if followup_answers:
            ai_data['followup_answers'] = followup_answers
            print(f"📝 Follow-up answers collected: {len(followup_answers)}")
        
        print(f"🤖 AI insights collected: {len(ai_data)} fields")
        print(f"📎 Files uploaded: {len(files_data)}")
        
        # Use new step-based save function
        success = save_step_based_patient_data(
            step_number=4,
            form_data=form_data,
            ai_data=ai_data,
            files_data=files_data
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save step 4 data'})
        
        # If modification, invalidate downstream steps
        if is_modification:
            invalidate_downstream_steps(4)
        
        # Get patient summary for response
        all_data = get_all_patient_data()
        patient_name = 'Patient'
        
        # Try to get patient name from any step
        for step_key in ['step1', 'step2']:
            if step_key in all_data.get('steps', {}):
                step_data = all_data['steps'][step_key]
                name = step_data.get('form_data', {}).get('full_name')
                if name:
                    patient_name = name
                    break
        
        # Count active medications
        active_medications = []
        step4_form_data = form_data
        for key in step4_form_data:
            if key.endswith('_medication') and step4_form_data[key]:
                med_type = key.replace('_medication', '').replace('_', ' ').title()
                active_medications.append(f"{med_type}: {step4_form_data[key]}")
        
        # Emergency contact info
        emergency_name = step4_form_data.get('emergency_name', 'Not provided')
        emergency_relation = step4_form_data.get('emergency_relation', '')
        emergency_contact_display = f"{emergency_name} ({emergency_relation})" if emergency_relation else emergency_name
        
        # Keep minimal data in session for navigation
        if 'patient_data' not in session:
            session['patient_data'] = {}
        
        session['patient_data']['step_completed'] = 4
        session['patient_data']['step4_completed'] = True
        session.modified = True
        
        print("✅ Step 4 data saved successfully")
        
        return jsonify({
            'success': True, 
            'message': 'Medical records and contact information saved successfully',
            'redirect_url': '/step5',
            'patient_name': patient_name,
            'summary': {
                'form_fields': len(form_data),
                'ai_insights': len(ai_data),
                'files_uploaded': len(files_data),
                'medications_count': len(active_medications),
                'emergency_contact': emergency_contact_display,
                'followup_answers': len(followup_answers) if followup_answers else 0
            }
        })
        
    except Exception as e:
        print(f"❌ ERROR in save_step4: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to save step 4: {str(e)}'})

# Step 5: Complaints and Symptoms
@app.route('/step5')
@login_required
def step5():
    if not validate_session_step(4):
        return redirect('/')
    
    # Get patient data for display
    all_data = get_all_patient_data()
    patient_name = "Patient"
    patient_age = "Unknown"
    patient_gender = "Unknown"
    
    # Try to get patient info from step2
    has_medical_reports = False  # Default to false
    if 'steps' in all_data and 'step2' in all_data['steps']:
        step2_data = all_data['steps']['step2'].get('form_data', {})
        patient_name = step2_data.get('full_name', 'Patient')
        patient_age = step2_data.get('calculated_age', 'Unknown')
        patient_gender = step2_data.get('gender', 'Unknown')
        has_medical_reports = step2_data.get('other_medical_reports', '') == 'yes'
    
    # Load existing step5 data if available for editing
    step5_data = {}
    if 'steps' in all_data and 'step5' in all_data['steps']:
        step5_data = all_data['steps']['step5'].get('form_data', {})
        print(f"✅ Loading existing step5 data for editing: {len(step5_data)} fields")
    
    # Extract abnormal findings from step4 data
    abnormal_findings = []
    if 'steps' in all_data and 'step4' in all_data['steps']:
        step4_ai_data = all_data['steps']['step4'].get('ai_generated_data', {})
        generated_questions_str = step4_ai_data.get('generated_questions', '[]')
        
        try:
            import json
            if isinstance(generated_questions_str, str):
                generated_questions = json.loads(generated_questions_str)
            else:
                generated_questions = generated_questions_str
            
            # Use a set to track unique findings and avoid duplicates
            unique_findings = {}
            
            # Extract unique abnormal findings from the questions
            for question_data in generated_questions:
                if isinstance(question_data, dict) and 'abnormal_finding' in question_data:
                    finding_key = question_data.get('abnormal_finding', '').lower().strip()
                    if finding_key and finding_key not in unique_findings:
                        unique_findings[finding_key] = {
                            'finding': question_data.get('abnormal_finding', ''),
                            'concern': question_data.get('medical_concern', ''),
                            'priority': question_data.get('priority', 'normal'),
                            'question': question_data.get('question', '')
                        }
            
            # Convert unique findings to list
            abnormal_findings = list(unique_findings.values())
            
            print(f"✅ Extracted {len(abnormal_findings)} unique abnormal findings from step4 (filtered from {len(generated_questions)} questions)")
        except Exception as e:
            print(f"⚠️ Error parsing step4 generated_questions: {e}")
            abnormal_findings = []
    
    return render_template('step5.html', 
                         patient_name=patient_name,
                         patient_age=patient_age,
                         patient_gender=patient_gender,
                         step5_data=step5_data,
                         abnormal_findings=abnormal_findings,
                         has_medical_reports=has_medical_reports)

@app.route('/analyze_symptoms_quick', methods=['POST'])
def analyze_symptoms_quick():
    """Quick insights on symptoms - extract medical labels"""
    try:
        print("🔍 Starting quick symptom analysis...")
        
        if not validate_session_step(4):
            return jsonify({'success': False, 'error': 'Please complete step 4 first'})
        
        # Get symptom text from request
        complaint_text = request.json.get('symptoms', '').strip()
        if not complaint_text:
            return jsonify({'success': False, 'error': 'Please enter symptom description first'})
        
        print(f"📝 Analyzing complaint: {complaint_text[:100]}...")
        
        # Get patient context for better analysis
        all_data = get_all_patient_data()
        patient_context = {
            'age': 'Unknown',
            'gender': 'Unknown',
            'vitals': {}
        }
        
        # Extract context from previous steps
        if 'steps' in all_data:
            if 'step2' in all_data['steps']:
                step2_data = all_data['steps']['step2'].get('form_data', {})
                patient_context['age'] = step2_data.get('calculated_age', 'Unknown')
                patient_context['gender'] = step2_data.get('gender', 'Unknown')
            
            if 'step3' in all_data['steps']:
                step3_data = all_data['steps']['step3'].get('form_data', {})
                patient_context['vitals'] = step3_data
        
        # Create AI prompt for medical label extraction
        prompt_template = load_prompt("symptom_analysis")
        prompt = prompt_template.format(
            complaint_text=complaint_text,
            age=patient_context['age'],
            gender=patient_context['gender'],
            vitals=patient_context['vitals']
        )
        
        # Call OpenAI API
        response = call_gpt4(prompt, {})
        print(f"🤖 GPT-4 response received: {len(response) if response else 0} characters")
        
        if not response or response.strip() == "":
            raise Exception("Empty response from AI")
        
        # Clean and parse response
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:]
        if response.endswith('```'):
            response = response[:-3]
        
        # Find JSON boundaries
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_str = response[start_idx:end_idx]
            insights_data = json.loads(json_str)
        else:
            raise ValueError("No valid JSON found in response")
        
        # Validate and ensure required fields
        if not isinstance(insights_data, dict):
            raise ValueError("Invalid JSON structure")
        
        insights_data.setdefault('medical_labels', [])
        insights_data.setdefault('urgency_assessment', {'level': 'moderate', 'reasoning': 'Standard assessment'})
        insights_data.setdefault('key_insights', [])
        insights_data.setdefault('symptom_summary', {'primary_concern': 'Symptom analysis'})
        
        print(f"✅ Analysis complete: {len(insights_data.get('medical_labels', []))} labels extracted")
        
        return jsonify({
            'success': True,
            'insights': insights_data,
            'message': 'Quick symptom analysis completed'
        })
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {str(e)}")
        # Return fallback insights
        fallback_insights = {
            'medical_labels': [
                {
                    'label': 'Patient Complaint',
                    'confidence': 50,
                    'category': 'symptom',
                    'severity': 'moderate',
                    'description': 'Symptoms as described by patient'
                }
            ],
            'urgency_assessment': {
                'level': 'moderate',
                'reasoning': 'Standard assessment pending detailed analysis',
                'immediate_concerns': []
            },
            'key_insights': [
                'Symptom analysis requires further evaluation',
                'Professional medical assessment recommended'
            ],
            'symptom_summary': {
                'primary_concern': complaint_text[:100] if complaint_text else 'Patient symptoms',
                'affected_systems': ['To be determined'],
                'duration_significance': 'Requires detailed history',
                'next_steps': 'Complete detailed symptom questionnaire'
            }
        }
        return jsonify({
            'success': True,
            'insights': fallback_insights,
            'fallback': True,
            'message': 'Basic symptom analysis completed'
        })
        
    except Exception as e:
        print(f"❌ Error in quick symptom analysis: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Analysis failed: {str(e)}'
        })

@app.route('/save_step5', methods=['POST'])
def save_step5():
    try:
        print("✅ Starting save_step5")
        
        if not validate_session_step(4):
            return jsonify({'success': False, 'error': 'Please complete step 4 first'})
        
        # Check if this is a modification
        existing_step5 = get_step_data(5)
        is_modification = bool(existing_step5)
        
        # Collect form data
        form_data = {}
        complaint_fields = [
            'primary_complaint', 'complaint_description', 'symptom_duration',
            'pain_level', 'additional_symptoms', 'complaint_text'
        ]
        
        for field in complaint_fields:
            value = request.form.get(field, '')
            if value and value.strip():
                form_data[field] = value.strip()
        
        # Collect AI-generated insights if available
        ai_data = {}
        
        # Include abnormal findings from step4 in step5 data
        all_data = get_all_patient_data()
        abnormal_findings = []
        if 'steps' in all_data and 'step4' in all_data['steps']:
            step4_ai_data = all_data['steps']['step4'].get('ai_generated_data', {})
            generated_questions_str = step4_ai_data.get('generated_questions', '[]')
            
            try:
                if isinstance(generated_questions_str, str):
                    generated_questions = json.loads(generated_questions_str)
                else:
                    generated_questions = generated_questions_str
                
                # Use a set to track unique findings and avoid duplicates
                unique_findings = {}
                
                # Extract unique abnormal findings
                for question_data in generated_questions:
                    if isinstance(question_data, dict) and 'abnormal_finding' in question_data:
                        finding_key = question_data.get('abnormal_finding', '').lower().strip()
                        if finding_key and finding_key not in unique_findings:
                            unique_findings[finding_key] = {
                                'finding': question_data.get('abnormal_finding', ''),
                                'concern': question_data.get('medical_concern', ''),
                                'priority': question_data.get('priority', 'normal')
                            }
                
                # Convert to list
                abnormal_findings = list(unique_findings.values())
                
                print(f"✅ Including {len(abnormal_findings)} unique abnormal findings from step4 in step5 data")
                
            except Exception as e:
                print(f"⚠️ Error parsing step4 findings: {e}")
                abnormal_findings = []
                
                ai_data['abnormal_findings'] = abnormal_findings
                print(f"📊 Included {len(abnormal_findings)} abnormal findings from step4")
            except Exception as e:
                print(f"⚠️ Error parsing step4 abnormal findings: {e}")
        
        # Check if insights were generated and include them
        insights_json = request.form.get('symptom_insights', '')
        if insights_json:
            try:
                insights_data = json.loads(insights_json)
                ai_data['symptom_insights'] = insights_data
                ai_data['insights_generated_at'] = datetime.now().isoformat()
                print(f"🤖 AI insights included: {len(insights_data.get('medical_labels', []))} labels")
            except json.JSONDecodeError:
                print("⚠️ Could not parse symptom insights JSON")
        
        # Handle medical documentation data from step5 section 2
        medical_docs_json = request.form.get('medical_documents', '')
        if medical_docs_json:
            try:
                medical_docs = json.loads(medical_docs_json)
                ai_data['medical_documents'] = medical_docs
                ai_data['medical_docs_uploaded_at'] = datetime.now().isoformat()
                
                # Extract critical findings from medical documentation
                critical_findings = []
                for doc in medical_docs:
                    if doc.get('insights', {}).get('concerns'):
                        for concern in doc['insights']['concerns']:
                            if any(critical_term in concern.lower() for critical_term in ['critical', 'severe', 'abnormal', 'urgent']):
                                critical_findings.append({
                                    'source_document': doc.get('filename', 'Unknown'),
                                    'category': doc.get('category', 'Unknown'),
                                    'finding': concern,
                                    'priority': 'high'
                                })
                
                if critical_findings:
                    ai_data['critical_medical_findings'] = critical_findings
                    print(f"⚠️ {len(critical_findings)} critical findings identified from medical documents")
                
                print(f"📄 Medical documentation included: {len(medical_docs)} documents")
            except json.JSONDecodeError:
                print("⚠️ Could not parse medical documents JSON")
        
        # Collect follow-up question answers from step 4
        followup_answers = {}
        
        for key in request.form.keys():
            if key.startswith('followup_answer_'):
                question_id = key.replace('followup_answer_', '')
                answer = request.form.get(key, '').strip()
                if answer:
                    followup_answers[question_id] = {
                        'answer': answer,
                        'answered_at': datetime.now().isoformat(),
                        'step': 5
                    }
        
        if followup_answers:
            ai_data['followup_answers'] = followup_answers
            print(f"📝 Follow-up answers collected: {len(followup_answers)}")
        
        print(f"📋 Complaints data collected: {len(form_data)} fields")
        print(f"🤖 AI data collected: {len(ai_data)} sections")
        
        # Use step-based save function
        success = save_step_based_patient_data(
            step_number=5,
            form_data=form_data,
            ai_data=ai_data,
            files_data={}
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save complaints data'})
        
        # If modification, invalidate downstream steps
        if is_modification:
            invalidate_downstream_steps(5)
        
        # Update session
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 5
        session.modified = True
        
        print("✅ Step 5 saved successfully with AI data")
        
        return jsonify({
            'success': True,
            'message': 'Complaints and symptoms saved successfully',
            'redirect_url': '/step6',
            'form_fields': len(form_data),
            'ai_insights': len(ai_data),
            'followup_answers': len(followup_answers)
        })
        
    except Exception as e:
        print(f"❌ Error in save_step5: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to save step 5: {str(e)}'})

# New endpoints for enhanced Step 5 functionality

@app.route('/upload_medical_document', methods=['POST'])
def upload_medical_document():
    """Handle medical document upload and AI analysis"""
    try:
        print("📎 Processing medical document upload...")
        
        # Get file and form data
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        category = request.form.get('category', '')
        caption = request.form.get('caption', '')
        model = request.form.get('model', 'gpt-4o-mini')
        
        print(f"📋 Upload details - Category: {category}, Model: {model}, File: {file.filename}")
        
        if not category:
            return jsonify({'success': False, 'error': 'Document category is required'})
        
        # Validate file type
        allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'File type not supported'})
        
        # Process the file based on category
        insights = {}
        try:
            # Read file content
            file_content = file.read()
            
            # Get the appropriate analysis prompt based on category
            if category == 'laboratory':
                prompt_name = 'educational_lab_analysis'
            elif category == 'imaging':
                prompt_name = 'educational_medical_image_analysis'
            elif category == 'signaling':
                prompt_name = 'educational_signal_analysis'
            elif category == 'multimedia':
                prompt_name = 'educational_pathology_analysis'
            else:
                prompt_name = 'educational_lab_analysis'  # Default
            
            # Load the appropriate prompt
            prompt_content = load_prompt(prompt_name)
            if not prompt_content:
                return jsonify({'success': False, 'error': 'Analysis prompt not found'})
            
            # Create analysis request
            print(f"📋 Starting AI analysis for {category} document with model {model}")
            
            if file_ext in ['.jpg', '.jpeg', '.png']:
                # Image analysis
                print(f"🖼️ Processing image file: {file.filename}")
                base64_image = base64.b64encode(file_content).decode('utf-8')
                
                response = openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_content},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/{file_ext[1:]};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=1000
                )
                
                analysis_text = response.choices[0].message.content
                print(f"🤖 AI response received: {len(analysis_text)} characters")
                
            elif file_ext == '.pdf':
                # PDF analysis using OCR
                analysis_text = analyze_pdf_with_llm(file_content, prompt_content, model)
                
            else:
                # Text document analysis
                try:
                    if file_ext in ['.doc', '.docx']:
                        # Handle Word documents (you might need python-docx)
                        text_content = str(file_content, 'utf-8', errors='ignore')
                    else:
                        text_content = str(file_content, 'utf-8')
                    
                    full_prompt = f"{prompt_content}\n\nDocument content:\n{text_content}"
                    
                    response = openai_client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": full_prompt}],
                        max_tokens=1000
                    )
                    
                    analysis_text = response.choices[0].message.content
                    
                except Exception as e:
                    print(f"Error processing text document: {e}")
                    analysis_text = "Unable to process document content."
            
            # Parse the analysis response
            insights = parse_medical_analysis(analysis_text, category)
            print(f"🔍 Parsed insights: {insights}")
            
        except Exception as e:
            print(f"❌ Error analyzing document: {str(e)}")
            print(f"❌ Error details: {repr(e)}")
            insights = {
                'general_findings': f'Analysis failed: {str(e)}',
                'specific_observations': [],
                'recommendations': 'Please consult with a healthcare provider.',
                'concerns': ['Unable to complete automated analysis'],
                'confidence_level': 'Low'
            }
        
        print(f"✅ Medical document analyzed successfully")
        print(f"✅ Insights generated: {insights}")
        
        return jsonify({
            'success': True,
            'insights': insights,
            'message': f'{category.title()} document analyzed successfully'
        })
        
    except Exception as e:
        print(f"❌ Error in upload_medical_document: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/analyze_symptoms_with_medical_docs', methods=['POST'])
def analyze_symptoms_with_medical_docs():
    """Enhanced symptom analysis that includes medical documentation context"""
    try:
        print("🧠 Starting enhanced symptom analysis with medical documentation...")
        
        data = request.get_json()
        symptoms = data.get('symptoms', '').strip()
        medical_documents = data.get('medical_documents', [])
        
        if not symptoms:
            return jsonify({'success': False, 'error': 'Symptoms text is required'})
        
        # Build enhanced analysis context
        analysis_context = f"Patient Symptoms: {symptoms}\n\n"
        
        # Include medical documentation insights if available
        if medical_documents:
            analysis_context += "Medical Documentation Analysis:\n"
            for doc in medical_documents:
                if doc.get('insights'):
                    insights = doc['insights']
                    analysis_context += f"\n{doc.get('categoryLabel', 'Document')} - {doc.get('filename', 'Unknown')}:\n"
                    if insights.get('general_findings'):
                        analysis_context += f"Findings: {insights['general_findings']}\n"
                    if insights.get('concerns'):
                        analysis_context += f"Concerns: {', '.join(insights['concerns'])}\n"
        
        # Get comprehensive analysis from patient data
        all_patient_data = get_all_patient_data()
        
        # Load the symptom analysis prompt
        prompt_content = load_prompt('symptom_analysis')
        if not prompt_content:
            return jsonify({'success': False, 'error': 'Analysis prompt not found'})
        
        # Create enhanced prompt with all context
        enhanced_prompt = f"""
        {prompt_content}
        
        ADDITIONAL CONTEXT FROM MEDICAL DOCUMENTATION:
        {analysis_context}
        
        Patient's Current Symptoms and Health Concerns:
        {symptoms}
        
        Please provide a comprehensive analysis considering both the symptoms and any relevant findings from the uploaded medical documentation. Pay special attention to any critical findings from medical reports that might relate to the current symptoms.
        """
        
        # Generate AI analysis
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": enhanced_prompt}],
            max_tokens=1500
        )
        
        analysis_text = response.choices[0].message.content
        
        # Parse analysis into structured format
        insights = parse_symptom_analysis(analysis_text)
        
        # Add flag if medical documentation was considered
        if medical_documents:
            insights['medical_docs_considered'] = True
            insights['docs_count'] = len(medical_documents)
        
        print(f"✅ Enhanced symptom analysis completed with {len(medical_documents)} medical documents")
        
        return jsonify({
            'success': True,
            'insights': insights,
            'analysis_context_included': bool(medical_documents)
        })
        
    except Exception as e:
        print(f"❌ Error in analyze_symptoms_with_medical_docs: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def parse_medical_analysis(analysis_text, category):
    """Parse medical document analysis into structured format"""
    try:
        insights = {
            'general_findings': '',
            'specific_observations': [],
            'recommendations': '',
            'concerns': [],
            'confidence_level': 'Medium'
        }
        
        lines = analysis_text.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Detect sections
            if 'finding' in line.lower() or 'result' in line.lower():
                current_section = 'findings'
                insights['general_findings'] += line + ' '
            elif 'observation' in line.lower() or 'note' in line.lower():
                current_section = 'observations'
                if line not in insights['specific_observations']:
                    insights['specific_observations'].append(line)
            elif 'recommend' in line.lower() or 'suggest' in line.lower():
                current_section = 'recommendations'
                insights['recommendations'] += line + ' '
            elif 'concern' in line.lower() or 'abnormal' in line.lower() or 'critical' in line.lower():
                current_section = 'concerns'
                if line not in insights['concerns']:
                    insights['concerns'].append(line)
            elif current_section:
                # Continue previous section
                if current_section == 'findings':
                    insights['general_findings'] += line + ' '
                elif current_section == 'recommendations':
                    insights['recommendations'] += line + ' '
        
        # Clean up text
        insights['general_findings'] = insights['general_findings'].strip()
        insights['recommendations'] = insights['recommendations'].strip()
        
        # Set confidence based on content quality
        if len(insights['general_findings']) > 100:
            insights['confidence_level'] = 'High'
        elif len(insights['concerns']) > 0:
            insights['confidence_level'] = 'Medium'
        else:
            insights['confidence_level'] = 'Low'
        
        return insights
        
    except Exception as e:
        print(f"Error parsing medical analysis: {e}")
        return {
            'general_findings': analysis_text[:200] + '...' if len(analysis_text) > 200 else analysis_text,
            'specific_observations': [],
            'recommendations': 'Please consult with a healthcare provider for interpretation.',
            'concerns': [],
            'confidence_level': 'Low'
        }

def parse_symptom_analysis(analysis_text):
    """Parse symptom analysis text into structured format"""
    try:
        # Similar to existing symptom analysis parsing but enhanced
        medical_labels = []
        lines = analysis_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for medical terminology and create labels
            if any(term in line.lower() for term in ['symptom', 'condition', 'syndrome', 'disease']):
                label = {
                    'label': line[:50],  # First 50 chars as label
                    'category': 'Symptom Analysis',
                    'severity': 'Moderate',
                    'confidence': 75,
                    'description': line
                }
                medical_labels.append(label)
        
        return {
            'medical_labels': medical_labels,
            'analysis_text': analysis_text,
            'generated_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error parsing symptom analysis: {e}")
        return {
            'medical_labels': [],
            'analysis_text': analysis_text,
            'generated_at': datetime.now().isoformat()
        }

def analyze_pdf_with_llm(pdf_content, prompt, model="gpt-4.1-nano"):
    """Analyze PDF content using OCR and LLM"""
    try:
        # This is a simplified implementation
        # In a full implementation, you'd use OCR to extract text from PDF
        
        # For now, return a generic analysis
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"{prompt}\n\nNote: PDF content analysis - please provide general medical document analysis guidance."}],
            max_tokens=800
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error analyzing PDF: {e}")
        return "Unable to analyze PDF document. Please consult with a healthcare provider."

# Step 6: Complaint Analysis
@app.route('/step6')
@login_required
def step6():
    if not validate_session_step(5):
        return redirect('/')
    return render_template('step6.html', current_step='step6')

@app.route('/save_step6', methods=['POST'])
def save_step6():
    try:
        print("✅ Starting save_step6")
        
        if not validate_session_step(5):
            return jsonify({'success': False, 'error': 'Please complete step 5 first'})
        
        # This step is mainly AI-generated analysis
        # Collect any user selections or confirmations
        form_data = {}
        
        # Collect analysis results and user confirmations
        analysis_fields = [
            'selected_analysis', 'user_confirmation', 'additional_notes'
        ]
        
        for field in analysis_fields:
            value = request.form.get(field, '')
            if value and value.strip():
                form_data[field] = value.strip()
        
        # AI analysis data would be generated here
        ai_data = {}
        if request.form.get('ai_analysis_results'):
            ai_data['complaint_analysis'] = request.form.get('ai_analysis_results')
        
        print(f"📋 Analysis data collected: {len(form_data)} fields")
        
        # Use step-based save function
        success = save_step_based_patient_data(
            step_number=6,
            form_data=form_data,
            ai_data=ai_data,
            files_data={}
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save analysis data'})
        
        # Update session
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 6
        session.modified = True
        
        print("✅ Step 6 saved successfully")
        
        return jsonify({
            'success': True,
            'message': 'Complaint analysis saved successfully',
            'redirect_url': '/report',
            'form_fields': len(form_data),
            'ai_analysis': len(ai_data)
        })
        
    except Exception as e:
        print(f"❌ Error in save_step6: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to save step 6: {str(e)}'})

@app.route('/save_step7_complete', methods=['POST'])
def save_step7_complete():
    """Save complete step7 data including clinical summary, ICD codes, and user feedback"""
    try:
        print("✅ Starting save_step7_complete")
        
        if not validate_session_step(6):
            return jsonify({'success': False, 'error': 'Please complete step 6 first'})
        
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        # Extract all components
        clinical_summary = data.get('clinical_summary', '')
        original_clinical_summary = data.get('original_clinical_summary', '')
        icd_codes = data.get('icd_codes', [])
        diagnostic_tests = data.get('diagnostic_tests', [])
        recommended_lab_tests = data.get('recommended_lab_tests', [])
        elimination_history = data.get('elimination_history', [])
        analysis_notes = data.get('analysis_notes', '')
        recommendations = data.get('recommendations', [])
        system_analysis = data.get('system_analysis', {})
        completion_timestamp = data.get('completion_timestamp', datetime.now().isoformat())
        session_duration = data.get('session_duration', 0)
        final_codes_count = data.get('final_codes_count', 0)
        total_eliminations = data.get('total_eliminations', 0)
        total_lab_tests = data.get('total_lab_tests', 0)
        step_status = data.get('step_status', 'completed')
        
        # Prepare form data (user-entered data)
        form_data = {
            'clinical_summary_edited': clinical_summary,
            'completion_timestamp': completion_timestamp,
            'session_duration': session_duration,
            'final_codes_count': final_codes_count,
            'total_eliminations': total_eliminations,
            'total_lab_tests': total_lab_tests,
            'step_status': step_status
        }
        
        # Prepare AI-generated data
        ai_data = {
            'original_clinical_summary': original_clinical_summary,
            'icd_codes_generated': icd_codes,
            'diagnostic_tests_recommended': diagnostic_tests or recommended_lab_tests,
            'recommended_lab_tests': recommended_lab_tests,
            'elimination_history': elimination_history,
            'analysis_notes': analysis_notes,
            'clinical_recommendations': recommendations,
            'system_analysis': system_analysis,
            'generation_timestamp': datetime.now().isoformat()
        }
        
        # Prepare files data (if any documents were uploaded or generated)
        files_data = {}
        
        # Use the step-based save function
        success = save_step_based_patient_data(
            step_number=7,
            form_data=form_data,
            ai_data=ai_data,
            files_data=files_data
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save step7 data'})
        
        # Update step completion
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 7
        session.modified = True
        
        # Calculate summary statistics
        total_icd_codes = len(icd_codes)
        total_tests = len(recommended_lab_tests or diagnostic_tests)
        total_eliminations_count = len(elimination_history)
        
        print(f"✅ Step7 saved successfully:")
        print(f"   📋 Clinical summary: {len(clinical_summary)} characters")
        print(f"   🏥 ICD codes: {total_icd_codes}")
        print(f"   🔬 Lab tests: {total_tests}")
        print(f"   ❓ Eliminations: {total_eliminations_count}")
        print(f"   📊 Status: {step_status}")
        
        # 🚀 AUTOMATIC CASE SUBMISSION TO DATABASE - ONLY ON FINAL COMPLETION
        # Only submit case when step7 is truly finished (not intermediate saves)
        should_submit_case = (
            step_status and 
            ('completed' in step_status.lower() or 'finished' in step_status.lower()) and
            'in_progress' not in step_status.lower()
        )
        
        if should_submit_case:
            print("🔄 Starting automatic case submission (FINAL COMPLETION DETECTED)...")
            
            # Load the patient data to get step7 details
            patient_data = load_patient_data()
            if patient_data and patient_data.get('step7'):
                step7_data = patient_data['step7']
                
                # 🛡️ CHECK FOR EXISTING CASE SUBMISSION TO PREVENT DUPLICATES
                session_id = patient_data.get('session_id')
                patient_email = step7_data.get('patient_email', '')
                
                try:
                    # Check if case already exists for this session/patient
                    connection = get_sqlite_connection()
                    if connection:
                        cursor = connection.cursor()
                        
                        # Search for existing case with same patient email and recent timestamp
                        cursor.execute("""
                            SELECT case_number FROM cases 
                            WHERE details LIKE ? 
                            AND details LIKE ?
                            ORDER BY case_number DESC 
                            LIMIT 1
                        """, (f'%"patient_email": "{patient_email}"%', f'%"session_id": "{session_id}"%'))
                        
                        existing_case = cursor.fetchone()
                        cursor.close()
                        connection.close()
                        
                        if existing_case:
                            print(f"⚠️ Case already exists for this session: {existing_case[0]}")
                            print("🔄 Skipping duplicate case submission")
                            
                            # Return success with existing case info
                            return jsonify({
                                'success': True,
                                'message': 'Step 7 completed successfully',
                                'case_submitted': True,
                                'case_number': existing_case[0],
                                'case_status': 'already_submitted',
                                'submission_message': f'Assessment completed! Your case {existing_case[0]} has already been submitted for expert review.',
                                'data': {
                                    'step_completed': 7,
                                    'total_icd_codes': total_icd_codes,
                                    'total_diagnostic_tests': total_tests,
                                    'total_eliminations': total_eliminations_count,
                                    'step_status': step_status,
                                    'session_duration_minutes': round(session_duration / 60000, 2) if session_duration > 0 else 0,
                                    'saved_timestamp': datetime.now().isoformat(),
                                    'case_number': existing_case[0]
                                }
                            })
                    
                    # Generate unique case number
                    case_number = generate_case_number()
                    print(f"📋 Generated case number: {case_number}")
                    
                    # Prepare step7 data as JSON string for database
                    step7_json_data = json.dumps(step7_data, indent=2, default=str)
                    
                    # Insert into SQLite database
                    connection = get_sqlite_connection()
                    if connection:
                        cursor = connection.cursor()
                        
                        insert_query = """
                            INSERT INTO cases (case_number, details, status) 
                            VALUES (?, ?, ?)
                        """
                        
                        cursor.execute(insert_query, (
                            case_number,
                            step7_json_data,
                            'pending_review'
                        ))
                        
                        connection.commit()
                        cursor.close()
                        connection.close()
                        
                        print(f"✅ Case {case_number} submitted successfully to database!")
                        
                        # Return success with case submission details
                        return jsonify({
                            'success': True,
                            'message': 'Step 7 completed and case submitted successfully',
                            'case_submitted': True,
                            'case_number': case_number,
                            'case_status': 'pending_review',
                            'submission_message': 'Case Submitted Successfully!\n\nYour comprehensive medical assessment has been submitted to our expert medical team for detailed review and analysis. You will be notified once the review is complete.',
                            'data': {
                                'step_completed': 7,
                                'total_icd_codes': total_icd_codes,
                                'total_diagnostic_tests': total_tests,
                                'total_eliminations': total_eliminations_count,
                                'step_status': step_status,
                                'session_duration_minutes': round(session_duration / 60000, 2) if session_duration > 0 else 0,
                                'saved_timestamp': datetime.now().isoformat(),
                                'case_number': case_number
                            }
                        })
                        
                    else:
                        print("❌ Could not connect to database for case submission")
                        
                except Exception as case_error:
                    print(f"❌ Error in case submission: {case_error}")
                    
            else:
                print("❌ No step7 data found for case submission")
                
        else:
            print(f"⏭️ Skipping case submission - step status '{step_status}' indicates intermediate save, not final completion")
            
        # Fallback response if case submission fails or is skipped
        return jsonify({
            'success': True,
            'message': 'Step 7 completed and saved successfully',
            'case_submitted': should_submit_case,
            'data': {
                'step_completed': 7,
                'total_icd_codes': total_icd_codes,
                'total_diagnostic_tests': total_tests,
                'total_eliminations': total_eliminations_count,
                'step_status': step_status,
                'session_duration_minutes': round(session_duration / 60000, 2) if session_duration > 0 else 0,
                'saved_timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        print(f"❌ Error in save_step7_complete: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to save step 7: {str(e)}'})

@app.route('/save_expert_review_data', methods=['POST'])
def save_expert_review_data():
    """Save comprehensive step7 data for expert review submission"""
    try:
        print("✅ Starting save_expert_review_data for expert review submission")
        
        if not validate_session_step(6):
            return jsonify({'success': False, 'error': 'Please complete step 6 first'})
        
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        # Extract step7 data package
        step7_data = data.get('step7_data', {})
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        # Extract comprehensive data components
        clinical_summary = step7_data.get('clinical_summary', '')
        patient_data_summary = step7_data.get('patient_data_summary', '')
        icd_codes = step7_data.get('icd_codes', [])
        elimination_history = step7_data.get('elimination_history', [])
        differential_questions = step7_data.get('differential_questions', [])
        recommended_lab_tests = step7_data.get('recommended_lab_tests', [])
        analysis_notes = step7_data.get('analysis_notes', '')
        completion_status = step7_data.get('completion_status', 'submitted_for_expert_review')
        
        # Prepare comprehensive form data for expert review
        form_data = {
            'expert_review_submitted': True,
            'submission_timestamp': timestamp,
            'completion_status': completion_status,
            'total_icd_codes': len(icd_codes),
            'total_lab_tests': len(recommended_lab_tests),
            'differential_questions_answered': len(elimination_history)
        }
        
        # Prepare comprehensive AI-generated data for expert review
        ai_data = {
            'clinical_summary': clinical_summary,
            'patient_data_summary': patient_data_summary,
            'icd_codes_generated': icd_codes,
            'elimination_history': elimination_history,
            'differential_questions': differential_questions,
            'recommended_lab_tests': recommended_lab_tests,
            'analysis_notes': analysis_notes,
            'expert_review_package_created': True,
            'generation_timestamp': datetime.now().isoformat(),
            'submission_for_review_timestamp': timestamp
        }
        
        # Prepare files data for expert review
        files_data = {
            'expert_review_submission': True,
            'comprehensive_data_package': True
        }
        
        # Use the step-based save function with comprehensive data
        success = save_step_based_patient_data(
            step_number=7,
            form_data=form_data,
            ai_data=ai_data,
            files_data=files_data
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save expert review data'})
        
        # Update step completion with expert review status
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 7
        session['patient_data']['expert_review_submitted'] = True
        session['patient_data']['expert_review_timestamp'] = timestamp
        session.modified = True
        
        # Calculate comprehensive summary statistics
        total_icd_codes = len(icd_codes)
        total_tests = len(recommended_lab_tests)
        total_questions = len(elimination_history)
        
        print(f"✅ Expert review data saved successfully:")
        print(f"   📋 Clinical summary: {len(clinical_summary)} characters")
        print(f"   👤 Patient data: {len(patient_data_summary)} characters")
        print(f"   🏥 ICD codes: {total_icd_codes}")
        print(f"   ❓ Differential questions: {total_questions}")
        print(f"   🔬 Lab tests: {total_tests}")
        print(f"   📝 Analysis notes: {len(analysis_notes)} characters")
        
        return jsonify({
            'success': True,
            'message': 'Case successfully submitted for expert review',
            'data': {
                'expert_review_submitted': True,
                'submission_timestamp': timestamp,
                'total_icd_codes': total_icd_codes,
                'total_lab_tests': total_tests,
                'total_differential_questions': total_questions,
                'comprehensive_data_saved': True
            }
        })
        
    except Exception as e:
        print(f"❌ Error in save_expert_review_data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to save expert review data: {str(e)}'})

@app.route('/save_feedback', methods=['POST'])
def save_feedback():
    """Save user feedback about the AI assessment system"""
    try:
        print("✅ Starting save_feedback")
        
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No feedback data provided'})
        
        feedback_text = data.get('feedback', '').strip()
        if not feedback_text:
            return jsonify({'success': False, 'error': 'Feedback text is empty'})
        
        # Create feedback entry
        feedback_entry = {
            'feedback': feedback_text,
            'timestamp': data.get('timestamp', datetime.now().isoformat()),
            'session_id': data.get('session_id', session.get('patient_id', 'unknown')),
            'username': session.get('username', 'anonymous'),
            'submitted_at': datetime.now().isoformat()
        }
        
        # Save feedback to a separate file
        feedback_dir = os.path.join(APP_DATA_DIR, 'feedback')
        os.makedirs(feedback_dir, exist_ok=True)
        
        # Generate unique feedback filename
        feedback_id = str(uuid.uuid4())[:8]
        feedback_filename = f'feedback_{datetime.now().strftime("%Y%m%d")}_{feedback_id}.json'
        feedback_path = os.path.join(feedback_dir, feedback_filename)
        
        # Save feedback
        with open(feedback_path, 'w') as f:
            json.dump(feedback_entry, f, indent=2)
        
        print(f"✅ Feedback saved successfully to {feedback_path}")
        print(f"Feedback preview: {feedback_text[:100]}...")
        
        return jsonify({
            'success': True,
            'message': 'Feedback saved successfully',
            'data': {
                'feedback_id': feedback_id,
                'saved_timestamp': feedback_entry['submitted_at']
            }
        })
        
    except Exception as e:
        print(f"❌ Error in save_feedback: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to save feedback: {str(e)}'})


@app.route('/save_feedback_with_images', methods=['POST'])
def save_feedback_with_images():
    """Save user feedback with optional multiple image attachments"""
    try:
        print("✅ Starting save_feedback_with_images")
        
        # Get form data
        feedback_text = request.form.get('feedback', '').strip()
        if not feedback_text:
            return jsonify({'success': False, 'error': 'Feedback text is empty'})
        
        session_id = request.form.get('session_id', session.get('patient_id', 'unknown'))
        image_count = int(request.form.get('image_count', 0))
        
        # Generate consistent naming convention
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        feedback_id = str(uuid.uuid4())[:8]
        base_name = f"feedback_{timestamp_str}_{feedback_id}"
        
        # Create feedback entry
        feedback_entry = {
            'feedback': feedback_text,
            'timestamp': request.form.get('timestamp', datetime.now().isoformat()),
            'session_id': session_id,
            'username': session.get('username', 'anonymous'),
            'submitted_at': datetime.now().isoformat(),
            'feedback_id': feedback_id,
            'images': [],
            'image_count': image_count
        }
        
        # Create feedback directory
        feedback_dir = os.path.join(APP_DATA_DIR, 'feedback')
        os.makedirs(feedback_dir, exist_ok=True)
        
        # Save uploaded images with consistent naming
        saved_images = []
        for i in range(image_count):
            image_key = f'image_{i}'
            if image_key in request.files:
                image_file = request.files[image_key]
                if image_file and image_file.filename:
                    # Get file extension
                    file_extension = os.path.splitext(image_file.filename)[1].lower()
                    if not file_extension:
                        file_extension = '.jpg'  # Default extension
                    
                    # Create consistent image filename
                    image_filename = f"{base_name}_img_{i+1}{file_extension}"
                    image_path = os.path.join(feedback_dir, image_filename)
                    
                    # Save image
                    image_file.save(image_path)
                    
                    # Add to feedback entry
                    image_info = {
                        'filename': image_filename,
                        'original_name': image_file.filename,
                        'path': image_path,
                        'size': os.path.getsize(image_path),
                        'uploaded_at': datetime.now().isoformat()
                    }
                    saved_images.append(image_info)
                    feedback_entry['images'].append(image_info)
                    
                    print(f"✅ Image saved: {image_filename}")
        
        # Update image count with actually saved images
        feedback_entry['image_count'] = len(saved_images)
        
        # Save feedback JSON with consistent naming
        feedback_filename = f'{base_name}.json'
        feedback_path = os.path.join(feedback_dir, feedback_filename)
        
        with open(feedback_path, 'w') as f:
            json.dump(feedback_entry, f, indent=2)
        
        print(f"✅ Feedback with {len(saved_images)} images saved successfully")
        print(f"Feedback file: {feedback_filename}")
        print(f"Feedback preview: {feedback_text[:100]}...")
        
        return jsonify({
            'success': True,
            'message': f'Feedback and {len(saved_images)} images saved successfully',
            'data': {
                'feedback_id': feedback_id,
                'feedback_filename': feedback_filename,
                'images_saved': len(saved_images),
                'saved_timestamp': feedback_entry['submitted_at']
            }
        })
        
    except Exception as e:
        print(f"❌ Error in save_feedback_with_images: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to save feedback with images: {str(e)}'})

@app.route('/save_question_responses', methods=['POST'])
def save_question_responses():
    """Save responses to follow-up questions from step 6 with complete question data"""
    try:
        print("✅ Starting save_question_responses")
        
        if not validate_session_step(5):
            return jsonify({'success': False, 'error': 'Please complete step 5 first'})
        
        data = request.get_json()
        responses = data.get('responses', {})
        original_questions = data.get('original_questions', [])
        analysis_data = data.get('analysis_data', {})
        
        print(f"📝 Received {len(responses)} question responses")
        print(f"📋 Received {len(original_questions)} original questions")
        print(f"🔍 DEBUG: analysis_data received: {analysis_data}")
        
        # Prepare comprehensive responses data for storage
        responses_data = {
            'question_responses': responses,
            'original_questions': original_questions,
            'analysis_metadata': analysis_data,
            'total_questions_generated': len(original_questions),
            'total_questions_answered': len(responses),
            'completion_rate': len(responses) / len(original_questions) if original_questions else 0,
            'completed_at': datetime.now().isoformat(),
            'session_data': {
                'questions_generated_from': {
                    'step3_vitals': True,
                    'step4_followups': True,
                    'step5_symptoms': True
                },
                'priority_distribution': {
                    'step5_priority': 0.8,
                    'step3_step4_priority': 0.2
                }
            }
        }
        
        # Also prepare organized Q&A pairs for easy access
        qa_pairs = []
        for response_index, response_data in responses.items():
            qa_pair = {
                'question_index': int(response_index),
                'question_text': response_data.get('question', ''),
                'question_category': response_data.get('category', ''),
                'answer': response_data.get('answer_value', ''),
                'answered_at': response_data.get('timestamp', ''),
                'original_question_data': original_questions[int(response_index)] if int(response_index) < len(original_questions) else {}
            }
            qa_pairs.append(qa_pair)
        
        responses_data['organized_qa_pairs'] = qa_pairs
        
        # Update step 6 data with comprehensive responses
        success = save_step_based_patient_data(
            step_number=6,
            form_data={
                'question_responses_completed': True,
                'questions_answered': len(responses),
                'questions_generated': len(original_questions)
            },
            ai_data=responses_data,
            files_data={}
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save question responses'})
        
        # Update session to mark step 6 as completed
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['step_completed'] = 6
        session.modified = True
        
        print("✅ Question responses and questions saved successfully")
        print(f"   📊 Questions generated: {len(original_questions)}")
        print(f"   📝 Questions answered: {len(responses)}")
        print(f"   📈 Completion rate: {len(responses)/len(original_questions)*100:.1f}%")
        
        # Generate clinical summary for popup
        print("🏥 Generating clinical summary...")
        summary_result = generate_clinical_summary()
        clinical_summary = ""
        summary_success = False
        
        if summary_result and summary_result.get("success"):
            clinical_summary = summary_result.get("clinical_summary", "")
            summary_success = True
            print(f"✅ Clinical summary generated successfully: {len(clinical_summary)} characters")
        else:
            print(f"❌ Clinical summary generation failed: {summary_result}")
            clinical_summary = "Clinical summary could not be generated at this time."
        
        # Check if questions were skipped to hide summary from user
        analysis_data = data.get('analysis_data', {})
        questions_skipped = analysis_data.get('questions_skipped', False)
        questions_answered = len(responses)
        
        print(f"🔍 Questions skipped: {questions_skipped}, Questions answered: {questions_answered}")
        
        # IMPORTANT: Save clinical summary to file storage BEFORE returning response
        print("💾 Saving clinical summary to file storage...")
        
        # Get existing step6 AI data 
        existing_patient_data = load_patient_data()
        existing_step6 = existing_patient_data.get('step6', {}) if existing_patient_data else {}
        existing_ai_data = existing_step6.get('ai_generated_data', {})
        
        # Prepare clinical summary data for storage
        clinical_summary_data = {
            'clinical_summary': clinical_summary,
            'summary_generated_at': datetime.now().isoformat(),
            'assessment_completed': True,
            'final_review_status': 'completed',
            'questions_skipped': questions_skipped,
            'questions_answered': questions_answered
        }
        
        # Preserve existing AI data and add clinical summary data
        if existing_ai_data:
            clinical_summary_data.update(existing_ai_data)
            clinical_summary_data.update({
                'clinical_summary': clinical_summary,
                'summary_generated_at': datetime.now().isoformat(),
                'assessment_completed': True,
                'final_review_status': 'completed',
                'questions_skipped': questions_skipped,
                'questions_answered': questions_answered
            })
        
        # Save clinical summary to step 6 data
        save_success = save_step_based_patient_data(
            step_number=6,
            form_data={
                'assessment_completed': True,
                'clinical_summary_saved': True,
                'final_completion_timestamp': datetime.now().isoformat()
            },
            ai_data=clinical_summary_data,
            files_data={}
        )
        
        if save_success:
            print("✅ Clinical summary saved successfully to step6 data")
            print(f"   📝 Summary length: {len(clinical_summary)} characters")
            print(f"   ⏰ Saved at: {datetime.now().isoformat()}")
        else:
            print("❌ Failed to save clinical summary to file storage")
        
        # Prepare response - hide clinical summary from user but still save it in background
        response_data = {
            'success': True,
            'message': 'Question responses saved successfully',
            'show_summary': False,  # Hide summary from user
            'questions_skipped': questions_skipped,
            'summary_generated': summary_success,
            'summary_saved': save_success,
            'data': {
                'responses_count': len(responses),
                'questions_count': len(original_questions),
                'completion_rate': len(responses) / len(original_questions) if original_questions else 0,
                'redirect_url': '/step7'
            }
        }
        
        # Clinical summary is saved in file storage and not sent to frontend
        print(f"📋 Clinical summary processing complete - Generated: {summary_success}, Saved: {save_success}")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in save_question_responses: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to save responses: {str(e)}'})

@app.route('/save_clinical_summary', methods=['POST'])
def save_clinical_summary():
    """Save the clinical summary when user clicks Complete Assessment in the popup"""
    try:
        print("✅ Starting save_clinical_summary")
        
        if not validate_session_step(5):
            return jsonify({'success': False, 'error': 'Please complete step 5 first'})
        
        data = request.get_json()
        clinical_summary = data.get('clinical_summary', '')
        
        if not clinical_summary:
            return jsonify({'success': False, 'error': 'No clinical summary provided'})
        
        print(f"📝 Received clinical summary: {len(clinical_summary)} characters")
        
        # Load existing patient data to preserve skip information
        existing_patient_data = load_patient_data()
        existing_step6 = existing_patient_data.get('step6', {}) if existing_patient_data else {}
        existing_ai_data = existing_step6.get('ai_generated_data', {})
        
        # Preserve existing analysis_metadata (contains questions_skipped flag)
        existing_analysis_metadata = existing_ai_data.get('analysis_metadata', {})
        
        print(f"🔍 DEBUG: Preserving existing analysis_metadata: {existing_analysis_metadata}")
        
        # Prepare clinical summary data for storage
        clinical_summary_data = {
            'clinical_summary': clinical_summary,
            'summary_accepted_at': datetime.now().isoformat(),
            'assessment_completed': True,
            'final_review_status': 'completed',
            'user_action': 'clicked_complete_assessment'
        }
        
        # Preserve existing AI data and add clinical summary data
        if existing_ai_data:
            # Merge existing data with new clinical summary data
            clinical_summary_data.update(existing_ai_data)
            clinical_summary_data.update({
                'clinical_summary': clinical_summary,
                'summary_accepted_at': datetime.now().isoformat(),
                'assessment_completed': True,
                'final_review_status': 'completed',
                'user_action': 'clicked_complete_assessment'
            })
            print(f"🔍 DEBUG: Merged ai_data keys: {list(clinical_summary_data.keys())}")
        
        # Update step 6 data with clinical summary
        success = save_step_based_patient_data(
            step_number=6,
            form_data={
                'assessment_completed': True,
                'clinical_summary_saved': True,
                'final_completion_timestamp': datetime.now().isoformat()
            },
            ai_data=clinical_summary_data,
            files_data={}
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save clinical summary'})
        
        # Update session to mark assessment as fully completed
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['assessment_completed'] = True
        session['patient_data']['clinical_summary_saved'] = True
        session.modified = True
        
        print("✅ Clinical summary saved successfully to step6 data")
        print(f"   📝 Summary length: {len(clinical_summary)} characters")
        print(f"   ⏰ Saved at: {datetime.now().isoformat()}")
        
        return jsonify({
            'success': True,
            'message': 'Clinical summary saved successfully',
            'data': {
                'summary_length': len(clinical_summary),
                'saved_at': datetime.now().isoformat(),
                'assessment_status': 'completed'
            }
        })
        
    except Exception as e:
        print(f"❌ Error in save_clinical_summary: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to save clinical summary: {str(e)}'})

@app.route('/step7')
@login_required
def step7():
    """Step 7: ICD11 Code Generation and Analysis"""
    if not validate_session_step(6):
        return redirect('/')
    return render_template('step7.html', current_step='step7')

@app.route('/check_questions_skipped_status', methods=['GET'])
@login_required
def check_questions_skipped_status():
    """Check if follow-up questions were skipped in step 6"""
    try:
        print("🔍 Checking if questions were skipped in step 6")
        
        patient_data = load_patient_data()
        if not patient_data:
            print("❌ No patient data found")
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        # Check step6 data for skip information
        step6_data = patient_data.get('step6', {})
        print(f"📋 Step6 data keys: {list(step6_data.keys())}")
        
        # Check ai_generated_data (comprehensive response data - this is the correct field name!)
        ai_generated_data = step6_data.get('ai_generated_data', {})
        print(f"📋 ai_generated_data keys: {list(ai_generated_data.keys())}")
        total_questions_answered = ai_generated_data.get('total_questions_answered', -1)
        question_responses = ai_generated_data.get('question_responses', {})
        actual_responses_count = len(question_responses)
        
        # Check analysis_metadata (this contains the analysis_data from the request)
        analysis_metadata = ai_generated_data.get('analysis_metadata', {})
        print(f"📋 analysis_metadata: {analysis_metadata}")
        questions_skipped_flag = analysis_metadata.get('questions_skipped', False)
        skip_flow_answered = analysis_metadata.get('questions_answered', -1)
        
        # Check form_data (from normal submit flow)
        form_data = step6_data.get('form_data', {})
        print(f"📋 form_data keys: {list(form_data.keys())}")
        form_questions_answered = form_data.get('questions_answered', -1)
        
        print(f"📊 Step 6 data analysis:")
        print(f"   questions_skipped_flag: {questions_skipped_flag}")
        print(f"   skip_flow_answered: {skip_flow_answered}")
        print(f"   form_questions_answered: {form_questions_answered}")
        print(f"   total_questions_answered: {total_questions_answered}")
        print(f"   actual_responses_count: {actual_responses_count}")
        
        # Determine if questions were actually skipped
        # Questions are considered skipped ONLY if:
        # 1. The skip flag is explicitly True AND there are no actual responses
        skipped = False
        
        if questions_skipped_flag and actual_responses_count == 0:
            skipped = True
            print("   ✅ Questions explicitly skipped with no responses")
        elif actual_responses_count > 0 or total_questions_answered > 0 or form_questions_answered > 0:
            skipped = False
            print("   ✅ Questions were answered (not skipped)")
        else:
            # Default: if we can't determine clearly, assume not skipped
            skipped = False
            print("   ⚠️ Unable to determine clearly, assuming not skipped")
        
        # Determine the actual number of questions answered
        questions_answered_count = max(
            total_questions_answered if total_questions_answered > 0 else 0,
            actual_responses_count,
            form_questions_answered if form_questions_answered > 0 else 0
        )
        
        print(f"   🎯 Final result: skipped={skipped}, answered={questions_answered_count}")
        
        return jsonify({
            'success': True,
            'questions_skipped': skipped,
            'questions_answered': questions_answered_count,
            'debug_info': {
                'skip_flag': questions_skipped_flag,
                'skip_flow_count': skip_flow_answered,
                'form_flow_count': form_questions_answered,
                'ai_data_count': total_questions_answered,
                'actual_responses': actual_responses_count,
                'analysis_metadata': analysis_metadata
            }
        })
        
    except Exception as e:
        print(f"❌ Error checking questions skipped status: {str(e)}")
        return jsonify({
            'success': False, 
            'error': str(e),
            'questions_skipped': False  # Default to false on error
        })

@app.route('/get_clinical_summary', methods=['GET'])
def get_clinical_summary():
    """Retrieve the clinical summary from step6 data"""
    try:
        print("✅ Getting clinical summary from step6 data")
        
        if not validate_session_step(6):
            return jsonify({'success': False, 'error': 'Please complete step 6 first'})
        
        # Load patient data and get clinical summary from step6
        patient_data = load_patient_data()
        if not patient_data:
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        step6_data = patient_data.get('step6', {})
        ai_data = step6_data.get('ai_generated_data', {})
        
        # Look for clinical summary in the AI data
        clinical_summary = ai_data.get('clinical_summary', '')
        
        if not clinical_summary:
            return jsonify({'success': False, 'error': 'No clinical summary found in step6 data'})
        
        print(f"✅ Clinical summary retrieved: {len(clinical_summary)} characters")
        
        return jsonify({
            'success': True,
            'clinical_summary': clinical_summary,
            'data': {
                'summary_length': len(clinical_summary),
                'retrieved_at': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        print(f"❌ Error in get_clinical_summary: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to retrieve clinical summary: {str(e)}'})

@app.route('/format_clinical_summary', methods=['POST'])
def format_clinical_summary():
    """Format clinical summary text using LLM for professional medical formatting"""
    try:
        print("✅ Starting format_clinical_summary with LLM")
        
        data = request.get_json()
        raw_summary = data.get('text', '').strip()
        
        if not raw_summary:
            return jsonify({'success': False, 'error': 'No clinical summary text provided'})
        
        if len(raw_summary) < 10:
            return jsonify({'success': False, 'error': 'Clinical summary too short to format'})
        
        print(f"📝 Formatting clinical summary: {len(raw_summary)} characters")
        
        # Create formatting prompt for LLM
        formatting_prompt = f"""Please format the following clinical summary text into a professional, well-structured medical document using this EXACT format structure:

Patient Clinical Summary

Patient Information:
- Name: [Extract or use "Not documented"]
- Age: [Extract or use "Not documented"]  
- Gender: [Extract or use "Not documented"]

Vital Signs:
- Temperature: [Extract with normal range if elevated/low]
- Oxygen Saturation: [Extract with interpretation if abnormal]
- Blood Glucose: [Extract with interpretation]
- Other vitals: [Include any other vital signs mentioned]

Presenting Complaints:
- Chief Complaint: [Main symptoms/complaints]
- Symptom Analysis:
  - [Symptom 1]: [Details about severity, description]
  - [Symptom 2]: [Details]
- Additional Symptoms:
  - [List other symptoms with yes/no and details]
  - Impact on daily activities: [Extract information]

Clinical Findings:
- [List clinical findings and examination results]
- [Include negative findings where mentioned]

Detailed Symptom Assessment:
- Onset:
  - [Symptom]: [Timeline information]
- Characteristics:
  - [Describe symptom characteristics]
- Severity:
  - [Rate severity with descriptions]
- Relieving Factors:
  - [What improves symptoms]
- Aggravating Factors:
  - [What worsens symptoms]
- Temporal Pattern:
  - [When symptoms occur/worsen]
- Associated Symptoms:
  - [Related symptoms]
- Functional Impact:
  - [How symptoms affect daily life]

Assessment Summary:
- [Comprehensive clinical assessment paragraph summarizing the case]

IMPORTANT RULES:
1. Extract information from the original text - do not add clinical details not present
2. Use "Not documented" for missing information
3. Include normal ranges in parentheses for abnormal values
4. Maintain all medical facts exactly as provided
5. Remove excessive spaces, dots, and formatting inconsistencies
6. Use bullet points and proper indentation as shown
7. Keep the exact section headers as shown above

ORIGINAL CLINICAL SUMMARY:
{raw_summary}

Please return ONLY the formatted clinical summary following this exact structure."""

        # Use the existing call_gpt4 function for formatting
        try:
            formatted_summary = call_gpt4(formatting_prompt)
            
            # Clean up any potential formatting issues from LLM response
            formatted_summary = formatted_summary.strip()
            
            # Remove any markdown formatting that might have been added
            formatted_summary = formatted_summary.replace('```', '').replace('**', '').replace('##', '')
            
            # Ensure consistent line breaks
            formatted_summary = '\n'.join(line.strip() for line in formatted_summary.split('\n') if line.strip())
            
            print(f"✅ Clinical summary formatted successfully: {len(formatted_summary)} characters")
            
            return jsonify({
                'success': True,
                'formatted_text': formatted_summary,
                'original_length': len(raw_summary),
                'formatted_length': len(formatted_summary),
                'formatted_at': datetime.now().isoformat()
            })
            
        except Exception as llm_error:
            print(f"❌ LLM formatting error: {str(llm_error)}")
            
            # Fallback to basic formatting if LLM fails
            basic_formatted = basic_clinical_formatting(raw_summary)
            
            return jsonify({
                'success': True,
                'formatted_text': basic_formatted,
                'fallback_used': True,
                'original_length': len(raw_summary),
                'formatted_length': len(basic_formatted),
                'formatted_at': datetime.now().isoformat(),
                'note': 'Basic formatting used due to LLM unavailability'
            })
        
    except Exception as e:
        print(f"❌ Error in format_clinical_summary: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to format clinical summary: {str(e)}'})

def basic_clinical_formatting(text):
    """Basic fallback formatting for clinical summary following the structured format"""
    if not text:
        return text
    
    # Remove excessive spaces and dots
    formatted = text.strip()
    formatted = ' '.join(formatted.split())  # Normalize whitespace
    formatted = formatted.replace('....', '.').replace('...', '.').replace('..', '.')
    
    # Start with basic structure
    result = "Patient Clinical Summary\n\n"
    
    # Add basic sections with extracted information where possible
    result += "Patient Information:\n"
    result += "- Name: Not documented\n"
    result += "- Age: Not documented\n"
    result += "- Gender: Not documented\n\n"
    
    result += "Vital Signs:\n"
    result += "- [Vital signs information from original text]\n\n"
    
    result += "Presenting Complaints:\n"
    result += "- Chief Complaint: [Main complaints from text]\n\n"
    
    result += "Clinical Findings:\n"
    result += "- [Clinical examination findings]\n\n"
    
    result += "Assessment Summary:\n"
    result += f"- {formatted}\n"
    
    return result

@app.route('/get_patient_data_summary', methods=['GET'])
def get_patient_data_summary():
    """Get a comprehensive summary of all patient data for differential questioning"""
    try:
        print("📊 Generating patient data summary for differential questioning")
        
        if not validate_session_step(6):
            return jsonify({'success': False, 'error': 'Please complete step 6 first'})
        
        patient_data = load_patient_data()
        if not patient_data:
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        summary_parts = []
        
        # Step 1: Symptoms
        step1_data = patient_data.get('step1', {})
        if step1_data:
            symptoms = step1_data.get('symptoms', {})
            if symptoms:
                symptom_list = []
                for symptom, details in symptoms.items():
                    severity = details.get('severity', 'N/A')
                    symptom_list.append(f'{symptom} (severity: {severity})')
                summary_parts.append(f"Symptoms: {', '.join(symptom_list)}")
        
        # Step 2: Vitals
        step2_data = patient_data.get('step2', {})
        if step2_data:
            vitals_text = []
            for key, value in step2_data.items():
                if key != 'timestamp' and value:
                    vitals_text.append(f"{key}: {value}")
            if vitals_text:
                summary_parts.append(f"Vitals: {', '.join(vitals_text)}")
        
        # Step 3: Medical History
        step3_data = patient_data.get('step3', {})
        if step3_data:
            history_text = []
            for key, value in step3_data.items():
                if key != 'timestamp' and value:
                    if isinstance(value, list):
                        history_text.append(f"{key}: {', '.join(value)}")
                    else:
                        history_text.append(f"{key}: {value}")
            if history_text:
                summary_parts.append(f"Medical History: {', '.join(history_text)}")
        
        # Step 4: Physical Examination  
        step4_data = patient_data.get('step4', {})
        if step4_data:
            exam_text = []
            for key, value in step4_data.items():
                if key != 'timestamp' and value:
                    exam_text.append(f"{key}: {value}")
            if exam_text:
                summary_parts.append(f"Physical Exam: {', '.join(exam_text)}")
        
        # Step 5: Symptoms and Medical Documents
        step5_data = patient_data.get('step5', {})
        if step5_data:
            lab_text = []
            for key, value in step5_data.items():
                if key not in ['timestamp', 'test_results'] and value:
                    lab_text.append(f"{key}: {value}")
            
            # Add specific test results
            test_results = step5_data.get('test_results', {})
            if test_results:
                for test, result in test_results.items():
                    lab_text.append(f"{test}: {result}")
            
            if lab_text:
                summary_parts.append(f"Symptoms & Lab Results: {', '.join(lab_text)}")
        
        # Step 5 AI Data: Medical Documents and Critical Findings
        step5_ai_data = patient_data.get('steps', {}).get('step5', {}).get('ai_generated_data', {})
        if step5_ai_data:
            # Include medical documents information
            medical_docs = step5_ai_data.get('medical_documents', [])
            if medical_docs:
                doc_summaries = []
                for doc in medical_docs:
                    doc_category = doc.get('category', 'Unknown')
                    doc_filename = doc.get('filename', 'Unknown')
                    doc_caption = doc.get('caption', '')
                    
                    # Include key insights from the document
                    insights = doc.get('insights', {})
                    if insights:
                        concerns = insights.get('concerns', [])
                        findings = insights.get('key_findings', [])
                        
                        doc_summary_parts = [f"{doc_category} document ({doc_filename})"]
                        if doc_caption:
                            doc_summary_parts.append(f"Purpose: {doc_caption}")
                        if concerns:
                            doc_summary_parts.append(f"Concerns: {', '.join(concerns[:3])}")  # Limit to top 3
                        if findings:
                            doc_summary_parts.append(f"Key findings: {', '.join(findings[:3])}")  # Limit to top 3
                        
                        doc_summaries.append(" - ".join(doc_summary_parts))
                    else:
                        doc_summaries.append(f"{doc_category} document ({doc_filename}): {doc_caption}")
                
                if doc_summaries:
                    summary_parts.append(f"Medical Documents: {'; '.join(doc_summaries)}")
            
            # Include critical medical findings
            critical_findings = step5_ai_data.get('critical_medical_findings', [])
            if critical_findings:
                critical_summary = []
                for finding in critical_findings:
                    source = finding.get('source_document', 'Unknown')
                    concern = finding.get('finding', '')
                    critical_summary.append(f"{concern} (from {source})")
                summary_parts.append(f"Critical Medical Findings: {'; '.join(critical_summary)}")
            
            # Include symptom insights if available
            symptom_insights = step5_ai_data.get('symptom_insights', {})
            if symptom_insights:
                medical_labels = symptom_insights.get('medical_labels', [])
                if medical_labels:
                    labels_summary = [f"{label.get('condition', 'Unknown')}: {label.get('confidence', 'N/A')}" for label in medical_labels[:5]]  # Top 5
                    summary_parts.append(f"AI Symptom Analysis: {'; '.join(labels_summary)}")
        
        comprehensive_summary = "; ".join(summary_parts) if summary_parts else "No comprehensive patient data available"
        
        print(f"✅ Generated patient data summary: {len(comprehensive_summary)} characters")
        
        return jsonify({
            'success': True,
            'patient_data_summary': comprehensive_summary,
            'data': {
                'summary_length': len(comprehensive_summary),
                'steps_included': list(patient_data.keys()),
                'generated_at': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        print(f"❌ Error in get_patient_data_summary: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to generate patient data summary: {str(e)}'})

@app.route('/generate_diagnostic_tests', methods=['POST'])
def generate_diagnostic_tests():
    """Generate diagnostic test recommendations based on narrowed ICD codes"""
    try:
        print("🧪 Starting diagnostic tests generation")
        
        data = request.get_json()
        narrowed_icd_codes = data.get('icd_codes', [])
        clinical_summary = data.get('clinical_summary', '')
        patient_data_summary = data.get('patient_data_summary', '')
        elimination_history = data.get('elimination_history', [])
        
        if not narrowed_icd_codes:
            return jsonify({'success': False, 'error': 'No ICD codes provided for diagnostic test generation'})
        
        print(f"🔍 Generating diagnostic tests for {len(narrowed_icd_codes)} ICD codes")
        
        # Generate diagnostic tests using LLM
        tests_result = generate_diagnostic_tests_with_llm(
            narrowed_icd_codes, clinical_summary, patient_data_summary, elimination_history
        )
        
        if not tests_result or not tests_result.get('success'):
            return jsonify({'success': False, 'error': 'Failed to generate diagnostic tests recommendations'})
        
        print("✅ Diagnostic tests generated successfully")
        
        return jsonify({
            'success': True,
            'tests': tests_result.get('diagnostic_tests', []),  # JavaScript expects 'tests'
            'diagnostic_tests': tests_result.get('diagnostic_tests', []),  # Backend compatibility
            'priority_tests': tests_result.get('priority_tests', []),
            'reasoning': tests_result.get('reasoning', ''),
            'analysis_notes': tests_result.get('reasoning', ''),  # JavaScript expects 'analysis_notes'
            'estimated_timeline': tests_result.get('estimated_timeline', ''),
            'cost_considerations': tests_result.get('cost_considerations', ''),
            'clinical_notes': tests_result.get('clinical_notes', '')
        })
        
    except Exception as e:
        print(f"❌ Error in generate_diagnostic_tests: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to generate diagnostic tests: {str(e)}'})

def generate_diagnostic_tests_with_llm(icd_codes, clinical_summary, patient_data_summary, elimination_history):
    """Generate diagnostic test recommendations using LLM based on ICD codes"""
    try:
        print("🤖 Generating diagnostic tests with LLM")
        
        # Format ICD codes for prompt
        codes_text = "\n".join([f"- {code['code']}: {code['title']} (Confidence: {code['confidence']}%)" for code in icd_codes])
        
        # Format elimination history for context
        history_text = ""
        if elimination_history:
            history_text = "\nDifferential diagnosis history:\n" + "\n".join([
                f"- Eliminated {item['eliminated_code']} based on: {item['answer']} (Reasoning: {item['reasoning']})" 
                for item in elimination_history
            ])
        
        prompt_template = load_prompt("diagnostic_tests")
        prompt = prompt_template.format(
            clinical_summary=clinical_summary,
            patient_data_summary=patient_data_summary,
            codes_text=codes_text,
            history_text=history_text
        )

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": load_prompt("diagnostic_tests_system")},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        print(f"🔍 Raw diagnostic tests response: {result_text[:200]}...")
        
        # Clean the response to ensure it's valid JSON
        if not result_text.startswith('{'):
            start = result_text.find('{')
            end = result_text.rfind('}') + 1
            if start != -1 and end != -1:
                result_text = result_text[start:end]
        
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            print(f"📄 Full response text: {result_text}")
            return {'success': False, 'error': 'Invalid JSON response from AI'}
        
        if not result.get('success'):
            print(f"❌ LLM returned success=False: {result}")
            return {'success': False, 'error': result.get('error', 'Unknown AI error')}
        
        diagnostic_tests = result.get('diagnostic_tests', [])
        print(f"✅ Generated {len(diagnostic_tests)} diagnostic test recommendations")
        
        return result
        
    except Exception as e:
        print(f"❌ Error generating diagnostic tests: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/generate_icd_codes', methods=['POST'])
def generate_icd_codes():
    """Generate ICD11 codes based on clinical summary"""
    try:
        print("✅ Starting ICD11 code generation with LLM - DEBUG MODE")
        print(f"🔍 Request method: {request.method}")
        print(f"🔍 Request content type: {request.content_type}")
        
        if not validate_session_step(6):
            print("❌ Session validation failed - step 6 not completed")
            return jsonify({'success': False, 'error': 'Please complete step 6 first'})
        
        print("✅ Session validation passed")
        
        data = request.get_json()
        print(f"🔍 Received data: {data}")
        
        if not data:
            print("❌ No JSON data received")
            return jsonify({'success': False, 'error': 'No data received'})
            
        clinical_summary = data.get('clinical_summary', '')
        patient_contact_info = data.get('patient_contact_info', {})
        
        print(f"📝 Clinical summary length: {len(clinical_summary)}")
        print(f"📞 Patient contact info: {patient_contact_info}")
        
        if not clinical_summary:
            print("❌ No clinical summary provided")
            return jsonify({'success': False, 'error': 'No clinical summary provided'})
        
        print(f"📝 Generating ICD codes for summary: {len(clinical_summary)} characters")
        
        # Get all patient data for comprehensive analysis
        print("📂 Loading patient data...")
        patient_data = load_patient_data()
        if not patient_data:
            print("❌ No patient data available")
            return jsonify({'success': False, 'error': 'No patient data available'})
        
        print(f"✅ Patient data loaded: {len(patient_data)} sections")
        
        # Generate ICD11 codes using LLM
        print("🤖 Calling LLM for ICD code generation...")
        icd_result = generate_icd11_codes_with_llm(clinical_summary, patient_data)
        
        if not icd_result or not icd_result.get('success'):
            print(f"❌ LLM generation failed: {icd_result}")
            return jsonify({'success': False, 'error': 'Failed to generate ICD codes - LLM error'})
        
        icd_codes = icd_result.get('icd_codes', [])
        
        # Save the generated ICD codes to step7 data
        icd_data = {
            'icd_codes_generated': True,
            'icd_codes': icd_codes,
            'clinical_summary_used': clinical_summary,
            'generation_timestamp': datetime.now().isoformat(),
            'total_codes_generated': len(icd_codes),
            'llm_analysis': icd_result.get('analysis_notes', '')
        }
        
        # Save to step7
        # Get referring doctor details
        referring_doctor_details = get_referring_doctor_by_id(patient_contact_info.get('referringDoctor', ''))
        referring_doctor_name = ''
        if referring_doctor_details:
            referring_doctor_name = f"{referring_doctor_details['first_name']} {referring_doctor_details['last_name']}"
        
        success = save_step_based_patient_data(
            step_number=7,
            form_data={
                'icd_generation_completed': True,
                'codes_generated': len(icd_codes),
                'patient_email': patient_contact_info.get('patientEmail', ''),
                'patient_phone': patient_contact_info.get('patientPhone', ''),
                'referring_doctor_id': patient_contact_info.get('referringDoctor', ''),
                'referring_doctor_name': referring_doctor_name,
                'referring_doctor_phone': patient_contact_info.get('referringDoctorPhone', ''),
                'referring_doctor_email': patient_contact_info.get('referringDoctorEmail', ''),
                'referring_doctor_details': referring_doctor_details,
                'contact_info_completed': True,
                'contact_info_timestamp': datetime.now().isoformat()
            },
            ai_data=icd_data,
            files_data={}
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save ICD codes'})
        
        print(f"✅ ICD11 codes generated and saved: {len(icd_codes)} codes")
        
        return jsonify({
            'success': True,
            'icd_codes': icd_codes,
            'analysis_notes': icd_result.get('analysis_notes', ''),
            'data': {
                'codes_count': len(icd_codes),
                'generated_at': datetime.now().isoformat(),
                'summary_length': len(clinical_summary)
            }
        })
        
    except Exception as e:
        print(f"❌ Error in generate_icd_codes: {str(e)}")
        import traceback
        print("📄 Full traceback:")
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to generate ICD codes: {str(e)}'})

def get_referring_doctor_by_id(doctor_id):
    """Get referring doctor details by ID"""
    referring_doctors = [
        {'id': 1, 'first_name': 'Rajesh', 'last_name': 'Sharma', 'phone_number': '1111111111', 'email_address': 'rajesh.sharma@hospital.com', 'area_of_expertise': 'Cardiology'},
        {'id': 2, 'first_name': 'Priya', 'last_name': 'Patel', 'phone_number': '2222222222', 'email_address': 'priya.patel@clinic.com', 'area_of_expertise': 'Pediatrics'},
        {'id': 3, 'first_name': 'Amit', 'last_name': 'Kumar', 'phone_number': '3333333333', 'email_address': 'amit.kumar@medical.com', 'area_of_expertise': 'Orthopedics'},
        {'id': 4, 'first_name': 'Sunita', 'last_name': 'Singh', 'phone_number': '4444444444', 'email_address': 'sunita.singh@healthcare.com', 'area_of_expertise': 'Dermatology'},
        {'id': 5, 'first_name': 'Vikash', 'last_name': 'Gupta', 'phone_number': '5555555555', 'email_address': 'vikash.gupta@hospital.com', 'area_of_expertise': 'Neurology'},
        {'id': 6, 'first_name': 'Meera', 'last_name': 'Jain', 'phone_number': '6666666666', 'email_address': 'meera.jain@clinic.com', 'area_of_expertise': 'Gynecology'},
        {'id': 7, 'first_name': 'Rohit', 'last_name': 'Verma', 'phone_number': '7777777777', 'email_address': 'rohit.verma@medical.com', 'area_of_expertise': 'Gastroenterology'},
        {'id': 8, 'first_name': 'Kavita', 'last_name': 'Agarwal', 'phone_number': '8888888888', 'email_address': 'kavita.agarwal@healthcare.com', 'area_of_expertise': 'Pulmonology'},
        {'id': 9, 'first_name': 'Sanjay', 'last_name': 'Mishra', 'phone_number': '9999999999', 'email_address': 'sanjay.mishra@hospital.com', 'area_of_expertise': 'Oncology'}
    ]
    
    try:
        doctor_id = int(doctor_id)
        for doctor in referring_doctors:
            if doctor['id'] == doctor_id:
                return doctor
    except (ValueError, TypeError):
        pass
    
    return None

@app.route('/submit_case', methods=['POST'])
def submit_case():
    """Submit case to database after step7 completion"""
    try:
        print("✅ Starting case submission process")
        
        # Get patient data from JSON file
        patient_data = load_patient_data()
        if not patient_data:
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        # Check if step7 is completed
        step7_data = patient_data.get('step7', {})
        if not step7_data or not step7_data.get('step_completed', False):
            return jsonify({'success': False, 'error': 'Step 7 not completed yet'})
        
        # Generate unique case number
        case_number = generate_case_number()
        print(f"📋 Generated case number: {case_number}")
        
        # Prepare step7 data as JSON string for database
        step7_json_data = json.dumps(step7_data, indent=2, default=str)
        
        # Insert into database
        connection = get_sqlite_connection()
        if not connection:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        try:
            cursor = connection.cursor()
            
            insert_query = """
                INSERT INTO cases (case_number, details, status, feedback) 
                VALUES (?, ?, ?, ?)
            """
            
            cursor.execute(insert_query, (
                case_number,
                step7_json_data,
                'pending_review',
                ''  # blank feedback
            ))
            
            connection.commit()
            print(f"✅ Case {case_number} inserted successfully")
            
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'case_number': case_number,
                'status': 'pending_review',
                'message': 'Case submitted successfully for expert review'
            })
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            if connection:
                connection.rollback()
                connection.close()
            return jsonify({'success': False, 'error': f'Database error: {str(e)}'})
            
    except Exception as e:
        print(f"❌ Error in case submission: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to submit case: {str(e)}'})

@app.route('/generate_differential_question', methods=['POST'])
def generate_differential_question():
    """Generate a differential question to eliminate one ICD code"""
    try:
        print("🔍 Starting differential question generation")
        
        data = request.get_json()
        remaining_icd_codes = data.get('icd_codes', [])
        clinical_summary = data.get('clinical_summary', '')
        patient_data_summary = data.get('patient_data_summary', '')
        elimination_history = data.get('elimination_history', [])
        
        if len(remaining_icd_codes) <= 2:
            return jsonify({
                'success': False, 
                'error': 'Cannot eliminate more codes. Already at target of 2 codes.'
            })
        
        print(f"📊 Generating question for {len(remaining_icd_codes)} remaining codes")
        
        # Generate differential question using LLM
        question_result = generate_differential_question_with_llm(
            remaining_icd_codes, clinical_summary, patient_data_summary, elimination_history
        )
        
        if not question_result or not question_result.get('success'):
            return jsonify({'success': False, 'error': 'Failed to generate differential question'})
        
        print("✅ Differential question generated successfully")
        
        return jsonify({
            'success': True,
            'question': question_result.get('question'),
            'target_code_to_eliminate': question_result.get('target_code_to_eliminate'),
            'reasoning': question_result.get('reasoning'),
            'answer_options': question_result.get('answer_options', [])
        })
        
    except Exception as e:
        print(f"❌ Error in generate_differential_question: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to generate question: {str(e)}'})

@app.route('/process_differential_answer', methods=['POST'])
def process_differential_answer():
    """Process the answer and eliminate the appropriate ICD code"""
    try:
        print("🔄 Processing differential answer")
        
        data = request.get_json()
        answer = data.get('answer')
        remaining_icd_codes = data.get('icd_codes', [])
        target_code_to_eliminate = data.get('target_code_to_eliminate')
        question = data.get('question')
        clinical_summary = data.get('clinical_summary', '')
        
        print(f"📝 Answer: {answer}")
        print(f"🎯 Target to eliminate: {target_code_to_eliminate}")
        print(f"📊 Current codes count: {len(remaining_icd_codes)}")
        print(f"📋 Current codes: {[code['code'] for code in remaining_icd_codes]}")
        
        # Validate we have codes to eliminate
        if len(remaining_icd_codes) <= 2:
            return jsonify({
                'success': False, 
                'error': 'Already at target of 2 or fewer codes. Cannot eliminate more.'
            })
        
        # Use LLM to determine which code to eliminate
        elimination_result = process_answer_with_llm(
            answer, question, remaining_icd_codes, target_code_to_eliminate, clinical_summary
        )
        
        if not elimination_result or not elimination_result.get('success'):
            return jsonify({'success': False, 'error': 'Failed to process answer'})
        
        eliminated_code = elimination_result.get('eliminated_code', '').strip()
        reasoning = elimination_result.get('reasoning', '')
        
        print(f"🎯 Code to eliminate: '{eliminated_code}'")
        
        # Validate eliminated code exists in current list
        current_codes = [code['code'] for code in remaining_icd_codes]
        if eliminated_code not in current_codes:
            print(f"❌ Error: Code '{eliminated_code}' not found in current codes {current_codes}")
            return jsonify({
                'success': False, 
                'error': f'Invalid elimination: Code {eliminated_code} not in current list'
            })
        
        # Remove the eliminated code from the list
        updated_codes = [code for code in remaining_icd_codes if code['code'] != eliminated_code]
        
        print(f"✅ Eliminated code: {eliminated_code}")
        print(f"📊 Updated codes count: {len(updated_codes)}")
        print(f"📋 Updated codes: {[code['code'] for code in updated_codes]}")
        
        # Verify elimination actually happened
        if len(updated_codes) != len(remaining_icd_codes) - 1:
            print(f"❌ Elimination failed! Expected {len(remaining_icd_codes) - 1} codes, got {len(updated_codes)}")
            return jsonify({
                'success': False,
                'error': f'Elimination verification failed. Expected {len(remaining_icd_codes) - 1} codes, got {len(updated_codes)}'
            })
        
        return jsonify({
            'success': True,
            'eliminated_code': eliminated_code,
            'updated_icd_codes': updated_codes,
            'reasoning': reasoning,
            'remaining_count': len(updated_codes),
            'verification': {
                'original_count': len(remaining_icd_codes),
                'final_count': len(updated_codes),
                'eliminated_successfully': True
            }
        })
        
    except Exception as e:
        print(f"❌ Error in process_differential_answer: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to process answer: {str(e)}'})

def generate_differential_question_with_llm(icd_codes, clinical_summary, patient_data_summary, elimination_history):
    """Generate a targeted differential question to eliminate one specific ICD code"""
    try:
        print("🤖 Generating differential question with LLM")
        
        # Format ICD codes for prompt
        codes_text = "\n".join([f"- {code['code']}: {code['title']} (Confidence: {code['confidence']}%)" for code in icd_codes])
        current_codes = [code['code'] for code in icd_codes]
        
        # Format elimination history with QUESTIONS to prevent repetition
        history_text = ""
        eliminated_codes = []
        previous_questions = []
        
        if elimination_history:
            eliminated_codes = [item.get('eliminated_code', '') for item in elimination_history if item.get('eliminated_code')]
            previous_questions = [item.get('question', '') for item in elimination_history if item.get('question')]
            
            # Build comprehensive history text
            history_text = "PREVIOUSLY ASKED QUESTIONS (DO NOT REPEAT THESE OR SIMILAR):\n"
            for i, item in enumerate(elimination_history, 1):
                question = item.get('question', 'N/A')
                answer = item.get('answer', 'N/A')
                eliminated = item.get('eliminated_code', 'N/A')
                
                history_text += f"{i}. Question: \"{question}\"\n"
                history_text += f"   Answer: {answer}\n"
                history_text += f"   Result: Eliminated {eliminated}\n\n"
            
            history_text += f"ELIMINATED CODES (NEVER TARGET THESE): {', '.join(eliminated_codes)}\n\n"
            
            # Add specific instructions to avoid similar questions
            if previous_questions:
                history_text += "AVOID ASKING SIMILAR QUESTIONS ABOUT:\n"
                question_topics = []
                for q in previous_questions:
                    if 'pain' in q.lower():
                        question_topics.append("- Pain characteristics, location, or intensity")
                    if 'when' in q.lower() or 'time' in q.lower() or 'start' in q.lower():
                        question_topics.append("- Timing or onset of symptoms")  
                    if 'where' in q.lower() or 'location' in q.lower():
                        question_topics.append("- Location or anatomical areas")
                    if 'trigger' in q.lower() or 'cause' in q.lower() or 'bring' in q.lower():
                        question_topics.append("- Triggers or precipitating factors")
                    if 'better' in q.lower() or 'worse' in q.lower() or 'help' in q.lower():
                        question_topics.append("- Things that make symptoms better/worse")
                    if 'family' in q.lower() or 'history' in q.lower():
                        question_topics.append("- Family or medical history")
                    if 'see' in q.lower() or 'notice' in q.lower() or 'visual' in q.lower():
                        question_topics.append("- Visual symptoms or observations")
                    if 'feel' in q.lower() or 'sensation' in q.lower():
                        question_topics.append("- Physical sensations or feelings")
                
                # Remove duplicates and add to history
                unique_topics = list(set(question_topics))
                history_text += '\n'.join(unique_topics) + "\n\n"
                history_text += "FIND A COMPLETELY DIFFERENT ASPECT TO ASK ABOUT!\n"
        
        print(f"🔍 Current available codes: {current_codes}")
        print(f"🔍 Previously eliminated codes: {eliminated_codes}")
        print(f"🔍 Previous questions asked: {len(previous_questions)}")
        
        prompt_template = load_prompt("differential_question")
        prompt = prompt_template.format(
            clinical_summary=clinical_summary,
            patient_data_summary=patient_data_summary,
            codes_text=codes_text,
            history_text=history_text,
            current_codes=', '.join(current_codes),
            eliminated_codes=', '.join(eliminated_codes) if eliminated_codes else 'None eliminated yet'
        )

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": load_prompt("differential_question_system")},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3  # Increased slightly to add more creativity and avoid repetition
        )
        
        result_text = response.choices[0].message.content.strip()
        print(f"🔍 Raw LLM response: {result_text}")
        
        # Clean the response to ensure it's valid JSON
        if not result_text.startswith('{'):
            start = result_text.find('{')
            end = result_text.rfind('}') + 1
            if start != -1 and end != -1:
                result_text = result_text[start:end]
        
        result = json.loads(result_text)
        target_code = result.get('target_code_to_eliminate', '').strip()
        new_question = result.get('question', '').strip()
        
        print(f"🔍 Parsed target_code: '{target_code}'")
        print(f"🔍 Generated question: '{new_question}'")
        
        # Check for question similarity to prevent repetition
        if elimination_history and new_question:
            for prev_item in elimination_history:
                prev_question = prev_item.get('question', '').strip()
                if prev_question:
                    # Simple similarity check - look for common key words
                    new_words = set(new_question.lower().split())
                    prev_words = set(prev_question.lower().split())
                    common_words = new_words.intersection(prev_words)
                    
                    # Remove common stop words from comparison
                    stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for', 'of', 'as', 'by', 'do', 'does', 'did', 'you', 'your', 'have', 'has', 'had', 'this', 'that', 'these', 'those'}
                    meaningful_common = common_words - stop_words
                    
                    # If too many meaningful words overlap, it might be too similar
                    if len(meaningful_common) >= 3:
                        print(f"⚠️ Question might be too similar to previous: '{prev_question}'")
                        print(f"⚠️ Common words: {meaningful_common}")
                        
                        # Add a note to the reasoning to help track this
                        result['reasoning'] += " (Generated with similarity check)"
        
        # Validate the target code exists in current list
        if not target_code or target_code not in current_codes:
            print(f"❌ Invalid target code: '{target_code}' not in {current_codes}")
            # Fallback: target the first available code
            target_code = current_codes[0] if current_codes else ''
            result['target_code_to_eliminate'] = target_code
            result['reasoning'] = f"Fallback targeting due to invalid LLM response"
            print(f"🔧 Fallback: Targeting '{target_code}'")
        
        print(f"✅ Generated question targeting: {result.get('target_code_to_eliminate')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error generating differential question: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def process_answer_with_llm(answer, question, icd_codes, target_code_to_eliminate, clinical_summary):
    """Process the user's answer and determine which ICD code to eliminate"""
    try:
        print("🤖 Processing answer with LLM")
        
        codes_text = "\n".join([f"- {code['code']}: {code['title']}" for code in icd_codes])
        current_codes = [code['code'] for code in icd_codes]
        
        print(f"🔍 Current codes available: {current_codes}")
        print(f"🎯 Target code to eliminate: {target_code_to_eliminate}")
        
        prompt_template = load_prompt("answer_processing")
        prompt = prompt_template.format(
            clinical_summary=clinical_summary,
            codes_text=codes_text,
            question=question,
            answer=answer,
            target_code_to_eliminate=target_code_to_eliminate,
            current_codes=', '.join(current_codes)
        )

        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": load_prompt("answer_processing_system")},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.1
        )
        
        result_text = response.choices[0].message.content.strip()
        print(f"🔍 Raw LLM response: {result_text}")
        
        # Clean the response to ensure it's valid JSON
        if not result_text.startswith('{'):
            # Find the JSON part if there's extra text
            start = result_text.find('{')
            end = result_text.rfind('}') + 1
            if start != -1 and end != -1:
                result_text = result_text[start:end]
        
        result = json.loads(result_text)
        eliminated_code = result.get('eliminated_code', '').strip()
        
        print(f"🔍 Parsed eliminated_code: '{eliminated_code}'")
        
        # Validate the eliminated code exists in current list
        if not eliminated_code or eliminated_code not in current_codes:
            print(f"❌ Invalid eliminated code: '{eliminated_code}' not in {current_codes}")
            # Fallback: eliminate the target code or the last code
            if target_code_to_eliminate and target_code_to_eliminate in current_codes:
                eliminated_code = target_code_to_eliminate
                result['eliminated_code'] = eliminated_code
                result['reasoning'] = f"Fallback elimination of target code due to invalid LLM response"
                print(f"🔧 Fallback: Eliminating target code '{eliminated_code}'")
            else:
                # Last resort: eliminate the last code in the list
                eliminated_code = current_codes[-1]
                result['eliminated_code'] = eliminated_code  
                result['reasoning'] = f"Emergency fallback elimination due to LLM error"
                print(f"🚨 Emergency fallback: Eliminating last code '{eliminated_code}'")
        
        print(f"✅ Final decision: Eliminate {eliminated_code}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error processing answer: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Emergency fallback if everything fails
        if icd_codes and len(icd_codes) > 0:
            fallback_code = icd_codes[-1]['code']
            print(f"🚨 Complete fallback: Eliminating {fallback_code}")
            return {
                "success": True,
                "eliminated_code": fallback_code,
                "reasoning": "Emergency elimination due to system error"
            }
        
        return None

def generate_icd11_codes_with_llm(clinical_summary, patient_data):
    """Generate ICD11 codes using LLM API based on WHO official codes"""
    try:
        print("🤖 Generating ICD11 codes with LLM...")
        print(f"📝 Input summary length: {len(clinical_summary)}")
        print(f"📊 Patient data keys: {list(patient_data.keys())}")
        
        # Extract relevant data from patient data
        symptoms_data = patient_data.get('step1', {})
        vitals_data = patient_data.get('step2', {})
        followup_data = patient_data.get('step4', {})
        
        # Build comprehensive context for LLM
        context = f"""
Clinical Summary:
{clinical_summary}

Primary Symptoms:
- Chief Complaint: {symptoms_data.get('complaint_text', 'Not specified')}
- Duration: {symptoms_data.get('symptom_duration', 'Not specified')}
- Pain Level: {symptoms_data.get('pain_level', 'Not specified')}

Vital Signs:
- Temperature: {vitals_data.get('temperature', 'Not recorded')} {vitals_data.get('temperature_unit', '')}
- Oxygen Saturation: {vitals_data.get('oxygen_saturation', 'Not recorded')}%
- Lung Congestion: {vitals_data.get('lung_congestion', 'Not assessed')}

Follow-up Questions Answered: {len(followup_data.get('organized_qa_pairs', []))} questions
"""

        # Create LLM prompt for ICD11 code generation
        prompt_template = load_prompt("icd11_generation")
        prompt = prompt_template.format(context=context)

        # Make API call to OpenAI
        print("🔗 Making OpenAI API call...")
        try:
            # Use the existing openai_client that was configured at startup
            response = openai_client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[
                    {"role": "system", "content": load_prompt("icd11_generation_system")},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            print("✅ OpenAI API call successful")
            
            # Process the successful response
            result_text = response.choices[0].message.content.strip()
            print(f"✅ LLM response received: {len(result_text)} characters")
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                
                # Validate the response structure
                if not result.get('success'):
                    print("❌ LLM returned success=false")
                    return None
                    
                icd_codes = result.get('icd_codes', [])
                if not icd_codes or len(icd_codes) < 5:
                    print(f"❌ Insufficient ICD codes returned: {len(icd_codes)}")
                    return None
                
                # Ensure we have 7-10 codes
                if len(icd_codes) > 10:
                    icd_codes = icd_codes[:10]
                
                print(f"✅ Generated {len(icd_codes)} ICD-11 codes")
                for code in icd_codes[:3]:  # Log first 3 codes
                    print(f"   📋 {code.get('code')}: {code.get('title')} (confidence: {code.get('confidence')}%)")
                
                return {
                    'success': True,
                    'icd_codes': icd_codes,
                    'analysis_notes': result.get('analysis_notes', '')
                }
                
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse LLM JSON response: {e}")
                print(f"Raw response first 500 chars: {result_text[:500]}...")
                return None
            
        except Exception as api_error:
            print(f"❌ OpenAI API error: {str(api_error)}")
            print("🔄 Using mock data for testing purposes...")
            
            # Return mock ICD codes for testing
            mock_icd_codes = [
                {
                    "code": "8A80.Z",
                    "title": "Acute respiratory infection, unspecified",
                    "description": "An acute infection involving the respiratory system where the specific organism and location are not identified. This matches the patient's fever and breathing difficulties.",
                    "confidence": 92
                },
                {
                    "code": "MG30.0Y",
                    "title": "Fever, unspecified",
                    "description": "Elevated body temperature without identification of the underlying cause. Patient presents with high fever (101°C).",
                    "confidence": 95
                },
                {
                    "code": "MD11.9",
                    "title": "Dyspnoea, unspecified",
                    "description": "Difficulty breathing or shortness of breath without further specification. Correlates with low oxygen saturation (80%).",
                    "confidence": 88
                },
                {
                    "code": "8A81.2",
                    "title": "Upper respiratory tract infection, unspecified",
                    "description": "Infection of the upper respiratory tract without specification of the causative organism.",
                    "confidence": 85
                },
                {
                    "code": "MG30.1",
                    "title": "Pyrexia of unknown origin",
                    "description": "Fever of unknown cause, often associated with systemic infections.",
                    "confidence": 78
                },
                {
                    "code": "MD12.0",
                    "title": "Tachypnoea",
                    "description": "Rapid breathing often associated with respiratory distress or fever.",
                    "confidence": 82
                },
                {
                    "code": "8A84.1",
                    "title": "Viral respiratory tract infection, unspecified",
                    "description": "Viral infection affecting the respiratory tract, commonly presenting with fever and breathing difficulties.",
                    "confidence": 75
                },
                {
                    "code": "MG31.2",
                    "title": "Chills",
                    "description": "Sudden feeling of cold with shivering, often accompanying fever during infections.",
                    "confidence": 90
                }
            ]
            
            return {
                'success': True,
                'icd_codes': mock_icd_codes,
                'analysis_notes': 'Based on the clinical presentation of high fever (101°C), low oxygen saturation (80%), and respiratory symptoms, the most likely diagnoses include acute respiratory infections and fever-related conditions. The patient would benefit from further diagnostic tests including chest X-ray, blood cultures, and complete blood count. (Note: This analysis uses mock data due to API connectivity issues.)'
            }
            
    except Exception as e:
        print(f"❌ Error in generate_icd11_codes_with_llm: {str(e)}")
        import traceback
        print("📄 LLM function traceback:")
        traceback.print_exc()
        return None

@app.route('/complete_assessment', methods=['POST'])
def complete_assessment():
    """Complete the assessment process"""
    try:
        print("✅ Completing assessment")
        
        data = request.get_json()
        step = data.get('step', 7)
        
        # Update final completion status
        completion_data = {
            'assessment_fully_completed': True,
            'completion_step': step,
            'final_completion_timestamp': datetime.now().isoformat(),
            'user_confirmed_completion': True
        }
        
        # Save final completion status
        success = save_step_based_patient_data(
            step_number=step,
            form_data={
                'assessment_fully_completed': True,
                'completion_confirmed': True
            },
            ai_data=completion_data,
            files_data={}
        )
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save completion status'})
        
        # Update session
        if 'patient_data' not in session:
            session['patient_data'] = {}
        session['patient_data']['assessment_fully_completed'] = True
        session['patient_data']['highest_step_completed'] = step
        session.modified = True
        
        print("✅ Assessment completed successfully")
        
        return jsonify({
            'success': True,
            'message': 'Assessment completed successfully',
            'data': {
                'completed_at': datetime.now().isoformat(),
                'final_step': step
            }
        })
        
    except Exception as e:
        print(f"❌ Error in complete_assessment: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to complete assessment: {str(e)}'})

@app.route('/generate_icd_diagnosis', methods=['POST'])
def generate_icd_diagnosis():
    """Generate comprehensive ICD disease codes using holistic analysis of steps 4, 5, and 6"""
    try:
        print("✅ ===== STARTING COMPREHENSIVE ICD DIAGNOSIS GENERATION =====")
        
        if not validate_session_step(6):
            return jsonify({'success': False, 'error': 'Please complete step 6 first'})
        
        # Collect data from all relevant steps with specified priorities
        step4_data = get_step_data(4)  # 10% priority (or 40% if no step4 questions)
        step5_data = get_step_data(5)  # 60% priority 
        step6_data = get_step_data(6)  # 30% priority (or 50% if no step4 questions)
        
        print(f"📊 Step 4 data available: {bool(step4_data)}")
        print(f"📊 Step 5 data available: {bool(step5_data)}")
        print(f"📊 Step 6 data available: {bool(step6_data)}")
        
        # Determine priority distribution based on step 4 availability
        step4_questions = []
        if step4_data:
            ai_data = step4_data.get('ai_data', {})
            step4_questions = ai_data.get('generated_questions', [])
        
        has_step4_questions = len(step4_questions) > 0
        
        if has_step4_questions:
            priorities = {'step5': 0.6, 'step6': 0.3, 'step4': 0.1}
            print("📈 Using priority distribution: Step5(60%) + Step6(30%) + Step4(10%)")
        else:
            priorities = {'step5': 0.6, 'step6': 0.4, 'step4': 0.0}
            print("📈 Using priority distribution: Step5(60%) + Step6(40%) + Step4(0%)")
        
        # Generate comprehensive ICD diagnosis
        diagnosis_result = generate_comprehensive_icd_diagnosis(
            step4_data, step5_data, step6_data, priorities
        )
        
        # Save diagnosis data to step 7
        success = save_step_based_patient_data(
            step_number=7,
            form_data={'diagnosis_generated': True},
            ai_data=diagnosis_result,
            files_data={}
        )
        
        if not success:
            print("⚠️ Failed to save diagnosis data, but returning result anyway")
        
        return jsonify({
            'success': True,
            'diagnosis': diagnosis_result
        })
        
    except Exception as e:
        print(f"❌ Error in generate_icd_diagnosis: {str(e)}")
        return jsonify({'success': False, 'error': f'Diagnosis generation failed: {str(e)}'})

def generate_comprehensive_icd_diagnosis(step4_data, step5_data, step6_data, priorities):
    """Generate ICD disease codes using holistic medical analysis"""
    try:
        print("🔬 Starting comprehensive medical analysis...")
        
        # Extract and prioritize data from each step
        clinical_context = build_clinical_context(step4_data, step5_data, step6_data, priorities)
        
        if not clinical_context['has_sufficient_data']:
            print("⚠️ Insufficient clinical data for diagnosis")
            return generate_fallback_icd_diagnosis({})
        
        # Generate AI-powered ICD diagnosis
        icd_diagnosis = generate_ai_icd_diagnosis(clinical_context)
        
        if icd_diagnosis:
            print(f"✅ Generated {len(icd_diagnosis.get('top_diagnoses', []))} ICD diagnoses")
            return icd_diagnosis
        else:
            print("🔄 AI diagnosis failed, using fallback")
            return generate_fallback_icd_diagnosis(clinical_context)
            
    except Exception as e:
        print(f"❌ Error in comprehensive diagnosis generation: {str(e)}")
        return generate_fallback_icd_diagnosis({})

def build_clinical_context(step4_data, step5_data, step6_data, priorities):
    """Build comprehensive clinical context with weighted priorities"""
    try:
        print("📋 Building clinical context...")
        
        context = {
            'has_sufficient_data': False,
            'primary_symptoms': {},
            'follow_up_responses': {},
            'step6_qa_responses': {},
            'ai_insights': {},
            'vital_signs': {},
            'abnormal_findings': [],
            'priorities': priorities,
            'data_sources': []
        }
        
        # Process Step 5 data (60% priority) - Primary symptoms and AI insights
        if step5_data:
            form_data = step5_data.get('form_data', {})
            ai_data = step5_data.get('ai_data', {})
            
            context['primary_symptoms'] = {
                'complaint_text': form_data.get('complaint_text', ''),
                'primary_complaint': form_data.get('primary_complaint', ''),
                'complaint_description': form_data.get('complaint_description', ''),
                'symptom_duration': form_data.get('symptom_duration', ''),
                'pain_level': form_data.get('pain_level', ''),
                'additional_symptoms': form_data.get('additional_symptoms', '')
            }
            
            # AI insights from step 5
            symptom_insights = ai_data.get('symptom_insights', {})
            if symptom_insights:
                context['ai_insights'] = {
                    'medical_labels': symptom_insights.get('medical_labels', []),
                    'confidence_scores': symptom_insights.get('confidence_scores', {}),
                    'insights_metadata': symptom_insights.get('metadata', {})
                }
            
            context['data_sources'].append('step5_symptoms')
            print(f"   ✅ Step 5: Primary symptoms and AI insights extracted")
        
        # Process Step 6 data (30%/40% priority) - Follow-up Q&A responses
        if step6_data:
            ai_data = step6_data.get('ai_data', {})
            
            # Get organized Q&A pairs
            qa_pairs = ai_data.get('organized_qa_pairs', [])
            if qa_pairs:
                context['step6_qa_responses'] = qa_pairs
                print(f"   ✅ Step 6: {len(qa_pairs)} follow-up Q&A responses extracted")
            
            context['data_sources'].append('step6_followup_qa')
        
        # Process Step 4 data (10% priority) - Initial follow-up questions
        if step4_data and priorities['step4'] > 0:
            form_data = step4_data.get('form_data', {})
            ai_data = step4_data.get('ai_data', {})
            
            # Extract follow-up question responses
            followup_responses = {}
            for key, value in form_data.items():
                if key.startswith('followup_answer_'):
                    question_id = key.replace('followup_answer_', '')
                    followup_responses[question_id] = value
            
            if followup_responses:
                context['follow_up_responses'] = followup_responses
                print(f"   ✅ Step 4: {len(followup_responses)} initial follow-up responses extracted")
            
            context['data_sources'].append('step4_initial_followup')
        
        # Get vital signs from step 3 for context
        step3_data = get_step_data(3)
        if step3_data:
            form_data = step3_data.get('form_data', {})
            ai_data = step3_data.get('ai_data', {})
            
            context['vital_signs'] = form_data
            context['abnormal_findings'] = ai_data.get('abnormal_findings', [])
            context['data_sources'].append('step3_vitals')
            print(f"   ✅ Step 3: Vital signs and {len(context['abnormal_findings'])} abnormal findings")
        
        # Determine if we have sufficient data for diagnosis
        has_symptoms = bool(context['primary_symptoms'].get('complaint_text') or 
                           context['primary_symptoms'].get('primary_complaint'))
        has_followup = bool(context['step6_qa_responses'] or context['follow_up_responses'])
        has_ai_insights = bool(context['ai_insights'].get('medical_labels'))
        
        context['has_sufficient_data'] = has_symptoms and (has_followup or has_ai_insights)
        
        print(f"📊 Clinical context summary:")
        print(f"   🎯 Data sources: {', '.join(context['data_sources'])}")
        print(f"   📝 Has symptoms: {has_symptoms}")
        print(f"   🔍 Has follow-up data: {has_followup}")
        print(f"   🤖 Has AI insights: {has_ai_insights}")
        print(f"   ✅ Sufficient for diagnosis: {context['has_sufficient_data']}")
        
        return context
        
    except Exception as e:
        print(f"❌ Error building clinical context: {str(e)}")
        return {'has_sufficient_data': False}

def generate_ai_icd_diagnosis(clinical_context):
    """Generate ICD disease codes using AI with comprehensive clinical context"""
    try:
        print("🤖 Generating AI-powered ICD diagnosis...")
        
        # Build comprehensive prompt for AI diagnosis
        prompt = build_icd_diagnosis_prompt(clinical_context)
        
        if not prompt:
            print("❌ Failed to build diagnosis prompt")
            return None
        
        print(f"📝 Prompt length: {len(prompt)} characters")
        
        # Call OpenAI API for diagnosis
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": load_prompt("icd10_diagnosis_system")
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.3,  # Lower temperature for more accurate medical diagnosis
            max_tokens=2500
        )
        
        ai_response = response.choices[0].message.content.strip()
        print(f"🤖 AI Response received: {len(ai_response)} characters")
        
        # Parse AI response
        try:
            # Extract JSON from response
            json_start = ai_response.find('{')
            json_end = ai_response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_content = ai_response[json_start:json_end]
                diagnosis_result = json.loads(json_content)
                
                # Validate diagnosis structure
                if validate_diagnosis_result(diagnosis_result):
                    print("✅ AI diagnosis generated and validated successfully")
                    return diagnosis_result
                else:
                    print("❌ AI diagnosis failed validation")
                    return None
                    
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {str(e)}")
            print(f"Raw AI response: {ai_response[:300]}...")
            return None
            
    except Exception as e:
        print(f"❌ Error in AI diagnosis generation: {str(e)}")
        return None

def build_icd_diagnosis_prompt(clinical_context):
    """Build comprehensive prompt for AI ICD diagnosis generation"""
    try:
        print("📝 Building ICD diagnosis prompt...")
        
        priorities = clinical_context['priorities']
        data_sources = clinical_context['data_sources']
        
        # Build content for template replacement
        symptoms_data = ""
        symptoms = clinical_context.get('primary_symptoms', {})
        if symptoms:
            symptoms_data = f"""

Chief Complaint: {symptoms.get('complaint_text', 'Not specified')}
Primary Complaint: {symptoms.get('primary_complaint', 'Not specified')}
Detailed Description: {symptoms.get('complaint_description', 'Not specified')}
Duration: {symptoms.get('symptom_duration', 'Not specified')}
Pain Level: {symptoms.get('pain_level', 'Not specified')}
Additional Symptoms: {symptoms.get('additional_symptoms', 'Not specified')}"""
        
        # Add AI insights if available
        ai_insights = ""
        ai_insight_data = clinical_context.get('ai_insights', {})
        if ai_insight_data.get('medical_labels'):
            ai_insights = f"""

AI-IDENTIFIED MEDICAL LABELS:
{', '.join(ai_insight_data['medical_labels'])}

CONFIDENCE SCORES:
{ai_insight_data.get('confidence_scores', {})}"""
        
        # Add Step 6 follow-up Q&A data
        step6_qa_data = ""
        step6_qa = clinical_context.get('step6_qa_responses', [])
        if step6_qa and priorities['step6'] > 0:
            step6_qa_data = f"""

PERSONALIZED FOLLOW-UP RESPONSES (PRIORITY - {priorities['step6']*100:.0f}%):"""
            
            for qa_pair in step6_qa[:10]:  # Limit to avoid token overflow
                question = qa_pair.get('question', '')
                answer = qa_pair.get('answer', '')
                category = qa_pair.get('category', 'general')
                
                if question and answer:
                    step6_qa_data += f"""
[{category.upper()}] Q: {question}
A: {answer}"""
        
        # Add Step 4 initial follow-up data
        step4_followup_data = ""
        step4_responses = clinical_context.get('follow_up_responses', {})
        if step4_responses and priorities['step4'] > 0:
            step4_followup_data = f"""

INITIAL FOLLOW-UP RESPONSES (PRIORITY - {priorities['step4']*100:.0f}%):"""
            
            for question_id, answer in list(step4_responses.items())[:5]:  # Limit responses
                step4_followup_data += f"""
Response {question_id}: {answer}"""
        
        # Add vital signs context
        vital_signs = ""
        vital_signs_data = clinical_context.get('vital_signs', {})
        abnormal_findings = clinical_context.get('abnormal_findings', [])
        
        if vital_signs_data or abnormal_findings:
            vital_signs = f"""

VITAL SIGNS & CLINICAL FINDINGS (CONTEXT):"""
            
            if vital_signs_data:
                height_feet = vital_signs_data.get('height_feet', '')
                height_inches = vital_signs_data.get('height_inches', '')
                vital_signs += f"""
Age: {vital_signs_data.get('age', 'Not specified')}
Gender: {vital_signs_data.get('gender', 'Not specified')}
Blood Pressure: {vital_signs_data.get('systolic_bp', '')}/{vital_signs_data.get('diastolic_bp', '')} mmHg
Heart Rate: {vital_signs_data.get('heart_rate', '')} bpm
Temperature: {vital_signs_data.get('temperature', '')}°F
Respiratory Rate: {vital_signs_data.get('respiratory_rate', '')} breaths/min
Weight: {vital_signs_data.get('weight', '')} lbs
Height: {height_feet}'{height_inches}"
BMI: {vital_signs_data.get('bmi', '')}"""
            
            if abnormal_findings:
                vital_signs += f"""

ABNORMAL FINDINGS IDENTIFIED:
{', '.join(abnormal_findings)}"""
        
        # Patient demographics
        patient_demographics = clinical_context.get('patient_demographics', '')
        
        # Load and format the comprehensive diagnosis prompt
        prompt_template = load_prompt("comprehensive_diagnosis")
        prompt = prompt_template.format(
            step5_priority=priorities['step5']*100,
            step6_priority=priorities['step6']*100,
            step4_priority=priorities['step4']*100,
            data_sources=', '.join(data_sources),
            symptoms_data=symptoms_data,
            ai_insights=ai_insights,
            step6_qa_data=step6_qa_data,
            step4_followup_data=step4_followup_data,
            vital_signs=vital_signs,
            patient_demographics=patient_demographics
        )
        
        print(f"✅ Diagnosis prompt built successfully ({len(prompt)} characters)")
        return prompt
        
    except Exception as e:
        print(f"❌ Error building diagnosis prompt: {str(e)}")
        return None

def validate_diagnosis_result(diagnosis_result):
    """Validate the structure and content of AI diagnosis result"""
    try:
        if not isinstance(diagnosis_result, dict):
            return False
        
        # Check required fields
        required_fields = ['top_diagnoses', 'clinical_summary']
        for field in required_fields:
            if field not in diagnosis_result:
                print(f"❌ Missing required field: {field}")
                return False
        
        # Validate top_diagnoses structure
        top_diagnoses = diagnosis_result.get('top_diagnoses', [])
        if not isinstance(top_diagnoses, list) or len(top_diagnoses) == 0:
            print("❌ top_diagnoses must be a non-empty list")
            return False
        
        # Validate each diagnosis
        for i, diagnosis in enumerate(top_diagnoses):
            if not isinstance(diagnosis, dict):
                print(f"❌ Diagnosis {i} must be a dictionary")
                return False
            
            required_diagnosis_fields = ['icd_code', 'disease_name', 'confidence_percentage']
            for field in required_diagnosis_fields:
                if field not in diagnosis:
                    print(f"❌ Diagnosis {i} missing field: {field}")
                    return False
            
            # Validate ICD code format (basic check)
            icd_code = diagnosis.get('icd_code', '')
            if not icd_code or len(icd_code) < 3:
                print(f"❌ Invalid ICD code format: {icd_code}")
                return False
            
            # Validate confidence percentage
            confidence = diagnosis.get('confidence_percentage')
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 100:
                print(f"❌ Invalid confidence percentage: {confidence}")
                return False
        
        print("✅ Diagnosis result validation passed")
        return True
        
    except Exception as e:
        print(f"❌ Error validating diagnosis result: {str(e)}")
        return False

def get_step6_qa_data():
    """Retrieve organized Q&A data from step 6 for use in step 7"""
    try:
        step6_data = get_step_data(6)
        if not step6_data:
            return {}
        
        ai_data = step6_data.get('ai_data', {})
        
        # Extract organized Q&A pairs
        qa_pairs = ai_data.get('organized_qa_pairs', [])
        question_responses = ai_data.get('question_responses', {})
        original_questions = ai_data.get('original_questions', [])
        
        return {
            'qa_pairs': qa_pairs,
            'total_questions_generated': ai_data.get('total_questions_generated', 0),
            'total_questions_answered': ai_data.get('total_questions_answered', 0),
            'completion_rate': ai_data.get('completion_rate', 0),
            'completed_at': ai_data.get('completed_at', ''),
            'raw_responses': question_responses,
            'raw_questions': original_questions,
            'session_metadata': ai_data.get('session_data', {})
        }
    except Exception as e:
        print(f"❌ Error retrieving step 6 Q&A data: {str(e)}")
        return {}

# Step 7 routes removed - now ending at step 6 with clinical summary

def generate_clinical_summary():
    """Generate a clinical summary using LLM based on steps 4, 5, and 6 data"""
    try:
        print("🏥 GENERATING CLINICAL SUMMARY...")
        
        # Get patient data from all steps
        patient_data = load_patient_data()
        print(f"📊 Loaded patient data: {list(patient_data.keys()) if patient_data else 'None'}")
        
        if not patient_data:
            print("❌ No patient data found for clinical summary")
            return {"error": "No patient data found"}
        
        # Extract relevant data from steps (note: demographics in step2, vitals in step3)
        step1_data = patient_data.get('step1', {})
        step2_data = patient_data.get('step2', {})  # Demographics
        step3_data = patient_data.get('step3', {})  # Vital signs
        step4_data = patient_data.get('step4', {})
        step5_data = patient_data.get('step5', {})
        step6_data = patient_data.get('step6', {})
        
        print(f"📋 Step data found: Step1={bool(step1_data)}, Step2={bool(step2_data)}, Step3={bool(step3_data)}, Step4={bool(step4_data)}, Step5={bool(step5_data)}, Step6={bool(step6_data)}")
        
        # Build comprehensive clinical context
        clinical_context = []
        
        # Patient Demographics (Step 2)
        step2_form = step2_data.get('form_data', {})
        if step2_form:
            demographics = []
            if 'full_name' in step2_form:
                demographics.append(f"Name: {step2_form['full_name']}")
            if 'calculated_age' in step2_form:
                demographics.append(f"Age: {step2_form['calculated_age']} years")
            if 'gender' in step2_form:
                demographics.append(f"Gender: {step2_form['gender']}")
            if 'occupation' in step2_form:
                demographics.append(f"Occupation: {step2_form['occupation']}")
            if 'marital_status' in step2_form:
                demographics.append(f"Marital Status: {step2_form['marital_status']}")
            
            # Medical history
            medical_history = []
            if step2_form.get('diabetes') == 'yes':
                medical_history.append("Diabetes")
            if step2_form.get('hypertension') == 'yes':
                medical_history.append("Hypertension")
            if step2_form.get('asthma') == 'yes':
                medical_history.append("Asthma")
            if step2_form.get('heart_disease') == 'yes':
                medical_history.append("Heart Disease")
            if medical_history:
                demographics.append(f"Medical History: {', '.join(medical_history)}")
                
            if demographics:
                clinical_context.append("PATIENT DEMOGRAPHICS:\n" + "\n".join(demographics))
        
        # Vital Signs & Measurements (Step 3)
        step3_form = step3_data.get('form_data', {})
        if step3_form:
            vitals = []
            if 'pulse_rate' in step3_form:
                vitals.append(f"Pulse Rate: {step3_form['pulse_rate']} bpm")
            if 'systolic_bp' in step3_form and 'diastolic_bp' in step3_form:
                vitals.append(f"Blood Pressure: {step3_form['systolic_bp']}/{step3_form['diastolic_bp']} mmHg")
            if 'respiratory_rate' in step3_form:
                vitals.append(f"Respiratory Rate: {step3_form['respiratory_rate']} breaths/min")
            if 'temperature' in step3_form:
                temp_unit = step3_form.get('temperature_unit', 'fahrenheit')
                vitals.append(f"Temperature: {step3_form['temperature']}°{temp_unit[0].upper()}")
            if 'oxygen_saturation' in step3_form:
                vitals.append(f"Oxygen Saturation: {step3_form['oxygen_saturation']}%")
            if 'blood_glucose' in step3_form:
                glucose_timing = step3_form.get('glucose_timing', 'random')
                vitals.append(f"Blood Glucose ({glucose_timing}): {step3_form['blood_glucose']} mg/dL")
            if 'bmi' in step3_form:
                vitals.append(f"BMI: {step3_form['bmi']} kg/m²")
            if 'lung_congestion' in step3_form:
                vitals.append(f"Lung Congestion: {step3_form['lung_congestion']}")
            
            if vitals:
                clinical_context.append("VITAL SIGNS & CLINICAL FINDINGS:\n" + "\n".join(vitals))
        
        # Symptoms & Complaints (Step 5)
        step5_form = step5_data.get('form_data', {})
        step5_ai = step5_data.get('ai_generated_data', {})
        if step5_form or step5_ai:
            symptoms = []
            
            # Chief complaint
            if 'complaint_text' in step5_form:
                symptoms.append(f"Chief Complaint: {step5_form['complaint_text']}")
            
            # Symptom insights from AI analysis
            if 'symptom_insights' in step5_ai:
                symptom_insights = step5_ai['symptom_insights']
                if isinstance(symptom_insights, dict) and 'medical_labels' in symptom_insights:
                    labels = symptom_insights['medical_labels']
                    condition_details = []
                    for label in labels:
                        if isinstance(label, dict):
                            name = label.get('label', '')
                            severity = label.get('severity', '')
                            description = label.get('description', '')
                            if name:
                                condition_details.append(f"- {name} ({severity}): {description}")
                    if condition_details:
                        symptoms.append("Symptom Analysis:\n" + "\n".join(condition_details))
            
            # Abnormal findings from AI analysis
            if 'abnormal_findings' in step5_ai:
                findings = step5_ai['abnormal_findings']
                if findings:
                    findings_list = []
                    for finding in findings:
                        if isinstance(finding, dict):
                            finding_text = finding.get('finding', '')
                            concern = finding.get('concern', '')
                            priority = finding.get('priority', '')
                            if finding_text:
                                findings_list.append(f"- {finding_text} (Concern: {concern}, Priority: {priority})")
                    if findings_list:
                        symptoms.append("Clinical Findings:\n" + "\n".join(findings_list))
            
            if symptoms:
                clinical_context.append("PRESENTING SYMPTOMS & CLINICAL FINDINGS:\n" + "\n".join(symptoms))
        
        # Medical Documents (Step 5 Section 2)
        step5_medical_docs = step5_ai.get('medical_documents', [])
        if step5_medical_docs:
            doc_highlights = []
            for doc in step5_medical_docs:
                if doc.get('insights'):
                    filename = doc.get('filename', 'Unknown')
                    category = doc.get('categoryLabel', doc.get('category', 'Unknown'))
                    insights = doc.get('insights', {})
                    
                    # Extract key highlight (1-2 liner summary)
                    highlight_parts = []
                    if isinstance(insights, dict):
                        # Try to get the most important findings first
                        if insights.get('medical_condition_detected'):
                            highlight_parts.append(insights['medical_condition_detected'])
                        elif insights.get('key_findings'):
                            highlight_parts.append(insights['key_findings'])
                        elif insights.get('general_findings'):
                            highlight_parts.append(insights['general_findings'])
                        
                        # Add concerns if any
                        if insights.get('concerns') and isinstance(insights['concerns'], list) and insights['concerns']:
                            main_concern = insights['concerns'][0] if insights['concerns'] else ''
                            if main_concern and len(highlight_parts) < 2:
                                highlight_parts.append(f"Concern: {main_concern}")
                    else:
                        # Handle string insights
                        highlight_parts.append(str(insights)[:100] + "..." if len(str(insights)) > 100 else str(insights))
                    
                    if highlight_parts:
                        highlight = ". ".join(highlight_parts[:2])  # Max 2 parts for 1-2 liner
                        doc_highlights.append(f"- {filename} ({category}): {highlight}")
            
            if doc_highlights:
                clinical_context.append("UPLOADED MEDICAL DOCUMENTS:\n" + "\n".join(doc_highlights))
        
        # Detailed Assessment (Step 6)
        step6_ai = step6_data.get('ai_generated_data', {})
        if step6_ai and 'organized_qa_pairs' in step6_ai:
            responses = []
            qa_pairs = step6_ai['organized_qa_pairs']
            for qa_pair in qa_pairs:
                if isinstance(qa_pair, dict):
                    question = qa_pair.get('question_text', '')
                    answer = qa_pair.get('answer', '')
                    category = qa_pair.get('question_category', '')
                    if question and answer:
                        responses.append(f"Q ({category}): {question}")
                        responses.append(f"A: {answer}")
                        responses.append("")  # Empty line for readability
            
            if responses:
                clinical_context.append("DETAILED SYMPTOM ASSESSMENT:\n" + "\n".join(responses[:-1]))  # Remove last empty line
        
        if not clinical_context:
            return {"error": "Insufficient data for clinical summary"}
        
        full_context = "\n\n".join(clinical_context)
        
        # Create prompt for LLM to generate clinical summary
        prompt_template = load_prompt("clinical_summary")
        prompt = prompt_template.format(full_context=full_context)

        print("🤖 Sending clinical summary request to GPT-4o...")
        
        # Use GPT-4o for generating clinical summary
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "system",
                    "content": load_prompt("clinical_summary_system")
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.3,  # Lower temperature for more consistent medical documentation
            max_tokens=2000
        )
        
        clinical_summary = response.choices[0].message.content.strip()
        print(f"✅ Clinical summary generated: {len(clinical_summary)} characters")
        
        return {
            "success": True,
            "clinical_summary": clinical_summary,
            "data_sources": f"Steps 1, 4, 5, and 6 data compiled"
        }
        
    except Exception as e:
        print(f"❌ Error generating clinical summary: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to generate clinical summary: {str(e)}"}

@app.route('/generate_summary', methods=['POST'])
def generate_summary():
    """API endpoint to generate clinical summary"""
    try:
        summary_result = generate_clinical_summary()
        if "error" in summary_result:
            return jsonify({'success': False, 'error': summary_result['error']})
        
        return jsonify({
            'success': True,
            'summary': summary_result['clinical_summary'],
            'data_sources': summary_result['data_sources']
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Summary generation failed: {str(e)}'})
# Report generation
@app.route('/report')
def report():
    """Generate comprehensive patient report - SHOULD NOT BE USED NOW as we replaced with popup"""
    try:
        all_data = get_all_patient_data()
        print(f"DEBUG: /report route accessed. Data found: {'Yes' if all_data else 'No'}")
        
        if not all_data or 'steps' not in all_data:
            print("DEBUG: No patient data or no steps found, redirecting to home")
            return redirect('/')
        
        print("DEBUG: Report route accessed but we now use popup instead")
        return redirect('/')
    except Exception as e:
        print(f"❌ Error in /report route: {str(e)}")
        return redirect('/')
        return redirect('/')

@app.route('/get_complete_patient_report', methods=['GET'])
def get_complete_patient_report():
    """Get complete patient data for report generation"""
    try:
        all_data = get_all_patient_data()
        if not all_data:
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        # Organize data for easy report generation
        report_data = {
            'session_info': all_data.get('session_info', {}),
            'completion_status': all_data.get('completion_status', {}),
            'case_category': {},
            'patient_registration': {},
            'vital_signs': {},
            'medical_records': {},
            'complaints': {},
            'analysis': {},
            'diagnosis': {}
        }
        
        steps = all_data.get('steps', {})
        
        # Extract organized data for each section
        if 'step1' in steps:
            report_data['case_category'] = steps['step1']
        if 'step2' in steps:
            report_data['patient_registration'] = steps['step2']
        if 'step3' in steps:
            report_data['vital_signs'] = steps['step3']
        if 'step4' in steps:
            report_data['medical_records'] = steps['step4']
        if 'step5' in steps:
            report_data['complaints'] = steps['step5']
        if 'step6' in steps:
            report_data['analysis'] = steps['step6']
        # Step7 removed - clinical summary generated via LLM
        
        return jsonify({
            'success': True,
            'report_data': report_data,
            'total_steps_completed': len([k for k in steps.keys() if steps[k].get('step_completed', False)])
        })
        
    except Exception as e:
        print(f"❌ Error generating complete report: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to generate report: {str(e)}'})

@app.route('/get_patient_data', methods=['GET'])
def get_patient_data():
    """Get patient data from previous steps in clean format"""
    try:
        all_data = get_all_patient_data()
        if not all_data or 'steps' not in all_data:
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        # Extract clean data from step-based structure
        cleaned_data = {
            'step1': {},
            'step2': {},
            'step3': {},
            'step4': {},
            'session_info': all_data.get('session_info', {}),
            'completion_status': all_data.get('completion_status', {})
        }
        
        # Extract data from each step
        for step_num in range(1, 5):
            step_key = f'step{step_num}'
            if step_key in all_data['steps']:
                step_data = all_data['steps'][step_key]
                cleaned_data[step_key] = {
                    'form_data': step_data.get('form_data', {}),
                    'ai_data': step_data.get('ai_generated_data', {}),
                    'files': step_data.get('files_uploaded', {}),
                    'timestamp': step_data.get('timestamp', ''),
                    'completed': step_data.get('step_completed', False)
                }
        
        # Legacy format for backward compatibility
        legacy_format = {
            'registration': cleaned_data['step2']['form_data'],
            'vitals': cleaned_data['step3']['form_data'],
            'step4_data': cleaned_data['step4']['form_data']
        }
        
        print(f"✅ Patient data retrieved successfully")
        print(f"📊 Steps with data: {[k for k, v in cleaned_data.items() if k.startswith('step') and v.get('form_data')]}")
        
        return jsonify({
            'success': True,
            'step_based_data': cleaned_data,
            'legacy_data': legacy_format,
            'registration': legacy_format['registration'],
            'vitals': legacy_format['vitals'],
            'step4_data': legacy_format['step4_data']
        })
        
    except Exception as e:
        print(f"❌ Error getting patient data: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to get patient data: {str(e)}'})

@app.route('/analyze_complaints', methods=['POST'])
def analyze_complaints():
    """Generate targeted follow-up questions based on step5 data using specific medical categories"""
    try:
        print("✅ ===== STARTING STEP 6 TARGETED QUESTIONS ANALYSIS =====")
        
        # Get patient data
        all_data = get_all_patient_data()
        if not all_data:
            print("❌ ERROR - No patient data found")
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        # Extract step5 data only (as requested)
        step5_data = get_step_data(5)
        if not step5_data:
            print("❌ ERROR - No step5 data found")
            return jsonify({'success': False, 'error': 'Please complete step 5 first'})
        
        print(f"📊 Step 5 data available: {bool(step5_data)}")
        
        # Extract step5 components
        form_data = step5_data.get('form_data', {})
        ai_data = step5_data.get('ai_generated_data', {})
        
        # Extract medical documents from step5 section 2 - CHECK BOTH LOCATIONS
        medical_documents = ai_data.get('medical_documents', [])  # Primary location
        if not medical_documents:
            medical_documents = form_data.get('medical_documents', [])  # Fallback location
        print(f"📄 Medical documents found: {len(medical_documents)}")
        for doc in medical_documents:
            print(f"   📋 {doc.get('filename', 'Unknown')} - {doc.get('category', 'Unknown')} - Insights: {bool(doc.get('insights'))}")
        
        # Prepare step5 context
        step5_context = {
            'complaint_text': form_data.get('complaint_text', ''),
            'primary_complaint': form_data.get('primary_complaint', ''),
            'symptom_duration': form_data.get('symptom_duration', ''),
            'pain_level': form_data.get('pain_level', ''),
            'additional_symptoms': form_data.get('additional_symptoms', ''),
            'abnormal_findings': ai_data.get('abnormal_findings', []),
            'symptom_insights': ai_data.get('symptom_insights', {}),
            'followup_answers': ai_data.get('followup_answers', {}),
            'medical_documents': medical_documents  # NEW: Include medical document insights
        }
        
        print(f"📝 Complaint text available: {bool(step5_context['complaint_text'])}")
        print(f"🚨 Abnormal findings: {len(step5_context['abnormal_findings'])}")
        print(f"🧠 AI insights available: {bool(step5_context['symptom_insights'])}")
        print(f"📄 Medical documents with insights: {len([doc for doc in medical_documents if doc.get('insights')])}")
        
        # Generate targeted questions based on step5 data
        questions = generate_targeted_step5_questions(step5_context)
        
        return jsonify({
            'success': True,
            'analysis': {
                'correlated_questions': questions,
                'source_data': 'step5_only',
                'total_questions': len(questions)
            }
        })
        
    except Exception as e:
        print(f"❌ Error in analyze_complaints: {str(e)}")
        return jsonify({'success': False, 'error': f'Analysis failed: {str(e)}'})

# Removed get_patient_friendly_term() function - now using LLM for medical term translation

def generate_targeted_step5_questions(step5_context):
    """Use LLM to generate 5th-grade level questions about medical conditions"""
    try:
        print("🎯 USING LLM TO GENERATE 5TH-GRADE LEVEL QUESTIONS...")
        
        # Extract data from step5
        complaint_text = step5_context.get('complaint_text', '')
        abnormal_findings = step5_context.get('abnormal_findings', [])
        symptom_insights = step5_context.get('symptom_insights', {})
        medical_documents = step5_context.get('medical_documents', [])  # NEW: Extract medical documents
        
        print(f"📊 STEP5 DATA INVENTORY:")
        print(f"   📝 Complaint text: '{complaint_text}'")
        print(f"   🚨 Abnormal findings: {len(abnormal_findings)}")
        print(f"   🧠 Symptom insights available: {bool(symptom_insights)}")
        print(f"   📄 Medical documents: {len(medical_documents)}")
        
        # Extract medical labels
        medical_labels = []
        if symptom_insights and 'medical_labels' in symptom_insights:
            medical_labels = symptom_insights['medical_labels']
            print(f"🏷️ MEDICAL LABELS FOUND: {[label.get('label', '') for label in medical_labels if isinstance(label, dict)]}")
        
        # Extract critical highlights from medical documents
        medical_document_insights = []
        for doc in medical_documents:
            if doc.get('insights'):
                insights = doc.get('insights', {})
                doc_info = {
                    'filename': doc.get('filename', 'Unknown'),
                    'category': doc.get('category_label', doc.get('category', 'Unknown')),
                    'insights': insights
                }
                medical_document_insights.append(doc_info)
        
        print(f"📄 MEDICAL DOCUMENT INSIGHTS: {len(medical_document_insights)} documents with AI analysis")
        for doc in medical_document_insights:
            print(f"   📋 {doc['filename']} ({doc['category']}): {len(str(doc['insights']))} chars of insights")
        
        # If no medical conditions found, use fallback
        if not medical_labels and not complaint_text.strip() and not medical_document_insights:
            print("⚠️ No specific medical conditions found, using fallback")
            return generate_fallback_targeted_questions()
        
        # Build comprehensive context for LLM
        context_parts = []
        
        if complaint_text:
            context_parts.append(f"PATIENT SAID: '{complaint_text}'")
        
        if medical_labels:
            labels_text = []
            for label in medical_labels:
                if isinstance(label, dict):
                    name = label.get('label', '')
                    severity = label.get('severity', 'mild')
                    description = label.get('description', '')
                    if name:
                        labels_text.append(f"- {name} ({severity}): {description}")
            if labels_text:
                context_parts.append("MEDICAL CONDITIONS IDENTIFIED:\n" + "\n".join(labels_text))
        
        if abnormal_findings:
            findings_text = []
            for finding in abnormal_findings[:3]:  # Limit to top 3
                if isinstance(finding, dict):
                    finding_desc = finding.get('finding', '') or finding.get('concern', '')
                    if finding_desc:
                        findings_text.append(f"- {finding_desc}")
            if findings_text:
                context_parts.append("ABNORMAL TEST RESULTS:\n" + "\n".join(findings_text))
        
        # Include medical document insights
        if medical_document_insights:
            docs_text = []
            for doc in medical_document_insights:
                doc_header = f"Document: {doc['filename']} ({doc['category']})"
                insights = doc['insights']
                
                if isinstance(insights, dict):
                    # Extract key findings from insights
                    findings = []
                    if insights.get('key_findings'):
                        findings.append(f"Key findings: {insights['key_findings']}")
                    if insights.get('concerns'):
                        findings.append(f"Medical concerns: {insights['concerns']}")
                    if insights.get('recommendations'):
                        findings.append(f"Recommendations: {insights['recommendations']}")
                    if insights.get('medical_condition_detected'):
                        findings.append(f"Detected condition: {insights['medical_condition_detected']}")
                    if insights.get('abnormal_values'):
                        findings.append(f"Abnormal values: {insights['abnormal_values']}")
                    
                    if findings:
                        docs_text.append(f"- {doc_header}")
                        for finding in findings:
                            docs_text.append(f"  {finding}")
                else:
                    # Handle string insights
                    clean_insights = str(insights)[:300].replace('\n', ' ')
                    docs_text.append(f"- {doc_header}: {clean_insights}...")
            
            if docs_text:
                context_parts.append("MEDICAL DOCUMENTS UPLOADED:\n" + "\n".join(docs_text))
        
        if not context_parts:
            print("⚠️ No meaningful step5 context found")
            return generate_fallback_targeted_questions()
        
        full_context = "\n\n".join(context_parts)
        
        # Calculate target number of questions based on medical conditions and documents
        num_medical_conditions = len([label for label in medical_labels if isinstance(label, dict) and label.get('label')])
        num_document_conditions = len(medical_document_insights)  # Each document may reveal conditions
        
        total_medical_info = num_medical_conditions + num_document_conditions
        
        if total_medical_info >= 4:
            target_questions = 12  # Maximum questions for 4+ conditions/documents
        elif total_medical_info >= 2:
            target_questions = 10  # 10 questions for 2-3 conditions/documents
        else:
            target_questions = 8   # 8 questions for 1 condition/document or general symptoms
            
        print(f"🎯 TARGET: {target_questions} questions for {num_medical_conditions} conditions + {num_document_conditions} documents ({total_medical_info} total)")
        
        # Create prompt for LLM - acting as medical expert who understands what patients actually experience
        prompt_template = load_prompt("dynamic_questions")
        prompt = prompt_template.format(
            full_context=full_context,
            target_questions=target_questions,
            num_medical_conditions=num_medical_conditions
        )

        print(f"🤖 Sending medically-expert prompt to GPT-4o...")
        print(f"📝 Context length: {len(full_context)} characters")
        
        # Use GPT-4o for generating simple, understandable questions
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "system",
                    "content": load_prompt("dynamic_questions_system")
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.7,  # Slightly higher for more natural, friendly language
            max_tokens=3000
        )
        
        ai_response = response.choices[0].message.content.strip()
        print(f"🤖 GPT-4o response received: {len(ai_response)} characters")
        
        # Parse GPT-4o response
        try:
            # Extract JSON from response
            json_start = ai_response.find('[')
            json_end = ai_response.rfind(']') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_content = ai_response[json_start:json_end]
                questions = json.loads(json_content)
                
                # Validate and clean questions
                valid_questions = []
                for q in questions:
                    if isinstance(q, dict) and 'question' in q and 'options' in q:
                        # Ensure question is practical and understandable
                        question_text = q['question']
                        if len(question_text.split()) <= 20:  # Reasonable length
                            valid_questions.append(q)
                
                print(f"✅ Generated {len(valid_questions)} MEDICALLY-EXPERT questions:")
                for i, q in enumerate(valid_questions, 1):
                    print(f"   {i}. {q['question']}")
                
                # Check if we have enough questions based on our target
                min_questions = max(6, target_questions - 2)  # At least 6, but allow 2 less than target
                if len(valid_questions) >= min_questions:
                    return valid_questions[:target_questions]  # Return exactly target number
                else:
                    print(f"⚠️ Only {len(valid_questions)} questions generated (target: {target_questions}), adding practical fallbacks...")
                    # Add practical fallback questions to reach target
                    practical_fallbacks = generate_simple_fallback_questions()
                    combined = valid_questions + practical_fallbacks[:(target_questions-len(valid_questions))]
                    return combined[:target_questions]
                
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {str(e)}")
            print(f"Raw response sample: {ai_response[:300]}...")
        
        except Exception as e:
            print(f"❌ Error processing GPT-4o response: {str(e)}")
        
        # Fallback if LLM fails
        print(f"🔄 LLM failed, using {target_questions} practical fallback questions...")
        fallback_questions = generate_simple_fallback_questions()
        return fallback_questions[:target_questions]
        
    except Exception as e:
        print(f"❌ Error in LLM question generation: {str(e)}")
        import traceback
        traceback.print_exc()
        # Fallback with target number of questions
        fallback_questions = generate_simple_fallback_questions()
        return fallback_questions[:target_questions if 'target_questions' in locals() else 8]

def generate_simple_fallback_questions():
    """Generate practical fallback questions about common symptoms"""
    return [
        {
            "question": "When did you first notice you weren't feeling well?",
            "category": "onset",
            "type": "multiple_choice",
            "options": ["Less than an hour ago", "A few hours ago", "Yesterday", "A few days ago", "About a week ago", "More than a week ago"],
            "relevance": "Timing of symptom onset"
        },
        {
            "question": "Have you been feeling unusually tired or weak?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["No, normal energy", "A little more tired", "Pretty tired", "Very tired", "Extremely exhausted", "Energy comes and goes"],
            "relevance": "Fatigue levels and energy"
        },
        {
            "question": "Have you noticed any changes in your breathing?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["Breathing is normal", "Slightly short of breath", "Moderate breathing difficulty", "Hard to catch my breath", "Very hard to breathe", "Breathing problems come and go"],
            "relevance": "Respiratory symptoms"
        },
        {
            "question": "Have you been sweating more than usual or feeling hot?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["No changes", "Slightly more sweating", "Sweating quite a bit", "Sweating a lot", "Constant sweating", "Sweating comes in waves"],
            "relevance": "Temperature regulation and fever symptoms"
        },
        {
            "question": "How often do you feel these symptoms?",
            "category": "frequency",
            "type": "multiple_choice",
            "options": ["All the time", "Most of the day", "Several times a day", "Once a day", "Few times a week", "It's unpredictable"],
            "relevance": "Frequency and pattern of symptoms"
        },
        {
            "question": "What makes you feel worse?",
            "category": "aggravating",
            "type": "multiple_choice",
            "options": ["Physical activity", "Standing up", "Lying down", "Eating", "Heat or cold", "Nothing makes it worse"],
            "relevance": "Aggravating factors"
        },
        {
            "question": "What helps you feel better?",
            "category": "relieving",
            "type": "multiple_choice",
            "options": ["Resting", "Drinking fluids", "Fresh air", "Medication", "Nothing helps yet", "Haven't tried anything"],
            "relevance": "Relieving factors"
        },
        {
            "question": "How much are these symptoms affecting your daily activities?",
            "category": "severity",
            "type": "multiple_choice",
            "options": ["Not affecting me", "Slightly bothersome", "Somewhat limiting", "Very limiting", "Can't do normal activities", "Affects some things but not others"],
            "relevance": "Functional impact and severity"
        },
        {
            "question": "Have you been more thirsty than usual?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["No change", "Slightly more thirsty", "Pretty thirsty", "Very thirsty", "Extremely thirsty", "Thirst comes and goes"],
            "relevance": "Metabolic symptoms like dehydration"
        },
        {
            "question": "Have you noticed your heart beating fast or irregularly?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["Heart feels normal", "Sometimes beats fast", "Often beats fast", "Heart races frequently", "Heart feels like it's pounding", "Heart rhythm feels irregular"],
            "relevance": "Cardiovascular symptoms"
        }
    ]

def generate_fallback_targeted_questions():
    """Generate 8 fallback questions organized by the required categories"""
    fallback_questions = [
        {
            "question": "When did these symptoms first begin?",
            "category": "onset",
            "type": "multiple_choice",
            "options": ["Less than 1 hour ago", "2-6 hours ago", "12-24 hours ago", "2-3 days ago", "1 week ago", "More than 1 week ago"],
            "relevance": "Essential for understanding symptom timeline"
        },
        {
            "question": "How would you describe the pattern of your symptoms?",
            "category": "duration", 
            "type": "multiple_choice",
            "options": ["Constant throughout the day", "Comes and goes in episodes", "Getting progressively worse", "Getting gradually better", "Stays about the same", "Varies unpredictably"],
            "relevance": "Important for understanding symptom progression"
        },
        {
            "question": "How severe are your symptoms on average?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["Mild (1-3/10 - minimal interference)", "Moderate (4-6/10 - some interference)", "Severe (7-8/10 - major interference)", "Very severe (9-10/10 - can't function)", "Varies throughout the day", "Hard to rate"],
            "relevance": "Critical for assessing symptom intensity"
        },
        {
            "question": "How would you describe the quality of your symptoms?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["Sharp/stabbing", "Dull/aching", "Throbbing", "Burning", "Cramping", "Other quality"],
            "relevance": "Important for characterizing symptom quality"
        },
        {
            "question": "Where do you feel your symptoms most strongly?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["One specific location", "Multiple separate areas", "Moves around/radiates", "Whole body/generalized", "Hard to pinpoint exactly", "Not applicable"],
            "relevance": "Important for localization of symptoms"
        },
        {
            "question": "What activities or situations make your symptoms worse?",
            "category": "aggravating",
            "type": "multiple_choice",
            "options": ["Physical activity/movement", "Stress or anxiety", "Eating or drinking", "Weather changes", "Lying down", "Standing/walking", "Nothing makes it worse", "Multiple triggers"],
            "relevance": "Identifies triggers that worsen symptoms"
        },
        {
            "question": "What helps relieve or improve your symptoms?",
            "category": "relieving",
            "type": "multiple_choice",
            "options": ["Rest", "Over-the-counter medication", "Heat application", "Cold application", "Position changes", "Nothing has helped", "Haven't tried anything", "Multiple things help"],
            "relevance": "Identifies effective relief methods"
        },
        {
            "question": "How much do your symptoms interfere with your daily activities?",
            "category": "characteristics",
            "type": "multiple_choice",
            "options": ["Not at all", "Slightly", "Moderately", "Quite a bit", "Extremely", "Varies by day"],
            "relevance": "Functional impact assessment"
        }
    ]
    
    print(f"🔄 Generated {len(fallback_questions)} fallback targeted questions")
    return fallback_questions

def extract_specific_symptoms(complaint_text):
    """Extract specific symptoms mentioned in the complaint text"""
    if not complaint_text:
        return []
    
    text = complaint_text.lower()
    symptoms = []
    
    # Common symptoms to look for
    symptom_patterns = {
        'headache': ['headache', 'head pain', 'head hurt'],
        'fever': ['fever', 'temperature', 'hot', 'chills'],
        'nausea': ['nausea', 'nauseous', 'sick to stomach'],
        'vomiting': ['vomiting', 'throwing up', 'vomit'],
        'dizziness': ['dizzy', 'dizziness', 'lightheaded'],
        'fatigue': ['tired', 'fatigue', 'exhausted', 'weak'],
        'chest pain': ['chest pain', 'chest hurt', 'chest pressure'],
        'shortness of breath': ['short of breath', 'breathing difficulty', 'cant breathe'],
        'stomach pain': ['stomach pain', 'stomach ache', 'abdominal pain'],
        'back pain': ['back pain', 'back hurt', 'back ache'],
        'cough': ['cough', 'coughing'],
        'sore throat': ['sore throat', 'throat pain', 'throat hurt']
    }
    
    for symptom, patterns in symptom_patterns.items():
        for pattern in patterns:
            if pattern in text:
                symptoms.append(symptom)
                break
    
    # Remove duplicates and return top 3 most relevant
    return list(dict.fromkeys(symptoms))[:3]

@app.route('/generate_followup_questions', methods=['POST'])
def generate_followup_questions():
    """Generate AI follow-up questions based on out-of-range vitals from step3"""
    try:
        print("✅ ===== STARTING FOLLOW-UP QUESTIONS GENERATION =====")
        
        # Get all patient data using new structure
        all_data = get_all_patient_data()
        if not all_data or 'steps' not in all_data:
            print("❌ ERROR - No patient data found")
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        print(f"📊 Available steps: {list(all_data['steps'].keys())}")
        
        # Get vitals from step3
        vitals = {}
        patient_identity = {}
        
        if 'step3' in all_data['steps']:
            step3_data = all_data['steps']['step3']
            vitals = step3_data.get('form_data', {})
            print(f"📋 Vitals from step3: {len(vitals)} fields")
        
        # Get patient identity from step1 or step2
        if 'step2' in all_data['steps']:
            step2_data = all_data['steps']['step2']
            patient_identity = step2_data.get('form_data', {})
            print(f"👤 Patient identity from step2: {len(patient_identity)} fields")
        elif 'step1' in all_data['steps']:
            step1_data = all_data['steps']['step1']
            patient_identity = step1_data.get('form_data', {})
            print(f"👤 Patient identity from step1: {len(patient_identity)} fields")
        
        if not vitals:
            print("❌ ERROR - No vitals data found")
            return jsonify({'success': False, 'error': 'No vitals data found. Please complete Step 3 first.'})
        
        # Log vitals inventory
        print("📊 ===== VITAL SIGNS INVENTORY =====")
        vital_keys = ['temperature', 'temperature_unit', 'pulse_rate', 'systolic_bp', 'diastolic_bp', 
                     'respiratory_rate', 'oxygen_saturation', 'blood_glucose', 'bmi', 
                     'weight', 'height', 'ecg_available', 'ecg_findings', 
                     'lung_congestion', 'water_in_lungs']
        
        for key in vital_keys:
            value = vitals.get(key)
            print(f"   {key}: '{value}' (type: {type(value)})")
        
        print("===== END INVENTORY =====")
        
        # Get temperature unit and adjust temperature ranges accordingly
        temperature_unit = vitals.get('temperature_unit', 'celsius')
        print(f"🌡️ Temperature unit detected: {temperature_unit}")
        
        # Define temperature ranges based on unit
        if temperature_unit == 'fahrenheit':
            temp_range = {'min': 97.0, 'max': 99.0, 'unit': '°F', 'name': 'Body Temperature'}
            temp_critical_low = 95.0
            temp_critical_high = 102.2
        else:  # celsius (default)
            temp_range = {'min': 36.1, 'max': 37.2, 'unit': '°C', 'name': 'Body Temperature'}
            temp_critical_low = 35.0
            temp_critical_high = 39.0
        
        print(f"🌡️ Using temperature range: {temp_range['min']}-{temp_range['max']} {temp_range['unit']}")
        
        # Define comprehensive normal ranges
        normal_ranges = {
            'temperature': temp_range,
            'pulse_rate': {'min': 60, 'max': 100, 'unit': 'bpm', 'name': 'Pulse Rate'},
            'systolic_bp': {'min': 90, 'max': 120, 'unit': 'mmHg', 'name': 'Systolic Blood Pressure'},
            'diastolic_bp': {'min': 60, 'max': 80, 'unit': 'mmHg', 'name': 'Diastolic Blood Pressure'},
            'respiratory_rate': {'min': 12, 'max': 20, 'unit': 'breaths/min', 'name': 'Respiratory Rate'},
            'oxygen_saturation': {'min': 95, 'max': 100, 'unit': '%', 'name': 'Oxygen Saturation'},
            'blood_glucose': {'min': 70, 'max': 140, 'unit': 'mg/dL', 'name': 'Blood Glucose'},
            'bmi': {'min': 18.5, 'max': 24.9, 'unit': 'kg/m²', 'name': 'Body Mass Index'},
            'weight': {'min': 40, 'max': 200, 'unit': 'kg', 'name': 'Weight'},
            'height': {'min': 140, 'max': 220, 'unit': 'cm', 'name': 'Height'}
        }
        
        # Analyze vitals for abnormalities
        abnormal_findings = []
        critical_findings = []
        
        print("🔍 Starting comprehensive vitals analysis...")
        
        for vital_name, ranges in normal_ranges.items():
            vital_value = vitals.get(vital_name)
            print(f"   Checking {vital_name}: '{vital_value}' (range: {ranges['min']}-{ranges['max']} {ranges['unit']})")
            
            if vital_value is not None and str(vital_value).strip():
                try:
                    value = float(vital_value)
                    
                    # Check if value is outside normal range
                    if value < ranges['min'] or value > ranges['max']:
                        print(f"   ⚠️ ABNORMAL - {vital_name}: {value} {ranges['unit']} outside range {ranges['min']}-{ranges['max']}")
                        
                        # Determine severity level
                        severity = 'abnormal'
                        
                        # Define critical thresholds
                        if vital_name == 'temperature' and (value < temp_critical_low or value > temp_critical_high):
                            severity = 'critical'
                        elif vital_name == 'pulse_rate' and (value < 50 or value > 120):
                            severity = 'critical'
                        elif vital_name == 'systolic_bp' and (value < 80 or value > 160):
                            severity = 'critical'
                        elif vital_name == 'diastolic_bp' and (value < 50 or value > 100):
                            severity = 'critical'
                        elif vital_name == 'oxygen_saturation' and value < 90:
                            severity = 'critical'
                        elif vital_name == 'blood_glucose' and (value < 60 or value > 200):
                            severity = 'critical'
                        elif vital_name == 'respiratory_rate' and (value < 8 or value > 30):
                            severity = 'critical'
                        
                        finding = {
                            'parameter': vital_name,
                            'parameter_name': ranges['name'],
                            'value': value,
                            'normal_range': f"{ranges['min']}-{ranges['max']}",
                            'unit': ranges['unit'],
                            'severity': severity,
                            'deviation': 'high' if value > ranges['max'] else 'low'
                        }
                        
                        if severity == 'critical':
                            critical_findings.append(finding)
                            print(f"   🚨 CRITICAL finding added: {finding}")
                        else:
                            abnormal_findings.append(finding)
                            print(f"   ⚠️ ABNORMAL finding added: {finding}")
                    else:
                        print(f"   ✅ NORMAL - {vital_name}: {value} {ranges['unit']}")
                except (ValueError, TypeError) as e:
                    print(f"   ❌ Could not convert {vital_name} value '{vital_value}' to float: {e}")
                    continue
            else:
                print(f"   ⚪ No value provided for {vital_name}")
        
        print(f"📊 Analysis complete - {len(abnormal_findings)} abnormal, {len(critical_findings)} critical findings")
        
        # Check for additional concerning clinical information
        concerning_findings = []
        
        # ECG findings
        if vitals.get('ecg_available') == 'yes':
            ecg_findings = vitals.get('ecg_findings', '').strip()
            if ecg_findings and ecg_findings.lower() not in ['normal', 'none', 'n/a', 'na']:
                concerning_findings.append({
                    'category': 'ECG',
                    'finding': ecg_findings,
                    'severity': 'concerning'
                })
                print(f"💓 ECG concern found: {ecg_findings}")
        
        # Respiratory findings
        lung_congestion = vitals.get('lung_congestion', '').strip()
        water_in_lungs = vitals.get('water_in_lungs', '').strip()
        
        if lung_congestion and lung_congestion.lower() not in ['no', 'none', 'normal']:
            concerning_findings.append({
                'category': 'Respiratory',
                'finding': f"Lung congestion: {lung_congestion}",
                'severity': 'concerning'
            })
            print(f"🫁 Lung congestion concern: {lung_congestion}")
            
        if water_in_lungs and water_in_lungs.lower() not in ['no', 'none', 'normal']:
            concerning_findings.append({
                'category': 'Respiratory', 
                'finding': f"Fluid in lungs: {water_in_lungs}",
                'severity': 'concerning'
            })
            print(f"🫁 Lung fluid concern: {water_in_lungs}")
        
        # Combine all findings
        all_findings = critical_findings + abnormal_findings
        total_concerns = len(all_findings) + len(concerning_findings)
        
        print(f"📊 Total medical concerns to address: {total_concerns}")
        
        # If NO abnormal findings at all, return no questions
        if total_concerns == 0:
            print("✅ No abnormal findings detected - patient appears healthy")
            return jsonify({
                'success': True,
                'questions': [],
                'message': 'All vital signs appear within normal ranges. No follow-up questions needed.',
                'findings_type': 'normal'
            })
        
        # Generate AI follow-up questions for abnormal findings
        patient_name = patient_identity.get('full_name', 'Patient')
        age = patient_identity.get('calculated_age', patient_identity.get('age', 'Unknown'))
        gender = patient_identity.get('gender', 'Unknown')
        
        print(f"👤 Patient info - Name: {patient_name}, Age: {age}, Gender: {gender}")
        
        # Build findings summary for AI
        findings_summary = []
        
        # Add vital sign abnormalities
        for finding in all_findings:
            deviation_text = "ELEVATED" if finding['deviation'] == 'high' else "LOW"
            findings_summary.append(
                f"{finding['parameter_name']}: {finding['value']} {finding['unit']} "
                f"({deviation_text} - Normal: {finding['normal_range']} {finding['unit']}) "
                f"[{finding['severity'].upper()}]"
            )
        
        # Add clinical concerns
        for concern in concerning_findings:
            findings_summary.append(f"{concern['category']}: {concern['finding']} [{concern['severity'].upper()}]")
        
        if not findings_summary:
            print("ℹ️ No findings to generate questions for")
            return jsonify({
                'success': True,
                'questions': [],
                'message': 'No abnormal findings detected.',
                'findings_type': 'normal'
            })
        
        findings_text = "\n".join([f"• {finding}" for finding in findings_summary])
        print(f"📝 Findings for AI analysis:\n{findings_text}")
        
        # Create AI prompt
        prompt_template = load_prompt("abnormal_vitals_followup")
        prompt = prompt_template.format(
            age=age,
            gender=gender,
            patient_name=patient_name,
            findings_text=findings_text
        )
        
        print(f"🤖 Sending prompt to AI (length: {len(prompt)} chars)")
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[
                    {
                        "role": "system", 
                        "content": load_prompt("followup_questions_system")
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1200,
                temperature=0.2
            )
            
            questions_text = response.choices[0].message.content.strip()
            print(f"🤖 Raw AI response: {questions_text[:300]}...")
            
            # Clean JSON response
            if questions_text.startswith('```json'):
                questions_text = questions_text[7:]
            if questions_text.endswith('```'):
                questions_text = questions_text[:-3]
            questions_text = questions_text.strip()
            
            # Parse AI-generated questions
            try:
                ai_questions = json.loads(questions_text)
                print(f"✅ Successfully parsed {len(ai_questions)} AI questions")
                
                # Validate and limit questions
                valid_questions = []
                for q in ai_questions:
                    if isinstance(q, dict) and 'question' in q and 'abnormal_finding' in q:
                        valid_questions.append({
                            'abnormal_finding': q.get('abnormal_finding', 'Unknown finding'),
                            'question': q.get('question', ''),
                            'priority': q.get('priority', 'medium'),
                            'medical_concern': q.get('medical_concern', 'general')
                        })
                    if len(valid_questions) >= 8:
                        break
                
                print(f"✅ Final {len(valid_questions)} valid questions generated")
                
                return jsonify({
                    'success': True,
                    'questions': valid_questions,
                    'findings_count': len(all_findings),
                    'critical_count': len(critical_findings),
                    'concerning_count': len(concerning_findings),
                    'findings_type': 'critical' if critical_findings else 'abnormal'
                })
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse error: {e}")
                
                # Generate fallback questions
                fallback_questions = []
                
                symptom_map = {
                    'temperature_high': 'fever, chills, sweating, or fatigue',
                    'temperature_low': 'chills, shivering, or feeling cold',
                    'pulse_rate_high': 'palpitations, chest racing, or anxiety',
                    'pulse_rate_low': 'dizziness, fatigue, or fainting',
                    'systolic_bp_high': 'headaches, chest pain, or vision changes',
                    'systolic_bp_low': 'dizziness, lightheadedness, or fainting',
                    'oxygen_saturation_low': 'shortness of breath, chest tightness, or difficulty breathing',
                    'blood_glucose_high': 'increased thirst, frequent urination, or blurred vision',
                    'blood_glucose_low': 'shakiness, sweating, confusion, or weakness'
                }
                
                for finding in all_findings[:4]:
                    param_name = finding['parameter_name']
                    value = finding['value']
                    unit = finding['unit']
                    normal_range = finding['normal_range']
                    deviation = "elevated" if finding['deviation'] == 'high' else "low"
                    severity = finding['severity']
                    
                    symptom_key = f"{finding['parameter']}_{deviation}"
                    symptoms = symptom_map.get(symptom_key, "any unusual symptoms")
                    
                    fallback_questions.append({
                        "abnormal_finding": f"{param_name}: {value} {unit} (Normal: {normal_range} {unit})",
                        "question": f"Your {param_name.lower()} is {value} {unit}, which is {deviation} compared to the normal range of {normal_range} {unit}. Are you experiencing any related symptoms like {symptoms}?",
                        "priority": "critical" if severity == 'critical' else "high",
                        "medical_concern": f"{deviation}_{finding['parameter']}"
                    })
                
                return jsonify({
                    'success': True,
                    'questions': fallback_questions[:8],
                    'findings_count': len(all_findings),
                    'critical_count': len(critical_findings),
                    'concerning_count': len(concerning_findings),
                    'findings_type': 'critical' if critical_findings else 'abnormal',
                    'note': 'Using fallback questions due to AI parsing error'
                })
                
        except Exception as e:
            print(f"❌ Error calling OpenAI API: {e}")
            return jsonify({
                'success': False, 
                'error': f'Failed to generate AI questions: {str(e)}',
                'findings_count': len(all_findings)
            })
            
    except Exception as e:
        print(f"❌ Error generating follow-up questions: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to generate questions: {str(e)}'})

@app.route('/analyze_medical_document', methods=['POST'])
def analyze_medical_document():
    """Analyze uploaded medical documents using AI"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'})
        
        file = request.files['file']
        doc_type = request.form.get('type', 'unknown')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # In a real implementation, you would:
        # 1. Save the file securely
        # 2. Use OCR to extract text from images/PDFs
        # 3. Use AI to analyze the extracted text
        # 4. Return structured information
        
        # For now, return a mock analysis
        mock_analysis = {
            'lab': 'Blood glucose: 140 mg/dL (slightly elevated)\nHemoglobin: 12.5 g/dL (normal)\nChol: 220 mg/dL (borderline high)',
            'image': 'X-ray shows clear lung fields with no signs of infection or abnormalities. Heart size appears normal.',
            'signal': 'ECG shows normal sinus rhythm with heart rate of 72 bpm. No signs of arrhythmia or ischemia detected.'
        }
        
        analysis = mock_analysis.get(doc_type, 'Document uploaded successfully. Analysis pending.')
        
        return jsonify({
            'success': True,
            'extracted_info': analysis,
            'filename': file.filename
        })
        
    except Exception as e:
        print(f"Error analyzing medical document: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to analyze document: {str(e)}'})

# Enhanced Step 3 Routes
@app.route('/get_patient_summary', methods=['GET'])
def get_patient_summary():
    """Get patient summary from previous steps"""
    if not validate_session_step(3):
        return jsonify({'success': False, 'error': 'Please complete previous steps'})
    
    patient_data = session['patient_data']
    registration = patient_data.get('registration', {})
    
    # Extract patient name from multiple possible fields
    patient_name = (registration.get('full_name') or 
                   registration.get('name') or 
                   registration.get('patient_name') or 
                   'Not provided')
    
    # Extract contact information
    phone = registration.get('phone') or registration.get('phone_number') or ''
    email = registration.get('email') or ''
    patient_contact = f"{phone} {email}".strip() or 'Not provided'
    
    # Check if emergency contact already set
    emergency_contact = registration.get('emergency_contact') or 'Not set'
    
    return jsonify({
        'success': True,
        'patient_name': patient_name,
        'patient_contact': patient_contact,
        'emergency_contact': emergency_contact
    })

def create_fallback_analysis(content, category):
    """Create a fallback analysis structure when JSON parsing fails"""
    print(f"DEBUG: Creating fallback analysis for category: {category}")
    
    # Extract useful information from the text response
    lines = content.split('\n')
    summary_text = []
    findings = []
    recommendations = []
    
    current_section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Detect section headers
        if any(keyword in line.lower() for keyword in ['summary', 'interpretation', 'conclusion']):
            current_section = 'summary'
        elif any(keyword in line.lower() for keyword in ['finding', 'observation', 'result']):
            current_section = 'findings'
        elif any(keyword in line.lower() for keyword in ['recommend', 'suggest', 'follow']):
            current_section = 'recommendations'
        elif line.startswith('•') or line.startswith('-') or line.startswith('*'):
            # Bullet point - add to current section
            clean_line = line.lstrip('•-* ').strip()
            if current_section == 'findings':
                findings.append(clean_line)
            elif current_section == 'recommendations':
                recommendations.append(clean_line)
            else:
                summary_text.append(clean_line)
        elif line and not line.startswith('{') and not line.startswith('}'):
            # Regular text line
            if current_section == 'summary':
                summary_text.append(line)
            elif current_section == 'findings':
                findings.append(line)
            elif current_section == 'recommendations':
                recommendations.append(line)
            else:
                summary_text.append(line)
    
    # Create structured response
    fallback_analysis = {
        "summary": ' '.join(summary_text) if summary_text else "AI analysis completed successfully.",
        "key_findings": findings if findings else ["Analysis results available in summary"],
        "abnormal_values": [],  # Will be populated if specific patterns found
        "recommendations": recommendations if recommendations else ["Consult with healthcare provider for detailed interpretation"],
        "follow_up": "Please review with your healthcare provider for clinical correlation",
        "confidence": "Medium"
    }
    
    # Look for abnormal values or concerning findings
    abnormal_patterns = ['abnormal', 'elevated', 'decreased', 'high', 'low', 'concerning', 'pathologic']
    for line in lines:
        if any(pattern in line.lower() for pattern in abnormal_patterns):
            fallback_analysis["abnormal_values"].append(line.strip())
    
    print(f"DEBUG: Fallback analysis created: {fallback_analysis}")
    return fallback_analysis

@app.route('/analyze_medical_report', methods=['POST'])
def analyze_medical_report():
    """Analyze uploaded medical reports using AI"""
    # Remove session validation for medical report analysis
    print("DEBUG: Medical report analysis requested")
    
    try:
        # Handle both FormData and JSON formats
        if request.content_type and 'multipart/form-data' in request.content_type:
            print("DEBUG: Processing FormData upload")
            # Handle FormData upload (from our new JavaScript)
            uploaded_file = request.files.get('file')
            report_type = request.form.get('report_type', '')
            
            print(f"DEBUG: Uploaded file: {uploaded_file}")
            print(f"DEBUG: Report type: {report_type}")
            
            if not uploaded_file:
                print("ERROR: No file uploaded")
                return jsonify({'success': False, 'error': 'No file uploaded'})
            
            # Read and encode file data
            file_content = uploaded_file.read()
            file_data = base64.b64encode(file_content).decode('utf-8')
            file_name = uploaded_file.filename
            file_type = uploaded_file.content_type or 'image/jpeg'
            
            print(f"DEBUG: File name: {file_name}")
            print(f"DEBUG: File type: {file_type}")
            print(f"DEBUG: File data length: {len(file_data)}")
            
            # Determine category from report_type with comprehensive mapping
            if report_type in ['lab', 'laboratory']:
                category = 'laboratory'
            elif report_type in ['image', 'medical_image', 'medical_images']:
                category = 'medical_image'
            elif report_type in ['pathology', 'pathology_report']:
                category = 'pathology'
            elif report_type in ['signaling', 'signal', 'signaling_report', 'ecg', 'eeg']:
                category = 'signal'
            else:
                # Fallback mapping
                category = report_type
                print(f"WARNING: Unknown report_type '{report_type}', using as category")
                
            print(f"DEBUG: Mapped category: {category} from report_type: {report_type}")
                
        else:
            print("DEBUG: Processing JSON upload")
            # Handle JSON format (existing functionality)
            data = request.get_json()
            file_data = data.get('file_data')
            file_name = data.get('file_name')
            file_type = data.get('file_type')
            category = data.get('category')  # laboratory, medical_image, signal, pathology
            report_type = data.get('report_type', '')
        
        if not file_data:
            return jsonify({'success': False, 'error': 'No file data provided'})
        
        # Create specialized prompt based on category
        if category in ['laboratory', 'lab']:
            prompt_template = load_prompt("educational_lab_analysis")
            prompt = prompt_template.format(file_name=file_name)
        elif category in ['medical_image', 'image']:
            prompt_template = load_prompt("educational_medical_image_analysis")
            prompt = prompt_template.format(file_name=file_name, report_type=report_type)
        elif category == 'pathology':
            prompt_template = load_prompt("educational_pathology_analysis")
            prompt = prompt_template.format(file_name=file_name)
        elif category in ['signal', 'signaling']:
            prompt_template = load_prompt("educational_signal_analysis")
            prompt = prompt_template.format(file_name=file_name, report_type=report_type)
        else:
            return jsonify({'success': False, 'error': 'Invalid report category'})
        
        # Call OpenAI API for analysis
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",  # Best model for image analysis
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{file_type};base64,{file_data}",
                                "detail": "high"  # Use high detail for better analysis
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,  # Increased for more detailed analysis
            temperature=0.1   # Lower temperature for more consistent medical analysis
        )
        
        content = response.choices[0].message.content.strip()
        print(f"DEBUG: OpenAI Response for {file_name} (category: {category}, report_type: {report_type})")
        print(f"DEBUG: Raw response length: {len(content)} characters")
        print(f"DEBUG: Raw response preview: {content[:200]}...")
        
        # Check if content is empty
        if not content:
            print("ERROR: Empty response from OpenAI API")
            return jsonify({'success': False, 'error': 'Empty response from AI analysis'})
        
        # More robust JSON parsing
        analysis = None
        
        # First, try to parse as direct JSON
        try:
            analysis = json.loads(content)
            print("DEBUG: Successfully parsed direct JSON")
        except json.JSONDecodeError:
            print("DEBUG: Direct JSON parsing failed, trying markdown cleanup")
            
            # Remove markdown code blocks
            cleaned_content = content
            if content.startswith('```json'):
                cleaned_content = content[7:]
                if cleaned_content.endswith('```'):
                    cleaned_content = cleaned_content[:-3]
            elif content.startswith('```'):
                cleaned_content = content[3:]
                if cleaned_content.endswith('```'):
                    cleaned_content = cleaned_content[:-3]
            
            cleaned_content = cleaned_content.strip()
            
            try:
                analysis = json.loads(cleaned_content)
                print("DEBUG: Successfully parsed cleaned JSON")
            except json.JSONDecodeError as e:
                print(f"ERROR: JSON parsing failed after cleanup: {str(e)}")
                print(f"DEBUG: Cleaned content: {cleaned_content}")
                
                # Try to extract JSON from mixed content using regex
                import re
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned_content, re.DOTALL)
                if json_match:
                    try:
                        analysis = json.loads(json_match.group())
                        print("DEBUG: Successfully extracted JSON using regex")
                    except json.JSONDecodeError:
                        print("ERROR: Regex-extracted JSON is still invalid")
                        # Create fallback analysis from the text response
                        analysis = create_fallback_analysis(content, category)
                else:
                    print("ERROR: No JSON pattern found in response")
                    # Create fallback analysis from the text response
                    analysis = create_fallback_analysis(content, category)
        
        if not analysis:
            return jsonify({'success': False, 'error': 'Failed to parse AI response'})
        
        print(f"DEBUG: Final analysis object: {analysis}")
        
        # Ensure patient_data exists in session
        if 'patient_data' not in session:
            session['patient_data'] = {}
            print("DEBUG: Initialized empty patient_data in session")
        
        # Store analysis in session
        if 'medical_reports_analysis' not in session['patient_data']:
            session['patient_data']['medical_reports_analysis'] = []
            print("DEBUG: Initialized medical_reports_analysis list")
        
        session['patient_data']['medical_reports_analysis'].append({
            'file_name': file_name,
            'category': category,
            'report_type': report_type,
            'analysis': analysis,
            'analyzed_at': datetime.now().isoformat()
        })
        session.modified = True
        
        return jsonify({
            'success': True,
            'insights': analysis
        })
        
    except Exception as e:
        print(f"ERROR: Exception in analyze_medical_report: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Analysis failed: {str(e)}'})

# API endpoints for patient data management

# API endpoints for patient data management
@app.route('/api/get_patient_data', methods=['GET'])
def api_get_patient_data():
    """API endpoint to get patient data from file storage"""
    try:
        patient_data = load_patient_data()
        if not patient_data:
            return jsonify({'success': False, 'error': 'No patient data found'})
        
        # Extract relevant data for frontend
        response_data = {
            'success': True,
            'patient_name': '',
            'phone': '',
            'email': '',
            'hospital_selection': ''
        }
        
        # Get patient name from registration data
        if 'registration' in patient_data:
            reg_data = patient_data['registration']
            first_name = reg_data.get('first_name', '')
            last_name = reg_data.get('last_name', '')
            response_data['patient_name'] = f"{first_name} {last_name}".strip()
            response_data['phone'] = reg_data.get('phone', '')
            response_data['email'] = reg_data.get('email', '')
            response_data['hospital_selection'] = reg_data.get('hospital_selection', '')
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Error in api_get_patient_data: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to load patient data: {str(e)}'})

@app.route('/api/save_patient_data', methods=['POST'])
def api_save_patient_data():
    """API endpoint to save patient data to file storage"""
    try:
        request_data = request.get_json()
        if not request_data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        step = request_data.get('step')
        data = request_data.get('data')
        
        if not step or not data:
            return jsonify({'success': False, 'error': 'Missing step or data'})
        
        # Load existing patient data
        patient_data = load_patient_data()
        if not patient_data:
            patient_data = {'created_at': datetime.now().isoformat()}
        
        # Step 4 functionality has been removed
        if step == 'step4':
            return jsonify({'success': False, 'error': 'Step 4 has been removed from this application'})
        
        # Save to file
        if save_patient_data(patient_data):
            print(f"Patient data saved successfully for {step}")
            
            # Update data timestamp (only if not step4)
            if step != 'step4':
                update_data_timestamp(int(step.replace('step', '')))
            
            # Update session minimally (skip for step4)
            if step != 'step4' and 'patient_data' not in session:
                session['patient_data'] = {}
                session['patient_data']['step_completed'] = int(step.replace('step', ''))
                session.modified = True
            
            return jsonify({'success': True, 'message': f'Data saved successfully for {step}'})
        else:
            return jsonify({'success': False, 'error': 'Failed to save data to file'})
            
    except Exception as e:
        print(f"Error in api_save_patient_data: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to save data: {str(e)}'})

@app.route('/download_report')
def download_report():
    """Generate and download a comprehensive medical report as PDF"""
    try:
        print("📄 Generating medical report PDF for download")
        
        # Check if user completed the assessment
        if not validate_session_step(7):
            return redirect('/step1')
        
        # Load all patient data
        patient_data = load_patient_data()
        if not patient_data:
            return jsonify({'error': 'No patient data found'}), 404
        
        # Generate PDF report
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
        from datetime import datetime
        import io
        from flask import make_response
        
        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        )
        
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.black,
            spaceAfter=6,
            fontName='Helvetica',
            alignment=TA_JUSTIFY
        )
        
        # Build content - FOCUSED ON FINAL DIAGNOSIS ONLY
        content = []
        
        # Modern Title with emoji
        content.append(Paragraph("🏥 AI-POWERED MEDICAL ASSESSMENT REPORT", title_style))
        content.append(Spacer(1, 0.3*inch))
        
        # Report metadata in attractive format
        generation_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        content.append(Paragraph(f"📅 <b>Report Generated:</b> {generation_date}", normal_style))
        content.append(Spacer(1, 0.5*inch))
        
        # Skip directly to FINAL DIAGNOSIS & CLINICAL ASSESSMENT
        # Removed: Patient Information, Assessment Summary, and all intermediate steps
        
        # Step 7: Final Diagnosis - Enhanced Version with Premium Styling
        step7_data = patient_data.get('step7', {})
        if step7_data:
            # Enhanced Final Diagnosis Header with visual appeal
            content.append(Paragraph("🏥 FINAL DIAGNOSIS & CLINICAL ASSESSMENT", 
                                   ParagraphStyle(
                                       name='FinalDiagnosisTitle',
                                       parent=styles['Heading1'],
                                       fontSize=16,
                                       textColor=colors.HexColor('#2c3e50'),
                                       spaceAfter=20,
                                       spaceBefore=10,
                                       alignment=TA_CENTER,
                                       fontName='Helvetica-Bold',
                                       backColor=colors.HexColor('#ecf0f1'),
                                       borderPadding=10,
                                       borderWidth=2,
                                       borderColor=colors.HexColor('#3498db')
                                   )))
            
            # Get the proper nested data structure
            form_data = step7_data.get('form_data', {})
            ai_data = step7_data.get('ai_generated_data', {})
            
            # Enhanced Clinical Summary with better styling
            clinical_summary = form_data.get('clinical_summary_edited') or ai_data.get('original_clinical_summary')
            if clinical_summary:
                content.append(Paragraph("📋 Clinical Summary", 
                                       ParagraphStyle(
                                           name='DiagnosisSubheading',
                                           parent=styles['Heading2'],
                                           fontSize=14,
                                           textColor=colors.HexColor('#27ae60'),
                                           spaceAfter=10,
                                           spaceBefore=15,
                                           fontName='Helvetica-Bold'
                                       )))
                content.append(Paragraph(clinical_summary, 
                                       ParagraphStyle(
                                           name='ClinicalText',
                                           parent=styles['Normal'],
                                           fontSize=11,
                                           textColor=colors.HexColor('#2c3e50'),
                                           spaceAfter=15,
                                           fontName='Helvetica',
                                           alignment=TA_JUSTIFY,
                                           leftIndent=10,
                                           backColor=colors.HexColor('#f8f9fa'),
                                           borderPadding=8
                                       )))
            
            # Enhanced ICD Codes Section
            icd_codes = ai_data.get('icd_codes_generated', [])
            if icd_codes:
                # Debug: Print ICD codes structure
                print(f"🔍 DEBUG: Found {len(icd_codes)} ICD codes for PDF")
                for i, code in enumerate(icd_codes[:3]):  # Print first 3 codes for debugging
                    print(f"   Code {i+1}: Type: {type(code)}")
                    if isinstance(code, dict):
                        print(f"   Code {i+1} Keys: {list(code.keys())}")
                        print(f"   Code {i+1} Title: '{code.get('title', 'MISSING')}'")
                        print(f"   Code {i+1} Code: '{code.get('code', 'MISSING')}'")
                        print(f"   Code {i+1} Description: '{code.get('description', 'MISSING')[:100]}...'")
                        print(f"   Code {i+1} Reasoning: '{code.get('reasoning', 'MISSING')[:100]}...'")
                    else:
                        print(f"   Code {i+1}: {code}")
                    print("   ---")
                
                content.append(Paragraph("🔍 Final ICD-11 Diagnosis Codes", 
                                       ParagraphStyle(
                                           name='ICDHeading',
                                           parent=styles['Heading2'],
                                           fontSize=14,
                                           textColor=colors.HexColor('#e74c3c'),
                                           spaceAfter=8,
                                           spaceBefore=15,
                                           fontName='Helvetica-Bold'
                                       )))
                content.append(Paragraph("✨ <i>Most likely conditions based on comprehensive AI assessment</i>", 
                                       ParagraphStyle(
                                           name='ICDSubtext',
                                           parent=styles['Normal'],
                                           fontSize=10,
                                           textColor=colors.HexColor('#7f8c8d'),
                                           spaceAfter=12,
                                           fontName='Helvetica-Oblique',
                                           alignment=TA_CENTER
                                       )))
                
                # Enhanced ICD Codes Table with premium styling
                icd_data = []
                icd_data.append(['🏷️ ICD Code', '📊 Confidence', '🧠 Clinical Reasoning'])
                
                for code in icd_codes:
                    # Get full reasoning or description - NO TRUNCATION, PROPER WRAPPING
                    reasoning = code.get('reasoning', '') or code.get('description', 'Clinical assessment based on symptoms and findings')
                    print(f"   🧠 Reasoning field: '{reasoning[:100]}...' (length: {len(reasoning)})")
                    
                    # Create wrapped text using Paragraph for proper text wrapping
                    reasoning_paragraph = Paragraph(
                        reasoning,
                        ParagraphStyle(
                            name='ReasoningWrap',
                            parent=styles['Normal'],
                            fontSize=9,
                            fontName='Helvetica',
                            alignment=TA_JUSTIFY,
                            leftIndent=2,
                            rightIndent=2,
                            spaceAfter=3,
                            spaceBefore=3,
                            wordWrap='LTR'
                        )
                    )
                    
                    icd_data.append([
                        str(code.get('code', 'N/A')),
                        f"{code.get('confidence', 0)}%",
                        reasoning_paragraph
                    ])
                
                # Enhanced ICD table with optimized column widths for proper text wrapping
                icd_table = Table(icd_data, colWidths=[1.2*inch, 0.8*inch, 4.0*inch])
                icd_table.setStyle(TableStyle([
                    # Enhanced Header Styling
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    
                    # Enhanced Row Styling with alternating colors
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f8f9fa')]),
                    ('GRID', (0, 0), (-1, -1), 1.5, colors.HexColor('#bdc3c7')),
                    
                    # Critical: TOP alignment for proper text wrapping
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    
                    # Text alignment optimized for each column
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # ICD Code column - center
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Condition Name - left
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Confidence - center
                    ('ALIGN', (3, 0), (3, -1), 'LEFT'),    # Clinical Reasoning - left for reading
                    
                    # Enhanced Padding - MORE space for text wrapping
                    ('TOPPADDING', (0, 0), (-1, -1), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    
                    # Highlight confidence column
                    ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#e8f5e8')),
                    ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#27ae60')),
                    ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
                    
                    # Special styling for high confidence (>80%)
                    ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#3498db')),
                ]))
                content.append(icd_table)
                content.append(Spacer(1, 0.4*inch))
                
                # Enhanced Confidence Level Guide with beautiful styling
                content.append(Paragraph("📈 Confidence Level Guide", 
                                       ParagraphStyle(
                                           name='ConfidenceGuideTitle',
                                           parent=styles['Heading2'],
                                           fontSize=12,
                                           textColor=colors.HexColor('#3498db'),
                                           spaceAfter=12,
                                           fontName='Helvetica-Bold'
                                       )))
                
                confidence_info = [
                    ["🟢 90-100%", "Highly likely diagnosis - Strong clinical evidence"],
                    ["🟡 70-89%", "Probable diagnosis - Good supporting evidence"],
                    ["🟠 50-69%", "Possible diagnosis - Requires further evaluation"],
                    ["🔴 Below 50%", "Less likely - Additional testing recommended"]
                ]
                
                conf_table = Table(confidence_info, colWidths=[1.5*inch, 4.5*inch])
                conf_table.setStyle(TableStyle([
                    # Enhanced styling for confidence table
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f8f9fa')]),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                content.append(conf_table)
                content.append(Spacer(1, 0.5*inch))
                
            # Enhanced Recommended Lab Tests Section from Step7
            recommended_tests = ai_data.get('diagnostic_tests_recommended', [])
            if recommended_tests:
                content.append(Paragraph("🔬 RECOMMENDED LABORATORY TESTS", 
                                       ParagraphStyle(
                                           name='LabTestsTitle',
                                           parent=styles['Heading2'],
                                           fontSize=14,
                                           textColor=colors.HexColor('#8e44ad'),
                                           spaceAfter=12,
                                           spaceBefore=15,
                                           fontName='Helvetica-Bold'
                                       )))
                
                content.append(Paragraph("🧪 <i>Additional tests recommended based on differential diagnosis</i>", 
                                       ParagraphStyle(
                                           name='LabTestsSubtext',
                                           parent=styles['Normal'],
                                           fontSize=10,
                                           textColor=colors.HexColor('#7f8c8d'),
                                           spaceAfter=15,
                                           fontName='Helvetica-Oblique',
                                           alignment=TA_CENTER
                                       )))
                
                # Create enhanced lab tests table
                lab_data = []
                lab_data.append(['🧪 Test Name', '🎯 Purpose', '⚡ Priority', '📋 Instructions'])
                
                for test in recommended_tests:
                    if isinstance(test, dict):
                        test_name = test.get('test_name', test.get('name', 'N/A'))
                        purpose = test.get('purpose', test.get('reason', 'Diagnostic evaluation'))
                        priority = test.get('priority', test.get('urgency', 'Standard'))
                        instructions = test.get('instructions', test.get('notes', 'Follow standard protocol'))
                    else:
                        # Handle string format
                        test_name = str(test)
                        purpose = 'Diagnostic evaluation'
                        priority = 'Standard'
                        instructions = 'Follow standard protocol'
                    
                    # Create Paragraph objects for proper text wrapping
                    test_name_para = Paragraph(
                        test_name,
                        ParagraphStyle(
                            name='TestNameWrap',
                            parent=styles['Normal'],
                            fontSize=9,
                            fontName='Helvetica-Bold',
                            alignment=TA_LEFT,
                            leftIndent=2,
                            rightIndent=2
                        )
                    )
                    
                    purpose_para = Paragraph(
                        purpose,
                        ParagraphStyle(
                            name='PurposeWrap',
                            parent=styles['Normal'],
                            fontSize=9,
                            fontName='Helvetica',
                            alignment=TA_LEFT,
                            leftIndent=2,
                            rightIndent=2
                        )
                    )
                    
                    instructions_para = Paragraph(
                        instructions,
                        ParagraphStyle(
                            name='InstructionsWrap',
                            parent=styles['Normal'],
                            fontSize=8,
                            fontName='Helvetica',
                            alignment=TA_LEFT,
                            leftIndent=2,
                            rightIndent=2
                        )
                    )
                    
                    lab_data.append([
                        test_name_para,
                        purpose_para,
                        priority,
                        instructions_para
                    ])
                
                # Enhanced lab tests table with proper column widths
                lab_table = Table(lab_data, colWidths=[1.5*inch, 2*inch, 0.8*inch, 1.7*inch])
                lab_table.setStyle(TableStyle([
                    # Header styling
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8e44ad')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    
                    # Data rows styling
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f4f1f8')]),
                    ('GRID', (0, 0), (-1, -1), 1.5, colors.HexColor('#bdc3c7')),
                    
                    # Alignment and padding
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),    # Test name
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Purpose
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Priority
                    ('ALIGN', (3, 0), (3, -1), 'LEFT'),    # Instructions
                    
                    # Enhanced padding for readability
                    ('TOPPADDING', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    
                    # Highlight priority column
                    ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#fff3cd')),
                    ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#856404')),
                    ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
                    
                    # Special styling for header
                    ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#6c3483')),
                ]))
                content.append(lab_table)
                content.append(Spacer(1, 0.4*inch))
                
            # Enhanced Clinical Recommendations Section from Step7
            clinical_recommendations = ai_data.get('clinical_recommendations', [])
            if clinical_recommendations:
                content.append(Paragraph("💡 CLINICAL RECOMMENDATIONS", 
                                       ParagraphStyle(
                                           name='ClinicalRecsTitle',
                                           parent=styles['Heading2'],
                                           fontSize=14,
                                           textColor=colors.HexColor('#27ae60'),
                                           spaceAfter=12,
                                           spaceBefore=15,
                                           fontName='Helvetica-Bold'
                                       )))
                
                content.append(Paragraph("📋 <i>Evidence-based recommendations for optimal patient care</i>", 
                                       ParagraphStyle(
                                           name='ClinicalRecsSubtext',
                                           parent=styles['Normal'],
                                           fontSize=10,
                                           textColor=colors.HexColor('#7f8c8d'),
                                           spaceAfter=15,
                                           fontName='Helvetica-Oblique',
                                           alignment=TA_CENTER
                                       )))
                
                # Format clinical recommendations as numbered list with enhanced styling
                for i, recommendation in enumerate(clinical_recommendations, 1):
                    if isinstance(recommendation, dict):
                        rec_text = recommendation.get('recommendation', recommendation.get('text', str(recommendation)))
                        priority = recommendation.get('priority', 'Standard')
                        category = recommendation.get('category', 'General')
                    else:
                        rec_text = str(recommendation)
                        priority = 'Standard'
                        category = 'General'
                    
                    # Create styled recommendation paragraph
                    rec_paragraph = Paragraph(
                        f"<b>{i}.</b> {rec_text}",
                        ParagraphStyle(
                            name=f'Recommendation{i}',
                            parent=styles['Normal'],
                            fontSize=10,
                            fontName='Helvetica',
                            alignment=TA_JUSTIFY,
                            leftIndent=15,
                            rightIndent=10,
                            spaceAfter=8,
                            spaceBefore=5,
                            backColor=colors.HexColor('#f0f8e8'),
                            borderPadding=8,
                            borderWidth=1,
                            borderColor=colors.HexColor('#d4edda')
                        )
                    )
                    content.append(rec_paragraph)
                
                content.append(Spacer(1, 0.4*inch))
                
        # Enhanced Footer Section with Professional Touch
        content.append(Spacer(1, 0.5*inch))
        
        # Professional Disclaimer with better styling
        content.append(Paragraph("⚠️ IMPORTANT MEDICAL DISCLAIMER", 
                               ParagraphStyle(
                                   name='DisclaimerTitle',
                                   parent=styles['Heading2'],
                                   fontSize=12,
                                   textColor=colors.HexColor('#e74c3c'),
                                   spaceAfter=10,
                                   fontName='Helvetica-Bold',
                                   alignment=TA_CENTER,
                                   backColor=colors.HexColor('#ffeaa7'),
                                   borderPadding=5
                               )))
        
        disclaimer_text = """
        🔬 This report is generated by an AI-powered assessment system and is intended for informational purposes only. 
        It does not constitute medical advice, diagnosis, or treatment recommendations. Always consult with qualified 
        healthcare professionals for proper medical diagnosis and treatment. This assessment should be used as a 
        supplement to, not a replacement for, professional medical consultation.
        """
        content.append(Paragraph(disclaimer_text, 
                               ParagraphStyle(
                                   name='DisclaimerText',
                                   parent=styles['Normal'],
                                   fontSize=10,
                                   textColor=colors.HexColor('#2c3e50'),
                                   fontName='Helvetica',
                                   alignment=TA_JUSTIFY,
                                   leftIndent=15,
                                   rightIndent=15,
                                   spaceAfter=20,
                                   backColor=colors.HexColor('#fff5f5'),
                                   borderPadding=10,
                                   borderWidth=1,
                                   borderColor=colors.HexColor('#e74c3c')
                               )))
        
        # Professional Footer
        content.append(Spacer(1, 0.3*inch))
        content.append(Paragraph("✨ Generated by AI-Powered Medical Assessment System ✨", 
                               ParagraphStyle('ProfessionalFooter', 
                                             parent=styles['Normal'],
                                             fontSize=10,
                                             textColor=colors.HexColor('#7f8c8d'),
                                             alignment=TA_CENTER,
                                             fontName='Helvetica-Oblique',
                                             spaceAfter=10)))
        
        # Build PDF
        doc.build(content)
        buffer.seek(0)
        
        # Create response
        response = make_response(buffer.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="Medical_Assessment_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
        
        print("✅ Medical report PDF generated successfully")
        return response
        
    except Exception as e:
        print(f"❌ Error generating PDF report: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to generate PDF report: {str(e)}'}), 500

@app.route('/get_referring_doctors', methods=['GET'])
def get_referring_doctors():
    """Get list of referring doctors from database/static data"""
    try:
        # Static data based on the SQL table structure
        referring_doctors = [
            {
                'id': 1,
                'first_name': 'Rajesh',
                'last_name': 'Sharma',
                'phone_number': '1111111111',
                'email_address': 'rajesh.sharma@hospital.com',
                'area_of_expertise': 'Cardiology'
            },
            {
                'id': 2,
                'first_name': 'Priya',
                'last_name': 'Patel',
                'phone_number': '2222222222',
                'email_address': 'priya.patel@clinic.com',
                'area_of_expertise': 'Pediatrics'
            },
            {
                'id': 3,
                'first_name': 'Amit',
                'last_name': 'Kumar',
                'phone_number': '3333333333',
                'email_address': 'amit.kumar@medical.com',
                'area_of_expertise': 'Orthopedics'
            },
            {
                'id': 4,
                'first_name': 'Sunita',
                'last_name': 'Singh',
                'phone_number': '4444444444',
                'email_address': 'sunita.singh@healthcare.com',
                'area_of_expertise': 'Dermatology'
            },
            {
                'id': 5,
                'first_name': 'Vikash',
                'last_name': 'Gupta',
                'phone_number': '5555555555',
                'email_address': 'vikash.gupta@hospital.com',
                'area_of_expertise': 'Neurology'
            },
            {
                'id': 6,
                'first_name': 'Meera',
                'last_name': 'Jain',
                'phone_number': '6666666666',
                'email_address': 'meera.jain@clinic.com',
                'area_of_expertise': 'Gynecology'
            },
            {
                'id': 7,
                'first_name': 'Rohit',
                'last_name': 'Verma',
                'phone_number': '7777777777',
                'email_address': 'rohit.verma@medical.com',
                'area_of_expertise': 'Gastroenterology'
            },
            {
                'id': 8,
                'first_name': 'Kavita',
                'last_name': 'Agarwal',
                'phone_number': '8888888888',
                'email_address': 'kavita.agarwal@healthcare.com',
                'area_of_expertise': 'Pulmonology'
            },
            {
                'id': 9,
                'first_name': 'Sanjay',
                'last_name': 'Mishra',
                'phone_number': '9999999999',
                'email_address': 'sanjay.mishra@hospital.com',
                'area_of_expertise': 'Oncology'
            }
        ]
        
        print(f"✅ Retrieved {len(referring_doctors)} referring doctors")
        
        return jsonify({
            'success': True,
            'doctors': referring_doctors,
            'count': len(referring_doctors)
        })
        
    except Exception as e:
        print(f"❌ Error getting referring doctors: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to get referring doctors: {str(e)}'})

@app.route('/get_step_data/<int:step_number>', methods=['GET'])
def get_step_data_route(step_number):
    """Get data from a specific step via API endpoint"""
    try:
        # Use the existing load_patient_data function to get data from JSON files
        patient_data = load_patient_data()
        
        if not patient_data:
            return jsonify({
                'success': False,
                'error': 'No patient data found'
            })
            
        step_key = f'step{step_number}'
        
        if step_key in patient_data:
            step_data = patient_data[step_key]
            print(f"✅ Found step {step_number} data: {step_data.get('form_data', {})}")
            
            return jsonify({
                'success': True,
                'step_number': step_number,
                'form_data': step_data.get('form_data', {}),
                'ai_generated_data': step_data.get('ai_generated_data', {}),
                'files_uploaded': step_data.get('files_uploaded', {}),
                'timestamp': step_data.get('timestamp', '')
            })
        else:
            print(f"❌ Step {step_number} data not found in patient data")
            return jsonify({
                'success': False,
                'error': f'Step {step_number} data not found'
            })
            
    except Exception as e:
        print(f"❌ Error getting step {step_number} data: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to get step data: {str(e)}'})

# Main application code continues here
if __name__ == '__main__':
    api_key = os.getenv('OPENAI_API_KEY')
    print(f"OpenAI API Key loaded: {'Yes' if api_key else 'No'}")
    if api_key:
        print(f"API Key starts with: {api_key[:10]}...")
    app.run(host='0.0.0.0', port=5001, debug=True)

