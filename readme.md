# CryoTrack
### Pharmaceutical Cold-Chain Monitoring and Logistics Management System

CryoTrack is a web-based pharmaceutical logistics management system designed to monitor pharmaceutical products, batches, inventory, shipments, cold-chain conditions, and delivery operations.

## Technology Stack
- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python Flask
- **Database:** Oracle Database XE
- **Database Connectivity:** Python `oracledb`
- **Authentication:** Flask authentication with role-based access control

## Key Modules
1. Command Center
2. Products & Quality
3. Shipments & Fleet
4. Cold-Chain Monitoring
5. Inventory & Warehousing
6. Incidents & Compliance
7. Deliveries & Distribution
8. Reports & Analytics
9. User & Access Management
10. Settings

## Database
The application uses an Oracle database with the `COLDCHAIN` schema.

The database contains 23 relational tables covering pharmaceutical products, production batches, inventory, shipments, vehicles, sensors, temperature readings, incidents, and deliveries.

## Project Setup

1. Clone this repository.
2. Create and activate a Python virtual environment.
3. Install dependencies:

   `pip install -r requirements.txt`

4. Create a `.env` file using `.env.example` as a reference.
5. Configure your Oracle database connection details.
6. Start the application:

   `python app.py`

## Environment Configuration
Never commit `.env` or actual database credentials. Use `.env.example` as a configuration template.

## Team
- Nikil Siddaarth T
- Praveen V
- Shailesh K

**Institution:** VIT Chennai  
**Course:** Database Management Systems