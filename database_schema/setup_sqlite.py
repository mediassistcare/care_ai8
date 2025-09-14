import sqlite3
import json
import os
from datetime import datetime
import uuid

def setup_sqlite_database():
    """Create SQLite database and cases table for testing"""
    try:
        # Create database in current directory
        db_path = "care_ai_cases.db"
        
        print(f"🗄️ Creating SQLite database: {db_path}")
        
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Create cases table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number VARCHAR(50) UNIQUE NOT NULL,
            details TEXT NOT NULL,
            status VARCHAR(100) NOT NULL,
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        cursor.execute(create_table_sql)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_number ON cases(case_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON cases(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON cases(created_at);")
        
        connection.commit()
        
        print("✅ SQLite database and table created successfully")
        
        # Test insert
        test_case_number = f"CASE-{datetime.now().year}-TEST"
        test_details = json.dumps({"test": "data", "timestamp": datetime.now().isoformat()})
        
        cursor.execute("""
            INSERT OR REPLACE INTO cases (case_number, details, status, feedback) 
            VALUES (?, ?, ?, ?)
        """, (test_case_number, test_details, "pending_review", ""))
        
        connection.commit()
        
        # Verify insert
        cursor.execute("SELECT * FROM cases WHERE case_number = ?", (test_case_number,))
        result = cursor.fetchone()
        
        if result:
            print(f"✅ Test record inserted successfully: {result[1]}")
        else:
            print("❌ Test record insertion failed")
            
        cursor.close()
        connection.close()
        
        return db_path
        
    except Exception as e:
        print(f"❌ Error setting up SQLite database: {e}")
        return None

def insert_case_from_json():
    """Insert actual case data from the latest JSON file"""
    try:
        import glob
        
        # Find latest patient data file
        pattern = "care_app_data/patient_data_*.json"
        files = glob.glob(pattern)
        
        if not files:
            print("❌ No patient data files found")
            return
            
        latest_file = max(files, key=os.path.getctime)
        print(f"📁 Reading from: {latest_file}")
        
        with open(latest_file, 'r') as f:
            data = json.load(f)
            
        step7_data = data.get('step7', {})
        
        if not step7_data:
            print("❌ No step7 data found")
            return
            
        # Generate case number
        current_year = datetime.now().year
        case_number = f"CASE-{current_year}-0001"
        
        # Convert step7 data to JSON string
        details = json.dumps(step7_data, indent=2, default=str)
        
        # Insert into SQLite
        db_path = "care_ai_cases.db"
        
        if not os.path.exists(db_path):
            print("❌ Database doesn't exist. Run setup first.")
            return
            
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO cases (case_number, details, status, feedback) 
            VALUES (?, ?, ?, ?)
        """, (case_number, details, "pending_review", ""))
        
        connection.commit()
        
        print(f"✅ Case {case_number} inserted successfully!")
        
        # Display summary
        cursor.execute("SELECT case_number, status, created_at FROM cases ORDER BY created_at DESC LIMIT 1")
        result = cursor.fetchone()
        
        if result:
            print(f"📋 Case Number: {result[0]}")
            print(f"📊 Status: {result[1]}")
            print(f"📅 Created: {result[2]}")
            
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"❌ Error inserting case: {e}")

if __name__ == "__main__":
    print("🗄️ SQLite Database Setup for CARE AI Cases")
    print("=" * 50)
    
    # Setup database
    db_path = setup_sqlite_database()
    
    if db_path:
        print(f"\n📁 Database created at: {os.path.abspath(db_path)}")
        
        # Insert actual case data
        print("\n📋 Inserting case from JSON data...")
        print("-" * 30)
        insert_case_from_json()
        
        print(f"\n💡 You can now:")
        print(f"   1. View the database file: {os.path.abspath(db_path)}")
        print(f"   2. Modify the Flask app to use SQLite instead of MySQL")
        print(f"   3. Test the case submission functionality")