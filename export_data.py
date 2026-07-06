import os
import sqlite3
import pandas as pd

# Paths
DB_PATH = "adventure_works.db"
OUTPUT_DIR = "powerbi_data"

def export_tables_for_powerbi():
    print("=" * 60)
    print("EXPORTING SQLITE TABLES TO CSV FOR POWER BI")
    print("=" * 60)
    
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: '{OUTPUT_DIR}'")
        
    # Connect to SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"Found {len(tables)} tables to export: {tables}")
    print("-" * 60)
    
    # Export each table to CSV
    for table in tables:
        print(f"Exporting table '{table}'...")
        # Read table using Pandas
        df = pd.read_sql_query(f"SELECT * FROM {table};", conn)
        
        # Save as CSV in the output folder
        csv_path = os.path.join(OUTPUT_DIR, f"{table}.csv")
        df.to_csv(csv_path, index=False, encoding='utf-8')
        print(f"  -> Successfully saved as '{csv_path}' ({len(df):,} rows)")
        
    conn.close()
    print("=" * 60)
    print("EXPORT COMPLETED! Your Power BI data files are ready.")
    print("=" * 60)

if __name__ == "__main__":
    export_tables_for_powerbi()
