# CryoTrack   Pharmaceutical Cold-Chain Management System

## 1. Project Title

**CryoTrack: Pharmaceutical Cold-Chain Management System**

## 2. Problem Statement

Pharmaceutical products often require carefully controlled storage and transportation temperatures. Managing product batches, inventory, shipments, sensor readings, temperature alerts and delivery records across separate systems makes it difficult to maintain visibility and respond to cold-chain incidents. CryoTrack addresses this problem through a centralized, database-driven application for managing pharmaceutical inventory and monitoring cold-chain operations.

## 3. Abstract

CryoTrack is a pharmaceutical cold-chain management system developed to organize and monitor the storage and transportation of temperature-sensitive pharmaceutical products. It supports product and batch management, inventory tracking, shipment and route management, vehicle and driver records, IoT sensor readings, temperature alerts, cold-chain incidents and delivery tracking. The application uses Oracle Database 21c XE for operational data, Python Flask for backend services, HTML, CSS and JavaScript for the user interface, and SQLite for application authentication and access-control data. Role-based access control provides permissions appropriate to different operational responsibilities. The system brings key cold-chain workflows together in one application and improves visibility into pharmaceutical product movement and monitoring.

## 4. Team Members

| S. No. | Team Member Name | Register Number |
|---|---|---|
| 1 | NIKIL SIDDAARTH T | 25BCE5373 |
| 2 | PRAVEEN V | 25BCE5413 |
| 3 | SHAILESH K | 25BCE5707 |

## 5. Functional Features

- User authentication and role-based login.
- Role-based and permission-based access control.
- Pharmaceutical product and manufacturer management.
- Product batch management and quality-test records.
- Inventory management and inventory transaction tracking.
- Warehouse and storage-unit management.
- Shipment creation and shipment-item tracking.
- Route and route-stop management.
- Vehicle and driver management.
- IoT sensor registration and sensor-reading records.
- Temperature monitoring and temperature-alert management.
- Cold-chain incident recording and status updates.
- Delivery and healthcare-facility management.
- Dashboard statistics and operational reports.
- User profile and access-management features.

## 6. Technology Stack

| Component | Technology |
|---|---|
| DBMS | Oracle Database 21c XE |
| SQL Tool | Oracle SQL Developer / SQL*Plus |
| Backend | Python with Flask |
| Database Connectivity | Python oracledb |
| Authentication Database | SQLite |
| Frontend | HTML5, CSS3, JavaScript |
| Configuration | Python dotenv and environment variables |
| Code Editor | Visual Studio Code |
| Version Control | Git and GitHub |

## 7. Database Software and Setup Requirements

### Software Requirements

- Oracle Database 21c XE.
- Oracle SQL Developer or SQL*Plus.
- Python 3.
- Flask framework.
- Python Oracle Database driver (oracledb).
- Visual Studio Code.
- Git.

### Application Requirements

- Python virtual environment.
- Required Python packages listed in `requirements.txt`.
- Access to an Oracle database with the CryoTrack COLDCHAIN schema.
- Oracle connection details configured through environment variables.
- A modern web browser.

## 8. Application Setup Instructions

### Step 1: Clone the Repository

Replace the placeholder with the actual GitHub repository URL after publishing the project.

```bash
git clone <https://github.com/nikilsiddaarth/CryoTrack>
cd cold-chain-monitor
```

### Step 2: Create a Virtual Environment

```powershell
python -m venv .venv
```

### Step 3: Activate the Virtual Environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 4: Install Dependencies

```powershell
pip install -r requirements.txt
```

### Step 5: Configure Environment Variables

Create a local `.env` file using `.env.example` as a reference. Configure the Oracle connection and Flask settings.

Example configuration:

```env
ORACLE_USER=COLDCHAIN
ORACLE_PASSWORD=YOUR_ORACLE_PASSWORD
ORACLE_HOST=localhost
ORACLE_PORT=1521
ORACLE_SERVICE=XEPDB1
SECRET_KEY=REPLACE_WITH_A_RANDOM_SECRET_KEY
FLASK_PORT=5000
FLASK_DEBUG=False
```

Use your own Oracle password and a securely generated Flask secret key. Do not upload `.env` or publish passwords and private credentials to GitHub.

### Step 6: Configure the Oracle Database

1. Start the Oracle Database service.
2. Open Oracle SQL Developer or SQL*Plus.
3. Connect to the intended Oracle instance using the `XEPDB1` service.
4. Use the `COLDCHAIN` schema.
5. For a fresh database, execute the schema script:

```sql
@database/schema.sql
```

The project schema contains 23 tables and their defined relationships and constraints. Do not recreate the schema on top of an existing populated database.

### Step 7: Load Sample Data

