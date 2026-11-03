# CryoTrack Tests

These tests are designed for the CryoTrack Flask + Oracle XE project.

## Test files

- `test_db_connection.py` checks a real Oracle connection by executing `SELECT 1 FROM DUAL`. It is skipped automatically when `ORACLE_PASSWORD` is not configured.
- `test_auth.py` checks the role and permission configuration used by CryoTrack's role-based access control.
- `test_api.py` checks that important API routes are registered and tests response serialization, row conversion, and pagination helpers without changing database records.

## Run the tests

Open PowerShell in the CryoTrack project root (the folder containing `app.py`) and run:

```powershell
python -m unittest discover -s test -v
```

If dependencies are not installed yet:

```powershell
pip install -r requirements.txt
```

For the Oracle connection test, configure the correct Oracle settings in your local `.env` file first. Do not put `.env`, database passwords, SQLite files, or virtual-environment folders in Git.

## Important

The API helper tests do not insert, update, or delete Oracle records. The Oracle connectivity test is an integration test and requires a running Oracle listener and valid `COLDCHAIN` credentials.
