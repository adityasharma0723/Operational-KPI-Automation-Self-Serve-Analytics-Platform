-- schema.sql  — Single source of truth for the adventure_works.db schema.
-- Version: 1
-- Applied automatically by the ETL pipeline on first run or when version changes.

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
--  Schema Version Tracking
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL          -- ISO-8601 UTC timestamp
);

-- ─────────────────────────────────────────────
--  Dimension Tables  (must exist before fact tables)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS calendar (
    Date TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS products (
    ProductKey              INTEGER PRIMARY KEY,
    Product                 TEXT,
    Standard_Cost           REAL,
    Color                   TEXT,
    Subcategory             TEXT,
    Category                TEXT,
    Background_Color_Format TEXT,
    Font_Color_Format       TEXT
);

CREATE TABLE IF NOT EXISTS regions (
    SalesTerritoryKey INTEGER PRIMARY KEY,
    Region            TEXT,
    Country           TEXT,
    "Group"           TEXT
);

CREATE TABLE IF NOT EXISTS resellers (
    ResellerKey    INTEGER PRIMARY KEY,
    Business_Type  TEXT,
    Reseller       TEXT,
    City           TEXT,
    State_Province TEXT,
    Country_Region TEXT
);

CREATE TABLE IF NOT EXISTS salespeople (
    EmployeeKey INTEGER PRIMARY KEY,
    EmployeeID  INTEGER,
    Salesperson TEXT,
    Title       TEXT,
    UPN         TEXT
);

-- ─────────────────────────────────────────────
--  Bridge / Mapping Tables
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS salesperson_regions (
    EmployeeKey       INTEGER NOT NULL,
    SalesTerritoryKey INTEGER NOT NULL,
    PRIMARY KEY (EmployeeKey, SalesTerritoryKey),
    FOREIGN KEY (EmployeeKey)       REFERENCES salespeople (EmployeeKey),
    FOREIGN KEY (SalesTerritoryKey) REFERENCES regions     (SalesTerritoryKey)
);

-- ─────────────────────────────────────────────
--  Fact Tables
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS targets (
    EmployeeID  INTEGER NOT NULL,
    TargetMonth TEXT    NOT NULL,
    Target      REAL,
    FOREIGN KEY (TargetMonth) REFERENCES calendar (Date)
);

CREATE TABLE IF NOT EXISTS sales (
    SalesOrderNumber  TEXT    NOT NULL,
    OrderDate         TEXT,
    ProductKey        INTEGER NOT NULL,
    ResellerKey       INTEGER NOT NULL,
    EmployeeKey       INTEGER NOT NULL,
    SalesTerritoryKey INTEGER NOT NULL,
    Quantity          INTEGER,
    Unit_Price        REAL,
    Sales             REAL,
    Cost              REAL,
    FOREIGN KEY (OrderDate)         REFERENCES calendar    (Date),
    FOREIGN KEY (ProductKey)        REFERENCES products    (ProductKey),
    FOREIGN KEY (ResellerKey)       REFERENCES resellers   (ResellerKey),
    FOREIGN KEY (EmployeeKey)       REFERENCES salespeople (EmployeeKey),
    FOREIGN KEY (SalesTerritoryKey) REFERENCES regions     (SalesTerritoryKey)
);
