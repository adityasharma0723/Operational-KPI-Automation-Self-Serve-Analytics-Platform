import os
import sqlite3
import pandas as pd
import time

# Paths
DATASET_DIR = r"c:\Users\addis\OneDrive\Desktop\ADVENTURE WORKS DATASET"
DB_PATH = "adventure_works.db"

def clean_and_standardize_dates(df, date_columns):
    """Parses date columns and formats them as standard ISO YYYY-MM-DD strings."""
    for col in date_columns:
        if col in df.columns:
            # Parse using format='mixed' to handle different date structures (DD-MM-YYYY, YYYY-MM-DD, etc.)
            df[col] = pd.to_datetime(df[col], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
    return df

def build_database_schema(conn):
    """Creates the relational database schema with proper keys, types, and constraints."""
    cursor = conn.cursor()
    
    # Enable Foreign Key support
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. Calendar Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calendar (
        Date TEXT PRIMARY KEY
    );
    """)
    
    # 2. Customers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        CustomerKey INTEGER PRIMARY KEY,
        Prefix TEXT,
        FirstName TEXT,
        LastName TEXT,
        BirthDate TEXT,
        MaritalStatus TEXT,
        Gender TEXT,
        EmailAddress TEXT,
        AnnualIncome REAL,
        TotalChildren INTEGER,
        EducationLevel TEXT,
        Occupation TEXT,
        HomeOwner TEXT
    );
    """)
    
    # 3. Categories Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        ProductCategoryKey INTEGER PRIMARY KEY,
        CategoryName TEXT
    );
    """)
    
    # 4. Subcategories Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subcategories (
        ProductSubcategoryKey INTEGER PRIMARY KEY,
        SubcategoryName TEXT,
        ProductCategoryKey INTEGER,
        FOREIGN KEY (ProductCategoryKey) REFERENCES categories (ProductCategoryKey)
    );
    """)
    
    # 5. Products Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        ProductKey INTEGER PRIMARY KEY,
        ProductSubcategoryKey INTEGER,
        ProductSKU TEXT,
        ProductName TEXT,
        ModelName TEXT,
        ProductDescription TEXT,
        ProductColor TEXT,
        ProductSize TEXT,
        ProductStyle TEXT,
        ProductCost REAL,
        ProductPrice REAL,
        FOREIGN KEY (ProductSubcategoryKey) REFERENCES subcategories (ProductSubcategoryKey)
    );
    """)
    
    # 6. Territories Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS territories (
        SalesTerritoryKey INTEGER PRIMARY KEY,
        Region TEXT,
        Country TEXT,
        Continent TEXT
    );
    """)
    
    # 7. Returns Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS returns (
        ReturnDate TEXT,
        TerritoryKey INTEGER,
        ProductKey INTEGER,
        ReturnQuantity INTEGER,
        FOREIGN KEY (ReturnDate) REFERENCES calendar (Date),
        FOREIGN KEY (TerritoryKey) REFERENCES territories(SalesTerritoryKey),
        FOREIGN KEY (ProductKey) REFERENCES products(ProductKey)
    );
    """)
    
    # 8. Sales Table (Unified)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        OrderDate TEXT,
        StockDate TEXT,
        OrderNumber TEXT,
        ProductKey INTEGER,
        CustomerKey INTEGER,
        TerritoryKey INTEGER,
        OrderLineItem INTEGER,
        OrderQuantity INTEGER,
        PRIMARY KEY (OrderNumber, ProductKey, OrderLineItem),
        FOREIGN KEY (OrderDate) REFERENCES calendar (Date),
        FOREIGN KEY (StockDate) REFERENCES calendar (Date),
        FOREIGN KEY (ProductKey) REFERENCES products(ProductKey),
        FOREIGN KEY (CustomerKey) REFERENCES customers(CustomerKey),
        FOREIGN KEY (TerritoryKey) REFERENCES territories(SalesTerritoryKey)
    );
    """)
    
    conn.commit()
    print("Database schema successfully constructed!")

def drop_existing_tables(conn):
    """Helper to wipe existing tables to allow a clean run of the ETL pipeline."""
    cursor = conn.cursor()
    # Disable foreign keys temporarily to drop everything without conflicts
    cursor.execute("PRAGMA foreign_keys = OFF;")
    tables = ['sales', 'returns', 'products', 'subcategories', 'categories', 'customers', 'calendar', 'territories']
    for t in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {t};")
    conn.commit()
    print("Dropped any pre-existing tables to ensure a clean database setup.")

def load_csv_to_dataframe(filename, encoding='latin-1'):
    """Reads a CSV file, cleans whitespace from headers and string values, and returns a DataFrame."""
    path = os.path.join(DATASET_DIR, filename)
    df = pd.read_csv(path, encoding=encoding)
    df.columns = df.columns.str.strip()
    
    # Clean whitespace inside string columns
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()
        
    return df

