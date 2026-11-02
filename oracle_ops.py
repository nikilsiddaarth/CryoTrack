"""CryoTrack — Reusable Oracle Database Helpers, Validated Write Operations & Analytical Queries."""
from datetime import date, datetime
from decimal import Decimal
import re


DATE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(val, field_label, required=True):
    """Parse YYYY-MM-DD string into Python date object safely."""
    s = (str(val).strip() if val is not None else "")
    if not s:
        if required:
            raise ValueError(f"{field_label} is required.")
        return None
    s_short = s[:10]
    if not DATE_ISO_RE.match(s_short):
        raise ValueError(f"{field_label} must use YYYY-MM-DD format.")
    try:
        return datetime.strptime(s_short, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_label} is not a valid calendar date.") from exc


def parse_number(val, field_label, required=True, allow_float=True, min_val=None, max_val=None):
    """Parse integer or float safely with bounds checking."""
    if val is None or str(val).strip() == "":
        if required:
            raise ValueError(f"{field_label} is required.")
        return None
    try:
        num = float(val) if allow_float else int(val)
    except (ValueError, TypeError) as exc:
        kind = "number" if allow_float else "whole integer"
        raise ValueError(f"{field_label} must be a valid {kind}.") from exc
    if min_val is not None and num < min_val:
        raise ValueError(f"{field_label} must be at least {min_val}.")
    if max_val is not None and num > max_val:
        raise ValueError(f"{field_label} must not exceed {max_val}.")
    return num


def parse_text(val, field_label, max_len, required=True):
    """Validate and trim text string against Oracle VARCHAR2 column length."""
    s = (str(val).strip() if val is not None else "")
    if not s:
        if required:
            raise ValueError(f"{field_label} is required.")
        return None
    if len(s) > max_len:
        raise ValueError(f"{field_label} must be {max_len} characters or fewer.")
    return s


# Allowlisted schema metadata for safe PK allocation and FK / Uniqueness checks
ALLOWED_PK_COLUMNS = {
    "MANUFACTURER": "MANUFACTURER_ID",
    "PHARMACEUTICAL_PRODUCT": "PRODUCT_ID",
    "STORAGE_CONDITION": "CONDITION_ID",
    "PRODUCT_BATCH": "BATCH_ID",
    "QUALITY_TEST": "TEST_ID",
    "WAREHOUSE": "WAREHOUSE_ID",
    "DISTRIBUTION_CENTER": "DISTRIBUTION_CENTER_ID",
    "STORAGE_UNIT": "STORAGE_UNIT_ID",
    "INVENTORY": "INVENTORY_ID",
    "INVENTORY_TRANSACTION": "TRANSACTION_ID",
    "ROUTE": "ROUTE_ID",
    "ROUTE_STOP": "STOP_ID",
    "VEHICLE": "VEHICLE_ID",
    "DRIVER": "DRIVER_ID",
    "VEHICLE_ASSIGNMENT": "ASSIGNMENT_ID",
    "SHIPMENT": "SHIPMENT_ID",
    "IOT_SENSOR": "SENSOR_ID",
    "SENSOR_READING": "READING_ID",
    "TEMPERATURE_ALERT": "ALERT_ID",
    "COLD_CHAIN_INCIDENT": "INCIDENT_ID",
    "HEALTHCARE_FACILITY": "FACILITY_ID",
    "DELIVERY": "DELIVERY_ID",
}

ALLOWED_UNIQUE_CHECKS = {
    ("MANUFACTURER", "LICENSE_NUMBER"),
    ("PRODUCT_BATCH", "BATCH_NUMBER"),
    ("STORAGE_CONDITION", "PRODUCT_ID"),
    ("IOT_SENSOR", "SERIAL_NUMBER"),
    ("VEHICLE", "REGISTRATION_NUMBER"),
    ("DRIVER", "LICENSE_NUMBER"),
    ("HEALTHCARE_FACILITY", "LICENSE_NUMBER"),
    ("COLD_CHAIN_INCIDENT", "ALERT_ID"),
    ("DELIVERY", "SHIPMENT_ID"),
}


def next_pk(cursor, table_name):
    """Allocate next numeric primary key using explicit allowlist validation."""
    if table_name not in ALLOWED_PK_COLUMNS:
        raise ValueError("Unsupported entity identifier.")
    pk_col = ALLOWED_PK_COLUMNS[table_name]
    cursor.execute(f"SELECT NVL(MAX({pk_col}), 0) + 1 FROM {table_name}")
    return int(cursor.fetchone()[0])


