"""
Prompt loader utility for the Care AI application.
This module provides functions to load prompts from external text files.
"""

import os

def load_prompt(prompt_name):
    """
    Load a prompt from the prompts directory.
    
    Args:
        prompt_name (str): Name of the prompt file (without .txt extension)
        
    Returns:
        str: The prompt content
        
    Raises:
        FileNotFoundError: If the prompt file doesn't exist
        IOError: If there's an error reading the file
    """
    try:
        # Get the directory where this script is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        prompts_dir = os.path.join(current_dir, 'prompts')
        prompt_file = os.path.join(prompts_dir, f"{prompt_name}.txt")
        
        # Check if file exists
        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        # Read and return the prompt content
        with open(prompt_file, 'r', encoding='utf-8') as file:
            content = file.read().strip()
            
        return content
        
    except Exception as e:
        print(f"Error loading prompt '{prompt_name}': {str(e)}")
        raise

def get_photo_analysis_prompt(photo_type, report_type=None):
    """
    Get the appropriate photo analysis prompt based on photo type.
    
    Args:
        photo_type (str): Type of photo ('tongue', 'throat', 'infection', 'laboratory', 'medical_image', 'signal')
        report_type (str, optional): Specific report type for dynamic prompts
        
    Returns:
        str: The formatted prompt content
    """
    try:
        # Map photo types to prompt files
        prompt_mapping = {
            'tongue': 'photo_tongue_analysis',
            'throat': 'photo_throat_analysis',
            'infection': 'photo_infection_analysis',
            'laboratory': 'photo_laboratory_analysis',
            'medical_image': 'photo_medical_image_analysis',
            'signal': 'photo_signal_analysis'
        }
        
        # Get the prompt name, default to infection if not found
        prompt_name = prompt_mapping.get(photo_type, 'photo_infection_analysis')
        
        # Load the prompt
        prompt_content = load_prompt(prompt_name)
        
        # Replace placeholder if report_type is provided
        if report_type and '{report_type}' in prompt_content:
            prompt_content = prompt_content.replace('{report_type}', report_type.upper())
        elif '{report_type}' in prompt_content:
            prompt_content = prompt_content.replace('{report_type}', 'UNKNOWN')
            
        return prompt_content
        
    except Exception as e:
        print(f"Error getting photo analysis prompt: {str(e)}")
        # Return a fallback prompt
        return "Analyze the uploaded image and provide medical insights about any visible conditions or findings."

def list_available_prompts():
    """
    List all available prompt files.
    
    Returns:
        list: List of prompt names (without .txt extension)
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        prompts_dir = os.path.join(current_dir, 'prompts')
        
        if not os.path.exists(prompts_dir):
            return []
            
        prompt_files = [f[:-4] for f in os.listdir(prompts_dir) if f.endswith('.txt')]
        return sorted(prompt_files)
        
    except Exception as e:
        print(f"Error listing prompts: {str(e)}")
        return []
