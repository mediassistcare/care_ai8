#!/usr/bin/env python3
"""
Remove feedback column from cases table
Keeps all other columns intact: id, case_number, details, status, created_at, updated_at, panel_feedback, modified_date
"""

import sqlite3
import os
from datetime import datetime

def remove_feedback_column():
    """Remove the feedback column from cases table while preserving all other data"""
    
    db_path = 'care_ai_cases.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} not found!")
        return False
    
    print(f"🗄️ CARE AI Database Column Removal")
    print(f"============================================================")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Database: {db_path}")
    print()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First, check current table structure
        print("📋 Current table structure:")
        cursor.execute("PRAGMA table_info(cases)")
        current_columns = cursor.fetchall()
        for col in current_columns:
            print(f"   • {col[1]}: {col[2]} {'(PRIMARY KEY)' if col[5] else ''}")
        print()
        
        # Check if feedback column exists
        feedback_exists = any(col[1] == 'feedback' for col in current_columns)
        if not feedback_exists:
            print("✅ Feedback column does not exist. Nothing to remove.")
            conn.close()
            return True
        
        # Get current data count
        cursor.execute("SELECT COUNT(*) FROM cases")
        row_count = cursor.fetchone()[0]
        print(f"📊 Current rows in cases table: {row_count}")
        print()
        
        print("🔧 Starting column removal process...")
        
        # Step 0: Clean up any existing temporary table
        print("   0️⃣ Cleaning up any existing temporary table...")
        cursor.execute("DROP TABLE IF EXISTS cases_new")
        
        # Step 1: Create new table without feedback column
        print("   1️⃣ Creating new table structure without feedback column...")
        cursor.execute("""
            CREATE TABLE cases_new (
                id INTEGER PRIMARY KEY,
                case_number VARCHAR(50) NOT NULL UNIQUE,
                details TEXT NOT NULL,
                status VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                panel_feedback TEXT DEFAULT '',
                modified_date DATETIME
            )
        """)
        
        # Step 2: Copy data from old table to new table (excluding feedback column)
        print("   2️⃣ Copying data to new table (excluding feedback column)...")
        cursor.execute("""
            INSERT INTO cases_new (id, case_number, details, status, created_at, updated_at, panel_feedback, modified_date)
            SELECT id, case_number, details, status, created_at, updated_at, panel_feedback, modified_date
            FROM cases
        """)
        
        # Step 3: Drop old table
        print("   3️⃣ Removing old table...")
        cursor.execute("DROP TABLE cases")
        
        # Step 4: Rename new table to original name
        print("   4️⃣ Renaming new table...")
        cursor.execute("ALTER TABLE cases_new RENAME TO cases")
        
        # Step 5: Recreate indexes
        print("   5️⃣ Recreating indexes...")
        cursor.execute("CREATE INDEX idx_created_at ON cases(created_at)")
        cursor.execute("CREATE INDEX idx_status ON cases(status)")
        cursor.execute("CREATE INDEX idx_case_number ON cases(case_number)")
        # Note: sqlite_autoindex_cases_1 is automatically created by SQLite for UNIQUE constraints
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        print()
        print("✅ Column removal completed successfully!")
        print()
        print("📋 New table structure:")
        cursor.execute("PRAGMA table_info(cases)")
        new_columns = cursor.fetchall()
        for col in new_columns:
            print(f"   • {col[1]}: {col[2]} {'(PRIMARY KEY)' if col[5] else ''}")
        
        # Verify data count
        cursor.execute("SELECT COUNT(*) FROM cases")
        new_row_count = cursor.fetchone()[0]
        print(f"\n📊 Rows after migration: {new_row_count}")
        
        if new_row_count == row_count:
            print("✅ All data successfully preserved!")
        else:
            print(f"⚠️ Row count mismatch: {row_count} -> {new_row_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error removing feedback column: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    success = remove_feedback_column()
    if success:
        print("\n🎉 Feedback column successfully removed from cases table!")
        print("   All other columns and data have been preserved.")
    else:
        print("\n💥 Failed to remove feedback column.")