#!/usr/bin/env python3
"""
Script to show all table information in the SQLite database
"""

import sqlite3
import json
from datetime import datetime

def show_database_info():
    """Show comprehensive database information"""
    print("🗄️ CARE AI SQLite Database Information")
    print("=" * 60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Database: care_ai_cases.db")
    print()
    
    try:
        connection = sqlite3.connect('care_ai_cases.db')
        cursor = connection.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        if not tables:
            print("❌ No tables found in database")
            return
            
        print(f"📋 Tables in database: {len(tables)}")
        print()
        
        for table_name, in tables:
            print(f"📊 Table: {table_name}")
            print("-" * 40)
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            print("📋 Columns:")
            for col in columns:
                col_id, name, data_type, not_null, default_value, primary_key = col
                pk_indicator = " (PRIMARY KEY)" if primary_key else ""
                null_indicator = " NOT NULL" if not_null else ""
                default_indicator = f" DEFAULT {default_value}" if default_value else ""
                print(f"   • {name}: {data_type}{pk_indicator}{null_indicator}{default_indicator}")
            
            # Get indexes
            cursor.execute(f"PRAGMA index_list({table_name})")
            indexes = cursor.fetchall()
            
            if indexes:
                print("🔍 Indexes:")
                for index in indexes:
                    seq, name, unique, origin, partial = index
                    unique_indicator = " (UNIQUE)" if unique else ""
                    print(f"   • {name}{unique_indicator}")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            print(f"📊 Total rows: {row_count}")
            
            # Show sample data if available
            if row_count > 0:
                cursor.execute(f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT 3")
                sample_rows = cursor.fetchall()
                
                print("📄 Sample data (latest 3 rows):")
                for i, row in enumerate(sample_rows, 1):
                    print(f"   Row {i}:")
                    for j, col in enumerate(columns):
                        col_name = col[1]
                        value = row[j]
                        
                        # Format the display based on column type
                        if col_name == 'details' and value:
                            try:
                                # Try to parse JSON and show summary
                                details = json.loads(value)
                                if isinstance(details, dict):
                                    keys = list(details.keys())
                                    print(f"     {col_name}: JSON with keys: {keys}")
                                else:
                                    print(f"     {col_name}: JSON data")
                            except:
                                # If not JSON, show truncated text
                                display_value = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                                print(f"     {col_name}: {display_value}")
                        else:
                            print(f"     {col_name}: {value}")
                    print()
            
            print()
        
        cursor.close()
        connection.close()
        
        print("💡 Useful commands:")
        print("   • View all cases: python view_cases.py")
        print("   • Test database: python test_sqlite_workflow.py")
        print("   • Run Flask app: python app_new.py")
        
    except Exception as e:
        print(f"❌ Error reading database: {e}")

if __name__ == "__main__":
    show_database_info()