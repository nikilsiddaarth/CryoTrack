import os
import sys
from dotenv import load_dotenv
import oracledb

load_dotenv()

def test_database_connection():
    user = os.getenv("ORACLE_USER", "COLDCHAIN")
    password = os.getenv("ORACLE_PASSWORD", "")
    host = os.getenv("ORACLE_HOST", "localhost")
    port = os.getenv("ORACLE_PORT", "1521")
    service = os.getenv("ORACLE_SERVICE", "XEPDB1")

    print("=" * 65)
    print(" CryoTrack -- Oracle Database Connectivity Test")
    print("=" * 65)
    print(f"Target Database Host   : {host}:{port}")
    print(f"Service Name           : {service}")
    print(f"Database User          : {user}")
    print(f"Password Provided      : {'[YES - Masked]' if password and password != 'YOUR_ORACLE_PASSWORD' else '[NO or default placeholder]'}")
    print("-" * 65)

    if not password or password == "YOUR_ORACLE_PASSWORD":
        print("ERROR: ORACLE_PASSWORD in .env is not set or still set to 'YOUR_ORACLE_PASSWORD'.")
        print("Please configure a valid password in .env before testing.")
        return False

    try:
        conn = oracledb.connect(
            user=user,
            password=password,
            host=host,
            port=int(port),
            service_name=service
        )
        print(">> Oracle Database connection successfully established!")
        print(f">> Server Version: {conn.version}")

        cursor = conn.cursor()
        
        # Verify tables
        cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
        tables = [row[0] for row in cursor.fetchall()]
        print(f">> Verified {len(tables)} tables owned by {user}:")
        
        total_records = 0
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            cnt = cursor.fetchone()[0]
            total_records += cnt
            print(f"   - {table:<28} : {cnt:>4} rows")
            
        print("-" * 65)
        print(f">> Total Sample Records Across Tables: {total_records}")
        print(">> Database status: HEALTHY and READY for CryoTrack platform.")
        print("=" * 65)

        cursor.close()
        conn.close()
        return True

    except oracledb.DatabaseError as e:
        error_obj, = e.args
        print(f"ERROR: Oracle Database Error {error_obj.code}: {error_obj.message.strip()}")
        print("-" * 65)
        if error_obj.code == 1017:
            print("Troubleshooting: Username/Password is invalid. Verify the credentials in .env.")
        elif error_obj.code in (12541, 12514, 12505):
            print("Troubleshooting: Could not connect to the Oracle listener or service.")
            print(f"Ensure Oracle XE listener is running on {host}:{port} and service {service} is active.")
        return False
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1)