def run_etl():
    print("=" * 60)
    print("STARTING ADVENTURE WORKS ETL PIPELINE INGESTION")
    print("=" * 60)
    start_time = time.time()
    
    # --- PHASE 1: LOAD ALL DATA INTO MEMORY ---
    print("\n[1/3] Loading CSV files into memory...")
    
    df_cal = load_csv_to_dataframe("AdventureWorks Calendar Lookup.csv")
    df_cust = load_csv_to_dataframe("AdventureWorks Customer Lookup.csv")
    df_cat = load_csv_to_dataframe("AdventureWorks Product Categories Lookup.csv")
    df_sub = load_csv_to_dataframe("AdventureWorks Product Subcategories Lookup.csv")
    df_prod = load_csv_to_dataframe("AdventureWorks Product Lookup.csv")
    df_terr = load_csv_to_dataframe("AdventureWorks Territory Lookup.csv")
    df_ret = load_csv_to_dataframe("AdventureWorks Returns Data.csv")
    
    sales_files = [
        "AdventureWorks Sales Data 2020.csv",
        "AdventureWorks Sales Data 2021.csv",
        "AdventureWorks Sales Data 2022.csv"
    ]
    sales_dfs = []
    for sf in sales_files:
        print(f"  Reading {sf}...")
        sales_dfs.append(load_csv_to_dataframe(sf))
    df_sales_all = pd.concat(sales_dfs, ignore_index=True)
    
    # --- PHASE 2: DATA CLEANING & STANDARDIZATION ---
    print("\n[2/3] Transforming and cleaning datasets...")
    
    # Standardize all dates
    df_cal = clean_and_standardize_dates(df_cal, ['Date'])
    df_cust = clean_and_standardize_dates(df_cust, ['BirthDate'])
    df_ret = clean_and_standardize_dates(df_ret, ['ReturnDate'])
    df_sales_all = clean_and_standardize_dates(df_sales_all, ['OrderDate', 'StockDate'])
    
    # --- DYNAMIC CALENDAR EXTENSION ---
    # Combine original calendar dates with all transaction and stock dates to cover late 2019
    print("  Extending Calendar date dimension to prevent foreign key violations...")
    original_dates = set(df_cal['Date'].dropna())
    sales_order_dates = set(df_sales_all['OrderDate'].dropna())
    sales_stock_dates = set(df_sales_all['StockDate'].dropna())
    returns_dates = set(df_ret['ReturnDate'].dropna())
    
    extended_date_set = original_dates.union(sales_order_dates, sales_stock_dates, returns_dates)
    df_cal_extended = pd.DataFrame(sorted(list(extended_date_set)), columns=['Date'])
    print(f"  -> Extended calendar from {len(df_cal)} to {len(df_cal_extended)} dates (min: {df_cal_extended['Date'].min()}, max: {df_cal_extended['Date'].max()})")
    
    # --- PHASE 3: DATABASE WRITING ---
    print("\n[3/3] Setting up SQLite and writing tables...")
    conn = sqlite3.connect(DB_PATH)
    
    # Drop and recreate schema
    drop_existing_tables(conn)
    build_database_schema(conn)
    
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Ingest Dimension Tables (must be loaded before Fact tables because of foreign keys)
    df_cat.to_sql('categories', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_cat)} rows into 'categories'")
    
    df_sub.to_sql('subcategories', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_sub)} rows into 'subcategories'")
    
    df_prod.to_sql('products', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_prod)} rows into 'products'")
    
    df_cust.to_sql('customers', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_cust)} rows into 'customers'")
    
    df_terr.to_sql('territories', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_terr)} rows into 'territories'")
    
    df_cal_extended.to_sql('calendar', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_cal_extended)} rows into 'calendar'")
    
    # Ingest Fact Tables
    df_ret.to_sql('returns', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_ret)} rows into 'returns'")
    
    df_sales_all.to_sql('sales', conn, if_exists='append', index=False)
    print(f"  -> Ingested {len(df_sales_all)} rows into unified 'sales'")
    
    # --- POST-INGESTION SYSTEM INTEGRITY VALIDATIONS ---
    print("\n" + "=" * 40)
    print("RUNNING SYSTEM INTEGRITY VALIDATIONS")
    print("=" * 40)
    
    cursor = conn.cursor()
    
    # Double-check for dangling foreign keys
    cursor.execute("PRAGMA foreign_key_check;")
    fk_violations = cursor.fetchall()
    if not fk_violations:
        print("  [OK] Integrity Check: No Foreign Key constraint violations detected!")
    else:
        print(f"  [FAIL] WARNING: Detected {len(fk_violations)} Foreign Key constraint violations!")
        print("  Details:", fk_violations)
        
    # Check table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    print("\nSummary of Database Table Sizes:")
    for t in sorted(tables):
        cursor.execute(f"SELECT COUNT(*) FROM {t};")
        count = cursor.fetchone()[0]
        print(f"  - Table: {t:<15} | Row Count: {count:,}")
        
    # Test a simple query to calculate high-level operational KPIs
    print("\nQuerying Sample KPIs:")
    cursor.execute("""
    SELECT 
        COUNT(DISTINCT s.OrderNumber) as TotalOrders,
        SUM(s.OrderQuantity) as TotalItemsSold,
        ROUND(SUM(s.OrderQuantity * p.ProductPrice), 2) as GrossRevenue
    FROM sales s
    JOIN products p ON s.ProductKey = p.ProductKey;
    """)
    orders, items, revenue = cursor.fetchone()
    print(f"  - Total Unique Orders : {orders:,}")
    print(f"  - Total Items Sold   : {items:,}")
    print(f"  - Gross Revenue      : ${revenue:,.2f}")
    
    conn.close()
    
    duration = time.time() - start_time
    print("=" * 60)
    print(f"ETL PROCESS COMPLETED IN {duration:.2f} SECONDS!")
    print("=" * 60)

if __name__ == "__main__":
    run_etl()
