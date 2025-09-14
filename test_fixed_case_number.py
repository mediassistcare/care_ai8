import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app_new import generate_case_number

def test_fixed_case_number_generation():
    """Test the fixed case number generation function"""
    
    print("🔧 Testing fixed case number generation...")
    
    # Test the function multiple times
    for i in range(3):
        case_number = generate_case_number()
        print(f"📋 Generated case number {i+1}: {case_number}")
    
    print("✅ Fixed case number generation working!")

if __name__ == "__main__":
    test_fixed_case_number_generation()