def ensure_fk_exists(cursor, table_name, pk_val, label):
    """Verify foreign key parent record exists in Oracle."""
    if table_name not in ALLOWED_PK_COLUMNS:
        raise ValueError("Unsupported foreign key entity.")
    pk_col = ALLOWED_PK_COLUMNS[table_name]
    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {pk_col} = :pk_id", {"pk_id": pk_val})
    if cursor.fetchone()[0] == 0:
        raise ValueError(f"Selected {label} (#{pk_val}) does not exist.")


def ensure_unique_value(cursor, table_name, column_name, value, label):
    """Pre-check Oracle UNIQUE constraint using allowlisted table and column."""
    if value is None:
        return
    if (table_name, column_name) not in ALLOWED_UNIQUE_CHECKS:
        raise ValueError("Unsupported uniqueness check.")
    if isinstance(value, str):
        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE UPPER({column_name}) = UPPER(:val)",
            {"val": value.strip()},
        )
    else:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = :val",
            {"val": value},
        )
    if cursor.fetchone()[0] > 0:
        raise ValueError(f"A record with this {label} already exists.")


def fetch_lookups(cursor, rows_to_dicts):
    """Fetch reference options for validated foreign-key dropdowns across modules."""
    cursor.execute("SELECT MANUFACTURER_ID, MANUFACTURER_NAME, COUNTRY FROM MANUFACTURER ORDER BY MANUFACTURER_NAME")
    manufacturers = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT p.PRODUCT_ID, p.PRODUCT_NAME, p.STORAGE_CATEGORY,
               sc.MINIMUM_TEMPERATURE, sc.MAXIMUM_TEMPERATURE
        FROM PHARMACEUTICAL_PRODUCT p
        LEFT JOIN STORAGE_CONDITION sc ON p.PRODUCT_ID = sc.PRODUCT_ID
        ORDER BY p.PRODUCT_NAME
    """)
    products = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT b.BATCH_ID, b.BATCH_NUMBER, b.PRODUCT_ID, p.PRODUCT_NAME,
               b.BATCH_STATUS, b.QUALITY_STATUS, b.EXPIRY_DATE
        FROM PRODUCT_BATCH b
        JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
        ORDER BY b.BATCH_ID DESC
    """)
    batches = rows_to_dicts(cursor)

    cursor.execute("SELECT WAREHOUSE_ID, WAREHOUSE_NAME, CITY FROM WAREHOUSE ORDER BY WAREHOUSE_NAME")
    warehouses = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT su.STORAGE_UNIT_ID, su.UNIT_NAME, su.UNIT_TYPE, w.WAREHOUSE_NAME
        FROM STORAGE_UNIT su
        LEFT JOIN WAREHOUSE w ON su.WAREHOUSE_ID = w.WAREHOUSE_ID
        ORDER BY w.WAREHOUSE_NAME, su.UNIT_NAME
    """)
    storage_units = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT inv.INVENTORY_ID, inv.QUANTITY_AVAILABLE, inv.QUANTITY_RESERVED,
               b.BATCH_NUMBER, p.PRODUCT_NAME, su.UNIT_NAME, w.WAREHOUSE_NAME
        FROM INVENTORY inv
        JOIN PRODUCT_BATCH b ON inv.BATCH_ID = b.BATCH_ID
        JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
        JOIN STORAGE_UNIT su ON inv.STORAGE_UNIT_ID = su.STORAGE_UNIT_ID
        JOIN WAREHOUSE w ON su.WAREHOUSE_ID = w.WAREHOUSE_ID
        ORDER BY inv.INVENTORY_ID DESC
    """)
    inventory_items = rows_to_dicts(cursor)

    cursor.execute("SELECT ROUTE_ID, ORIGIN, DESTINATION, TOTAL_DISTANCE FROM ROUTE ORDER BY ROUTE_ID")
    routes = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT VEHICLE_ID, REGISTRATION_NUMBER, VEHICLE_TYPE, REFRIGERATION_TYPE, VEHICLE_STATUS
        FROM VEHICLE
        ORDER BY REGISTRATION_NUMBER
    """)
    vehicles = rows_to_dicts(cursor)

    cursor.execute("SELECT DRIVER_ID, DRIVER_NAME, LICENSE_NUMBER, EMPLOYMENT_STATUS FROM DRIVER ORDER BY DRIVER_NAME")
    drivers = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT s.SHIPMENT_ID, s.SHIPMENT_STATUS, r.ORIGIN, r.DESTINATION,
               CASE WHEN d.DELIVERY_ID IS NULL THEN 0 ELSE 1 END AS HAS_DELIVERY
        FROM SHIPMENT s
        LEFT JOIN ROUTE r ON s.ROUTE_ID = r.ROUTE_ID
        LEFT JOIN DELIVERY d ON s.SHIPMENT_ID = d.SHIPMENT_ID
        ORDER BY s.SHIPMENT_ID DESC
    """)
    shipments = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT s.SENSOR_ID, s.SERIAL_NUMBER, s.SENSOR_TYPE, v.REGISTRATION_NUMBER,
               v.TEMPERATURE_MIN, v.TEMPERATURE_MAX
        FROM IOT_SENSOR s
        LEFT JOIN VEHICLE v ON s.VEHICLE_ID = v.VEHICLE_ID
        ORDER BY s.SENSOR_ID
    """)
    sensors = rows_to_dicts(cursor)

    cursor.execute("""
        SELECT ta.ALERT_ID, ta.ALERT_TYPE, ta.SEVERITY, ta.RECORDED_TEMPERATURE,
               ta.SHIPMENT_ID,
               CASE WHEN cci.INCIDENT_ID IS NULL THEN 0 ELSE 1 END AS HAS_INCIDENT
        FROM TEMPERATURE_ALERT ta
        LEFT JOIN COLD_CHAIN_INCIDENT cci ON ta.ALERT_ID = cci.ALERT_ID
        ORDER BY ta.ALERT_ID DESC
    """)
    alerts = rows_to_dicts(cursor)

    cursor.execute("SELECT FACILITY_ID, FACILITY_NAME, CITY, STATE FROM HEALTHCARE_FACILITY ORDER BY FACILITY_NAME")
    facilities = rows_to_dicts(cursor)

    return {
        "manufacturers": manufacturers,
        "products": products,
        "batches": batches,
        "warehouses": warehouses,
        "storage_units": storage_units,
        "inventory_items": inventory_items,
        "routes": routes,
        "vehicles": vehicles,
        "drivers": drivers,
        "shipments": shipments,
        "sensors": sensors,
        "alerts": alerts,
        "facilities": facilities,
    }


def fetch_reports_overview(cursor, rows_to_dicts, expiry_window_days=None):
    """Execute real Oracle analytical queries across all operational domains."""
    # 1. Shipment status & priority summary
    cursor.execute("""
        SELECT s.SHIPMENT_STATUS,
               s.PRIORITY_LEVEL,
               COUNT(*) AS SHIPMENT_COUNT,
               ROUND(NVL(AVG(s.TOTAL_WEIGHT), 0), 1) AS AVG_WEIGHT_KG,
               ROUND(NVL(SUM(r.TOTAL_DISTANCE), 0), 1) AS TOTAL_DISTANCE_KM
        FROM SHIPMENT s
        LEFT JOIN ROUTE r ON s.ROUTE_ID = r.ROUTE_ID
        GROUP BY s.SHIPMENT_STATUS, s.PRIORITY_LEVEL
        ORDER BY s.SHIPMENT_STATUS, s.PRIORITY_LEVEL
    """)
    shipment_summary = rows_to_dicts(cursor)

    # 2. Batch expiry report
    exp_sql = """
        SELECT b.BATCH_ID, b.BATCH_NUMBER, p.PRODUCT_NAME, p.STORAGE_CATEGORY,
               m.MANUFACTURER_NAME, b.MANUFACTURING_DATE, b.EXPIRY_DATE,
               b.QUANTITY_PRODUCED, b.BATCH_STATUS, b.QUALITY_STATUS,
               TRUNC(b.EXPIRY_DATE - SYSDATE) AS DAYS_TO_EXPIRY,
               CASE
                   WHEN b.EXPIRY_DATE < TRUNC(SYSDATE) THEN 'Expired'
                   WHEN b.EXPIRY_DATE <= TRUNC(SYSDATE) + 90 THEN 'Critical (< 90 Days)'
                   WHEN b.EXPIRY_DATE <= TRUNC(SYSDATE) + 180 THEN 'Near Expiry (90-180 Days)'
                   ELSE 'Healthy (> 180 Days)'
               END AS EXPIRY_RISK
        FROM PRODUCT_BATCH b
        JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
        LEFT JOIN MANUFACTURER m ON p.MANUFACTURER_ID = m.MANUFACTURER_ID
        WHERE 1=1
    """
    exp_params = {}
    if expiry_window_days is not None:
        exp_sql += " AND b.EXPIRY_DATE <= TRUNC(SYSDATE) + :days"
        exp_params["days"] = int(expiry_window_days)
    exp_sql += " ORDER BY b.EXPIRY_DATE ASC, b.BATCH_ID ASC"
    cursor.execute(exp_sql, exp_params)
    batch_expiry = rows_to_dicts(cursor)

    # 3. Warehouse inventory availability
    cursor.execute("""
        SELECT w.WAREHOUSE_ID, w.WAREHOUSE_NAME, w.CITY, w.STATE, w.CAPACITY AS WAREHOUSE_CAPACITY,
               COUNT(DISTINCT su.STORAGE_UNIT_ID) AS STORAGE_UNITS,
               COUNT(inv.INVENTORY_ID) AS STOCK_LOTS,
               NVL(SUM(inv.QUANTITY_AVAILABLE), 0) AS AVAILABLE_UNITS,
               NVL(SUM(inv.QUANTITY_RESERVED), 0) AS RESERVED_UNITS,
               NVL(SUM(inv.QUANTITY_AVAILABLE + inv.QUANTITY_RESERVED), 0) AS TOTAL_STOCK_UNITS
        FROM WAREHOUSE w
        LEFT JOIN STORAGE_UNIT su ON w.WAREHOUSE_ID = su.WAREHOUSE_ID
        LEFT JOIN INVENTORY inv ON su.STORAGE_UNIT_ID = inv.STORAGE_UNIT_ID
        GROUP BY w.WAREHOUSE_ID, w.WAREHOUSE_NAME, w.CITY, w.STATE, w.CAPACITY
        ORDER BY TOTAL_STOCK_UNITS DESC, w.WAREHOUSE_NAME ASC
    """)
    inventory_availability = rows_to_dicts(cursor)

    # 4. Temperature excursion summary
    cursor.execute("""
        SELECT UPPER(ta.SEVERITY) AS SEVERITY_GROUP,
               UPPER(ta.ALERT_STATUS) AS STATUS_GROUP,
               COUNT(*) AS ALERT_COUNT,
               ROUND(AVG(ta.RECORDED_TEMPERATURE), 2) AS AVG_RECORDED_TEMP,
               ROUND(MAX(ABS(
                   CASE
                       WHEN ta.RECORDED_TEMPERATURE > ta.EXPECTED_MAX THEN ta.RECORDED_TEMPERATURE - ta.EXPECTED_MAX
                       WHEN ta.RECORDED_TEMPERATURE < ta.EXPECTED_MIN THEN ta.EXPECTED_MIN - ta.RECORDED_TEMPERATURE
                       ELSE 0
                   END
               )), 2) AS MAX_DEVIATION_C
        FROM TEMPERATURE_ALERT ta
        GROUP BY UPPER(ta.SEVERITY), UPPER(ta.ALERT_STATUS)
        ORDER BY ALERT_COUNT DESC
    """)
    excursion_summary = rows_to_dicts(cursor)

    # 5. Incident resolution metrics
    cursor.execute("""
        SELECT cci.INCIDENT_TYPE,
               cci.SEVERITY,
               cci.RESOLUTION_STATUS,
               COUNT(*) AS INCIDENT_COUNT,
               ROUND(AVG(
                   CASE
                       WHEN cci.RESOLUTION_DATE IS NOT NULL AND cci.INCIDENT_DATE IS NOT NULL
                       THEN cci.RESOLUTION_DATE - cci.INCIDENT_DATE
                       ELSE NULL
                   END
               ), 1) AS AVG_RESOLUTION_DAYS
        FROM COLD_CHAIN_INCIDENT cci
        GROUP BY cci.INCIDENT_TYPE, cci.SEVERITY, cci.RESOLUTION_STATUS
        ORDER BY INCIDENT_COUNT DESC
    """)
    incident_resolution = rows_to_dicts(cursor)

    # 6. Delivery performance & damaged quantities by facility
    cursor.execute("""
        SELECT hf.FACILITY_ID, hf.FACILITY_NAME, hf.FACILITY_TYPE, hf.CITY, hf.STATE,
               COUNT(d.DELIVERY_ID) AS DELIVERIES_COUNT,
               NVL(SUM(d.QUANTITY_RECEIVED), 0) AS TOTAL_RECEIVED,
               NVL(SUM(d.QUANTITY_DAMAGED), 0) AS TOTAL_DAMAGED,
               CASE
                   WHEN NVL(SUM(d.QUANTITY_RECEIVED + d.QUANTITY_DAMAGED), 0) > 0
                   THEN ROUND((NVL(SUM(d.QUANTITY_DAMAGED), 0) / SUM(d.QUANTITY_RECEIVED + d.QUANTITY_DAMAGED)) * 100, 2)
                   ELSE 0
               END AS DAMAGE_RATE_PCT
        FROM HEALTHCARE_FACILITY hf
        JOIN DELIVERY d ON hf.FACILITY_ID = d.FACILITY_ID
        GROUP BY hf.FACILITY_ID, hf.FACILITY_NAME, hf.FACILITY_TYPE, hf.CITY, hf.STATE
        ORDER BY TOTAL_RECEIVED DESC
    """)
    delivery_performance = rows_to_dicts(cursor)

    return {
        "shipment_summary": shipment_summary,
        "batch_expiry": batch_expiry,
        "inventory_availability": inventory_availability,
        "excursion_summary": excursion_summary,
        "incident_resolution": incident_resolution,
        "delivery_performance": delivery_performance,
    }