For a fresh schema only, review the demonstration data script and execute it after creating the schema:

```sql
@database/sample_data.sql
```

Check that the sample IDs and records do not already exist before execution. Do not run this script against the existing populated project database without reviewing its effects.

### Step 8: Initialize an Application User

The project includes `create_user.py` for user creation and administration workflows. Follow its prompts and the application's access-control rules when creating an initial user.

### Step 9: Run the Application

From the project root, with the virtual environment activated:

```powershell
python app.py
```

Open the local address displayed in the terminal using a web browser. The default configured port is 5000.

## 9. Database Tables and Relationships

The Oracle `COLDCHAIN` schema contains 23 tables.

| Category | Tables |
|---|---|
| Product and Manufacturing | MANUFACTURER, PHARMACEUTICAL_PRODUCT |
| Batch and Quality | PRODUCT_BATCH, QUALITY_TEST |
| Storage and Inventory | STORAGE_CONDITION, WAREHOUSE, STORAGE_UNIT, INVENTORY, INVENTORY_TRANSACTION |
| Shipment and Routing | SHIPMENT, SHIPMENT_ITEM, ROUTE, ROUTE_STOP |
| Fleet Management | VEHICLE, DRIVER, VEHICLE_ASSIGNMENT |
| IoT and Temperature Monitoring | IOT_SENSOR, SENSOR_READING, TEMPERATURE_ALERT |
| Incident Management | COLD_CHAIN_INCIDENT |
| Distribution and Delivery | DISTRIBUTION_CENTER, HEALTHCARE_FACILITY, DELIVERY |

Primary keys uniquely identify records in individual tables. Foreign keys connect related tables and help maintain referential integrity.

The `SHIPMENT_ITEM` table uses a composite primary key consisting of `SHIPMENT_ID` and `BATCH_ID`. Some reference fields in the schema are polymorphic references rather than ordinary foreign-key relationships.

Application authentication and authorization data are maintained separately from the Oracle operational schema using SQLite at `instance/cryotrack_auth.sqlite`.

## 10. Sample Data and SQL Queries

The `database/` directory contains the SQL scripts used by the project.

- `schema.sql` – Creates the Oracle database tables and relationships.
- `sample_data.sql` – Contains demonstration records intended for a fresh schema.
- `queries.sql` – Contains example SQL queries for retrieving and analyzing CryoTrack data.

The query examples cover filtering, joins, grouping, aggregate functions, subqueries and operational data retrieval.

Execute the scripts using the `COLDCHAIN` schema after confirming that the required tables and records are available.

## 11. Screenshots and Implemented Features

The `screenshots/` directory contains screenshots demonstrating the application and database.

| Screenshot | Description |
|---|---|
| `01_login.png` | Login page |
| `02_dashboard.png` | Main dashboard |
| `03_inventory.png` | Inventory management |
| `04_shipments.png` | Shipment management |
| `05_temperature.png` | Temperature monitoring |
| `06_alerts.png` | Temperature alerts |
| `07_products.png` | Product management |
| `08_database.png` | Database evidence |

These screenshots provide visual evidence of the application's interfaces and database implementation.

## 12. Testing Instructions

The `tests/` directory is reserved for project testing materials. The project also includes `test_db.py` for database connectivity checks.

Suggested areas for verification include:

- Application startup and login.
- Oracle database connectivity.
- Product and batch retrieval and insertion.
- Inventory retrieval and transaction handling.
- Shipment and shipment-item operations.
- Sensor-reading and temperature-alert operations.
- Role-based access restrictions.
- Incident and delivery workflows.
- Primary-key and foreign-key constraint validation.

Record actual test inputs, outputs and outcomes when executing these checks. The presence of a test script or suggested test scenario does not itself prove that a test has passed.

## 13. Known Limitations

- Oracle Database must be running and reachable for Oracle-backed application features.
- External IoT hardware and live sensor integrations depend on the configured data source.
- Email verification and Google OAuth require their respective external service credentials and configuration.
- SMTP and OAuth settings are optional and must be configured before those integrations can be used.
- Demonstration sample data is intended for a fresh schema and should not be blindly loaded into an existing populated database.

## 14. Project Presentation

The project presentation is available in the `presentation/` directory.

**File:** `CryoTrack_Presentation.pptx`

## 15. YouTube Demonstration Link

YouTube Demo: **[https://drive.google.com/file/d/1zb2uak-x952_XGyIT6BLveHkQSbdGUjc/view?usp=sharing]**

---

**CryoTrack – Pharmaceutical Cold-Chain Management System**

Developed as a DBMS project by:

- NIKIL SIDDAARTH T – 25BCE5373
- PRAVEEN V – 25BCE5413
- SHAILESH K – 25BCE5707