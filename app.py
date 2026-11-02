"""CryoTrack — Pharmaceutical Cold-Chain Intelligence Platform (Flask + Oracle XE Backend)."""
import os
import io
import csv
import json
import secrets
import urllib.parse
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta
from decimal import Decimal
from flask import (
    Flask,
    Response,
    render_template,
    jsonify,
    request,
    session,
    redirect,
    url_for,
)
from dotenv import load_dotenv
import oracledb

from auth import (
    authenticate_user,
    register_with_invitation,
    authenticate_or_provision_google_user,
    create_or_update_user,
    get_current_session_user,
    list_users_safe,
    admin_update_user,
    approve_user_account,
    issue_invitation,
    revoke_invitation,
    update_own_profile,
    change_own_password,
    generate_csrf_token,
    validate_csrf_token,
    verify_request_csrf,
    login_required,
    permission_required,
    role_required,
    get_auth_db,
    log_audit_event,
)
from rbac import (
    DEPARTMENTS,
    VALID_ROLES,
    ROLE_DEFAULT_DEPARTMENT,
    PRIVILEGED_ROLES,
    PRIVILEGED_PERMISSIONS,
    RECORD_SCOPE_TYPES,
    PERMISSION_CATALOG,
    ALL_PERMISSION_KEYS,
    DEFAULT_ROLE_PERMISSIONS,
    normalize_role_name,
    is_privileged_assignment,
    compute_allowed_tabs,
    resolve_landing_tab,
    sanitize_records_for_user,
    has_global_record_scope,
    build_shipment_scope_sql,
    build_warehouse_scope_sql,
    build_vehicle_scope_sql,
    build_route_scope_sql,
    build_facility_scope_sql,
    build_delivery_scope_sql,
    build_alert_scope_sql,
    check_shipment_in_scope,
    check_warehouse_in_scope,
    check_facility_in_scope,
    check_vehicle_in_scope,
)
from oracle_ops import (
    parse_iso_date,
    parse_number,
    parse_text,
    next_pk,
    ensure_fk_exists,
    ensure_unique_value,
    fetch_lookups,
    fetch_reports_overview,
)

# Load environment configuration from .env
load_dotenv()

app = Flask(__name__)

# Session & Cookie Security Configuration
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "yes")

# Oracle Database Configuration (never expose password!)
ORACLE_USER = os.getenv("ORACLE_USER", "COLDCHAIN")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "XEPDB1")

# Google OAuth 2.0 / OpenID Connect Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "").strip()


def is_google_oauth_configured():
    """Return True only when genuine Google OAuth client credentials are provided."""
    placeholders = {"", "your_google_client_id", "your-client-id", "changeme"}
    return (
        GOOGLE_CLIENT_ID.lower() not in placeholders
        and GOOGLE_CLIENT_SECRET.lower() not in placeholders
    )


def resolve_google_redirect_uri():
    """Resolve and validate the Google OAuth callback URI against current host allowlist."""
    candidate = GOOGLE_REDIRECT_URI or url_for("google_callback", _external=True)
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid OAuth redirect URI configuration.")
    if not parsed.path.endswith("/auth/google/callback"):
        raise ValueError("OAuth redirect URI path must end with /auth/google/callback.")
    return candidate


def get_db_connection():
    """Establish and return an Oracle Database connection."""
    if not ORACLE_PASSWORD or ORACLE_PASSWORD == "YOUR_ORACLE_PASSWORD":
        raise RuntimeError("Oracle database credentials are not configured in .env.")

    return oracledb.connect(
        user=ORACLE_USER,
        password=ORACLE_PASSWORD,
        host=ORACLE_HOST,
        port=int(ORACLE_PORT),
        service_name=ORACLE_SERVICE,
    )


def serialize_value(val):
    """Serialize Oracle & Python types cleanly into JSON primitives."""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val) if val % 1 else int(val)
    return val


def rows_to_dicts(cursor):
    """Convert cursor result rows into a list of lowercased dictionaries."""
    if not cursor.description:
        return []
    columns = [col[0].lower() for col in cursor.description]
    results = []
    for row in cursor.fetchall():
        record = {}
        for col_name, val in zip(columns, row):
            record[col_name] = serialize_value(val)
        results.append(record)
    return results


def maybe_paginate(items):
    """Support optional server-side pagination when ?paginate=1 is requested."""
    if request.args.get("paginate") == "1":
        try:
            page = max(1, int(request.args.get("page", 1)))
            raw_size = request.args.get("page_size") or request.args.get("per_page") or 15
            page_size = min(200, max(5, int(raw_size)))
        except ValueError:
            page, page_size = 1, 15
        total = len(items)
        start = (page - 1) * page_size
        return jsonify({
            "items": items[start : start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        })
    return jsonify(items)


def safe_api_error(exc, context_label="Database operation", status_code=500):
    """Log internal error server-side without leaking DB credentials or stack traces to clients."""
    if isinstance(exc, ValueError):
        return jsonify({"error": "Validation Error", "message": str(exc)}), 400
    app.logger.error("CryoTrack error in %s: %s", context_label, type(exc).__name__)
    if isinstance(exc, oracledb.IntegrityError):
        return jsonify({
            "error": "Constraint Violation",
            "message": "The submitted record conflicts with an existing unique identifier or foreign-key reference."
        }), 409
    return jsonify({
        "error": "Server Error",
        "message": f"{context_label} could not be completed at this time."
    }), status_code


# =============================================================================
# Authentication, Registration & Google OAuth 2.0 / OIDC Routes
# =============================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    """CryoTrack server-side email & password sign-in."""
    if get_current_session_user():
        return redirect(url_for("index"))

    error = None
    success = None
    oauth_notice = None

    if request.args.get("registered") == "1":
        success = "Account created successfully. Please sign in with your credentials below."
    elif request.args.get("pending_approval") == "1":
        success = "Account created and pending administrator approval. An authorized reviewer must approve your account before access is granted."
    elif request.args.get("logged_out") == "1":
        success = "You have been securely signed out of CryoTrack."

    notice_code = request.args.get("oauth_notice")
    if notice_code == "unconfigured":
        oauth_notice = (
            "Google Sign-In requires OAuth 2.0 Client credentials in .env "
            "(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI). "
            "Sign in with your CryoTrack email and password, or configure Google Cloud OAuth credentials."
        )

    if request.method == "POST":
        csrf_token = request.form.get("csrf_token", "")
        if not validate_csrf_token(csrf_token):
            return render_template(
                "login.html",
                error="Security session validation failed. Please try signing in again.",
                csrf_token=generate_csrf_token(),
                google_oauth_configured=is_google_oauth_configured(),
            ), 403

        email_or_id = request.form.get("email", "").strip() or request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user, auth_err = authenticate_user(email_or_id, password)
        if user:
            session.clear()
            session["user"] = user
            session.permanent = True
            generate_csrf_token()
            return redirect(url_for("index"))

        return render_template(
            "login.html",
            error=auth_err or "Invalid email address or password.",
            submitted_email=email_or_id,
            csrf_token=generate_csrf_token(),
            google_oauth_configured=is_google_oauth_configured(),
        ), 401

    return render_template(
        "login.html",
        error=error,
        success=success,
        oauth_notice=oauth_notice,
        csrf_token=generate_csrf_token(),
        google_oauth_configured=is_google_oauth_configured(),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    """Invitation-bound account creation workflow deriving role & department from server record."""
    if get_current_session_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        csrf_token = request.form.get("csrf_token", "")
        if not validate_csrf_token(csrf_token):
            return render_template(
                "register.html",
                error="Security token expired. Please submit the form again.",
                csrf_token=generate_csrf_token(),
                google_oauth_configured=is_google_oauth_configured(),
            ), 403

        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        invitation_key = request.form.get("invitation_key", "").strip()

        ok, result = register_with_invitation(
            full_name=full_name,
            email=email,
            password=password,
            confirm_password=confirm_password,
            raw_invitation_key=invitation_key,
            ip_address=request.remote_addr,
        )
        if ok:
            if result.get("status") == "Pending Approval":
                return redirect(url_for("login", pending_approval="1"))
            return redirect(url_for("login", registered="1"))

        return render_template(
            "register.html",
            error=result,
            submitted_name=full_name,
            submitted_email=email,
            submitted_key=invitation_key,
            csrf_token=generate_csrf_token(),
            google_oauth_configured=is_google_oauth_configured(),
        ), 400

    return render_template(
        "register.html",
        csrf_token=generate_csrf_token(),
        google_oauth_configured=is_google_oauth_configured(),
    )


@app.route("/auth/google")
def google_login():
    """Initiate genuine Google OAuth 2.0 / OpenID Connect authorization flow."""
    if not is_google_oauth_configured():
        return redirect(url_for("login", oauth_notice="unconfigured"))

    try:
        redirect_uri = resolve_google_redirect_uri()
    except ValueError as exc:
        return render_template(
            "login.html",
            error=str(exc),
            csrf_token=generate_csrf_token(),
            google_oauth_configured=is_google_oauth_configured(),
        ), 400

    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    session["google_oauth_redirect_uri"] = redirect_uri

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)


@app.route("/auth/google/callback")
def google_callback():
    """Validate OAuth state, exchange authorization code, and establish CryoTrack session."""
    if not is_google_oauth_configured():
        return redirect(url_for("login", oauth_notice="unconfigured"))

    oauth_err = request.args.get("error")
    if oauth_err:
        return render_template(
            "login.html",
            error="Google authentication was cancelled or denied.",
            csrf_token=generate_csrf_token(),
            google_oauth_configured=True,
        ), 400

    returned_state = request.args.get("state", "")
    expected_state = session.pop("google_oauth_state", None)
    redirect_uri = session.pop("google_oauth_redirect_uri", None) or resolve_google_redirect_uri()

    if not expected_state or not returned_state or not secrets.compare_digest(expected_state, returned_state):
        return render_template(
            "login.html",
            error="OAuth state verification failed. Please start Google Sign-In again.",
            csrf_token=generate_csrf_token(),
            google_oauth_configured=True,
        ), 403

    code = request.args.get("code", "").strip()
    if not code:
        return render_template(
            "login.html",
            error="Authorization code was not received from Google.",
            csrf_token=generate_csrf_token(),
            google_oauth_configured=True,
        ), 400

    try:
        token_payload = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode("utf-8")

        token_req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(token_req, timeout=10) as token_resp:
            token_data = json.loads(token_resp.read().decode("utf-8"))

        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("Access token missing in OAuth response.")

        userinfo_req = urllib.request.Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        with urllib.request.urlopen(userinfo_req, timeout=10) as info_resp:
            profile = json.loads(info_resp.read().decode("utf-8"))

        if not profile.get("email_verified"):
            return render_template(
                "login.html",
                error="Your Google account email address must be verified before signing in.",
                csrf_token=generate_csrf_token(),
                google_oauth_configured=True,
            ), 403

        user_session, link_err = authenticate_or_provision_google_user(
            email=profile.get("email"),
            full_name=profile.get("name"),
            google_sub=profile.get("sub"),
        )
        if not user_session:
            return render_template(
                "login.html",
                error=link_err or "Unable to provision CryoTrack account.",
                csrf_token=generate_csrf_token(),
                google_oauth_configured=True,
            ), 403

        session.clear()
        session["user"] = user_session
        session.permanent = True
        generate_csrf_token()
        return redirect(url_for("index"))

    except Exception as exc:
        app.logger.error("Google OAuth callback error: %s", type(exc).__name__)
        return render_template(
            "login.html",
            error="Could not complete Google authentication exchange. Check network and OAuth client settings.",
            csrf_token=generate_csrf_token(),
            google_oauth_configured=True,
        ), 502


@app.route("/logout", methods=["GET", "POST"])
def logout():
    """Invalidate session completely and redirect to login."""
    session.clear()
    return redirect(url_for("login", logged_out="1"))


# =============================================================================
# Primary Application Shell
# =============================================================================
@app.route("/")
@login_required
def index():
    """Render CryoTrack main multi-module platform shell."""
    current_user = get_current_session_user()
    user_perms = current_user.get("permissions") or []
    allowed_tabs = compute_allowed_tabs(user_perms)
    landing_tab = resolve_landing_tab(current_user.get("role"), user_perms)
    return render_template(
        "index.html",
        current_user=current_user,
        user_permissions=user_perms,
        allowed_tabs=allowed_tabs,
        landing_tab=landing_tab,
        csrf_token=generate_csrf_token(),
        google_oauth_configured=is_google_oauth_configured(),
        service=ORACLE_SERVICE,
        schema_user=ORACLE_USER,
    )


# =============================================================================
# API: Sanitized System Health & Lookups
# =============================================================================
@app.route("/api/health")
@login_required
def api_health():
    """Verify Oracle database connectivity without exposing credentials or internals."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SYSDATE, USER, SYS_CONTEXT('USERENV', 'CON_NAME') FROM DUAL")
        db_date, db_user, con_name = cursor.fetchone()
        server_version = conn.version
        cursor.close()
        conn.close()

        return jsonify({
            "status": "healthy",
            "database": "Oracle Database",
            "connected": True,
            "user": db_user,
            "container": con_name,
            "service": ORACLE_SERVICE,
            "server_version": server_version,
            "server_time": db_date.isoformat() if db_date else None,
            "google_oauth_configured": is_google_oauth_configured(),
            "message": "Oracle Database connection active.",
        })
    except Exception as exc:
        app.logger.error("Health check failed: %s", type(exc).__name__)
        return jsonify({
            "status": "unhealthy",
            "database": "Oracle Database",
            "connected": False,
            "service": ORACLE_SERVICE,
            "google_oauth_configured": is_google_oauth_configured(),
            "message": "Oracle Database connection unavailable. Verify listener and .env settings.",
        }), 503


@app.route("/api/lookups")
@login_required
def api_lookups():
    """Return FK reference options for validated create and edit forms."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        data = fetch_lookups(cursor, rows_to_dicts)
        cursor.close()
        conn.close()
        return jsonify(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading form reference lookups")


# =============================================================================
# API: Cold-Chain Command Center Summary Metrics
# =============================================================================
@app.route("/api/dashboard/stats")
@permission_required("command_center:view")
def api_dashboard_stats():
    """Aggregate real Oracle metrics for the Cold-Chain Command Center scoped to user role & permissions."""
    actor = get_current_session_user() or {}
    role = actor.get("role")
    perms = set(actor.get("permissions") or [])
    is_admin_or_mgr = role in ("Administrator", "Operations Manager")

    can_view_products = is_admin_or_mgr or ("products:view" in perms)
    can_view_shipments = is_admin_or_mgr or ("shipments:view" in perms)
    can_view_deliveries = is_admin_or_mgr or ("deliveries:view" in perms)
    can_view_monitoring = is_admin_or_mgr or ("monitoring:view" in perms)
    can_view_inventory = is_admin_or_mgr or ("inventory:view" in perms)
    can_view_incidents = is_admin_or_mgr or ("incidents:view" in perms)

    products_count = None
    batches_count = None
    available_batches = None
    expiring_soon_batches = None
    qt_total = None
    qt_passed = None

    total_shipments = None
    in_transit_shipments = None
    delivered_shipments = None
    vehicles_count = None

    deliveries_count = None
    total_units_delivered = None
    total_units_damaged = None
    facilities_count = None

    open_alerts = None
    critical_alerts = None
    total_incidents = None
    unresolved_incidents = None
    active_sensors = None
    readings_count = None
    avg_temp = None
    min_temp = None
    max_temp = None
    avg_humidity = None
    latest_row = None

    qty_available = None
    qty_reserved = None
    warehouses_count = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if can_view_products:
            cursor.execute("SELECT COUNT(*) FROM PHARMACEUTICAL_PRODUCT")
            products_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM PRODUCT_BATCH")
            batches_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM PRODUCT_BATCH WHERE UPPER(BATCH_STATUS) = 'AVAILABLE'")
            available_batches = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM PRODUCT_BATCH WHERE EXPIRY_DATE <= TRUNC(SYSDATE) + 180")
            expiring_soon_batches = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*), SUM(CASE WHEN UPPER(TEST_RESULT) = 'PASSED' THEN 1 ELSE 0 END) FROM QUALITY_TEST")
            qt_total, qt_passed = cursor.fetchone()
            qt_passed = qt_passed or 0

        if can_view_shipments:
            shp_clause, shp_params = build_shipment_scope_sql(actor, shipment_alias="s")
            cursor.execute(f"SELECT COUNT(*) FROM SHIPMENT s WHERE 1=1{shp_clause}", shp_params)
            total_shipments = cursor.fetchone()[0]

            cursor.execute(f"SELECT COUNT(*) FROM SHIPMENT s WHERE UPPER(SHIPMENT_STATUS) IN ('IN TRANSIT', 'DISPATCHED', 'IN_TRANSIT'){shp_clause}", shp_params)
            in_transit_shipments = cursor.fetchone()[0]

            cursor.execute(f"SELECT COUNT(*) FROM SHIPMENT s WHERE UPPER(SHIPMENT_STATUS) = 'DELIVERED'{shp_clause}", shp_params)
            delivered_shipments = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM VEHICLE")
            vehicles_count = cursor.fetchone()[0]

        if can_view_deliveries:
            cursor.execute("SELECT COUNT(*), NVL(SUM(QUANTITY_RECEIVED), 0), NVL(SUM(QUANTITY_DAMAGED), 0) FROM DELIVERY")
            deliveries_count, total_units_delivered, total_units_damaged = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM HEALTHCARE_FACILITY")
            facilities_count = cursor.fetchone()[0]

        if can_view_monitoring:
            cursor.execute("SELECT COUNT(*) FROM TEMPERATURE_ALERT WHERE UPPER(ALERT_STATUS) = 'OPEN'")
            open_alerts = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM TEMPERATURE_ALERT WHERE UPPER(ALERT_STATUS) = 'OPEN' AND UPPER(SEVERITY) IN ('HIGH', 'CRITICAL')")
            critical_alerts = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM IOT_SENSOR WHERE UPPER(SENSOR_STATUS) = 'ACTIVE'")
            active_sensors = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*),
                       ROUND(AVG(TEMPERATURE), 2),
                       ROUND(MIN(TEMPERATURE), 2),
                       ROUND(MAX(TEMPERATURE), 2),
                       ROUND(AVG(HUMIDITY), 1)
                FROM SENSOR_READING
            """)
            readings_count, avg_temp, min_temp, max_temp, avg_humidity = cursor.fetchone()

            cursor.execute("""
                SELECT sr.TEMPERATURE, sr.HUMIDITY, sr.READING_TIMESTAMP, s.SERIAL_NUMBER
                FROM SENSOR_READING sr
                JOIN IOT_SENSOR s ON sr.SENSOR_ID = s.SENSOR_ID
                ORDER BY sr.READING_TIMESTAMP DESC, sr.READING_ID DESC
                FETCH FIRST 1 ROWS ONLY
            """)
            latest_row = cursor.fetchone()

        if can_view_incidents:
            cursor.execute("SELECT COUNT(*) FROM COLD_CHAIN_INCIDENT")
            total_incidents = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM COLD_CHAIN_INCIDENT WHERE UPPER(RESOLUTION_STATUS) NOT IN ('RESOLVED', 'CLOSED')")
            unresolved_incidents = cursor.fetchone()[0]

        if can_view_inventory:
            wh_clause, wh_params = build_warehouse_scope_sql(actor, warehouse_col="i.WAREHOUSE_ID")
            cursor.execute(f"SELECT NVL(SUM(QUANTITY_AVAILABLE), 0), NVL(SUM(QUANTITY_RESERVED), 0) FROM INVENTORY i WHERE 1=1{wh_clause}", wh_params)
            qty_available, qty_reserved = cursor.fetchone()

            wh_scope_clause, wh_scope_params = build_warehouse_scope_sql(actor, warehouse_col="w.WAREHOUSE_ID")
            cursor.execute(f"SELECT COUNT(*) FROM WAREHOUSE w WHERE 1=1{wh_scope_clause}", wh_scope_params)
            warehouses_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return jsonify({
            "products_count": products_count,
            "batches_count": batches_count,
            "available_batches": available_batches,
            "expiring_soon_batches": expiring_soon_batches,
            "quality_tests_total": qt_total,
            "quality_tests_passed": int(qt_passed) if qt_passed is not None else None,
            "total_shipments": total_shipments,
            "in_transit_shipments": in_transit_shipments,
            "delivered_shipments": delivered_shipments,
            "deliveries_count": deliveries_count,
            "total_units_delivered": serialize_value(total_units_delivered) if total_units_delivered is not None else None,
            "total_units_damaged": serialize_value(total_units_damaged) if total_units_damaged is not None else None,
            "open_alerts": open_alerts,
            "critical_alerts": critical_alerts,
            "total_incidents": total_incidents,
            "unresolved_incidents": unresolved_incidents,
            "active_sensors": active_sensors,
            "inventory_available": serialize_value(qty_available) if qty_available is not None else None,
            "inventory_reserved": serialize_value(qty_reserved) if qty_reserved is not None else None,
            "warehouses_count": warehouses_count,
            "vehicles_count": vehicles_count,
            "facilities_count": facilities_count,
            "readings_count": readings_count,
            "avg_temperature": serialize_value(avg_temp) if avg_temp is not None else None,
            "min_temperature": serialize_value(min_temp) if min_temp is not None else None,
            "max_temperature": serialize_value(max_temp) if max_temp is not None else None,
            "avg_humidity": serialize_value(avg_humidity) if avg_humidity is not None else None,
            "latest_temperature": serialize_value(latest_row[0]) if latest_row else None,
            "latest_humidity": serialize_value(latest_row[1]) if latest_row else None,
            "latest_reading_time": serialize_value(latest_row[2]) if latest_row else None,
            "latest_sensor_serial": latest_row[3] if latest_row else None,
            "user_role": role,
            "user_department": actor.get("department"),
        })
    except Exception as exc:
        return safe_api_error(exc, "Loading Command Center metrics")


# =============================================================================
# PAGE 2 APIs: Products & Quality (Products, Batches, Manufacturers, QC, Conditions)
# =============================================================================
@app.route("/api/products", methods=["GET"])
@permission_required("products:view")
def api_products():
    """List pharmaceutical products with manufacturer and storage conditions."""
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT p.PRODUCT_ID, p.PRODUCT_NAME, p.GENERIC_NAME, p.DOSAGE_FORM,
                   p.STRENGTH, p.PRODUCT_TYPE, p.STORAGE_CATEGORY, p.SHELF_LIFE_DAYS,
                   p.REGULATORY_STATUS,
                   m.MANUFACTURER_ID, m.MANUFACTURER_NAME, m.COUNTRY AS MANUFACTURER_COUNTRY,
                   sc.CONDITION_ID, sc.MINIMUM_TEMPERATURE, sc.MAXIMUM_TEMPERATURE,
                   sc.MINIMUM_HUMIDITY, sc.MAXIMUM_HUMIDITY, sc.LIGHT_SENSITIVITY,
                   sc.STORAGE_INSTRUCTIONS,
                   (SELECT COUNT(*) FROM PRODUCT_BATCH b WHERE b.PRODUCT_ID = p.PRODUCT_ID) AS BATCH_COUNT
            FROM PHARMACEUTICAL_PRODUCT p
            LEFT JOIN MANUFACTURER m ON p.MANUFACTURER_ID = m.MANUFACTURER_ID
            LEFT JOIN STORAGE_CONDITION sc ON p.PRODUCT_ID = sc.PRODUCT_ID
            WHERE 1=1
        """
        params = {}
        if search:
            sql += " AND (UPPER(p.PRODUCT_NAME) LIKE :search OR UPPER(p.GENERIC_NAME) LIKE :search OR UPPER(m.MANUFACTURER_NAME) LIKE :search)"
            params["search"] = f"%{search.upper()}%"
        if category:
            sql += " AND UPPER(p.STORAGE_CATEGORY) = :category"
            params["category"] = category.upper()
        sql += " ORDER BY p.PRODUCT_ID DESC"

        cursor.execute(sql, params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading products")


@app.route("/api/products", methods=["POST"])
@permission_required("products:create")
def api_create_product():
    """Create a pharmaceutical product and its storage condition atomically."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        product_name = parse_text(body.get("product_name"), "Product Name", 100)
        generic_name = parse_text(body.get("generic_name"), "Generic Name", 100)
        manufacturer_id = parse_number(body.get("manufacturer_id"), "Manufacturer", allow_float=False, min_val=1)
        dosage_form = parse_text(body.get("dosage_form"), "Dosage Form", 50)
        strength = parse_text(body.get("strength"), "Strength", 50)
        product_type = parse_text(body.get("product_type"), "Product Type", 50)
        storage_category = parse_text(body.get("storage_category"), "Storage Category", 50)
        shelf_life_days = parse_number(body.get("shelf_life_days"), "Shelf Life (Days)", allow_float=False, min_val=1, max_val=3650)
        regulatory_status = parse_text(body.get("regulatory_status") or "Approved", "Regulatory Status", 30)

        min_temp = parse_number(body.get("minimum_temperature"), "Minimum Temperature", required=False, min_val=-90, max_val=50)
        max_temp = parse_number(body.get("maximum_temperature"), "Maximum Temperature", required=False, min_val=-90, max_val=50)
        min_hum = parse_number(body.get("minimum_humidity"), "Minimum Humidity", required=False, min_val=0, max_val=100)
        max_hum = parse_number(body.get("maximum_humidity"), "Maximum Humidity", required=False, min_val=0, max_val=100)
        light_sens = parse_text(body.get("light_sensitivity"), "Light Sensitivity", 30, required=False) or "Moderate"
        storage_instr = parse_text(body.get("storage_instructions"), "Storage Instructions", 300, required=False)

        if min_temp is not None and max_temp is not None and min_temp > max_temp:
            raise ValueError("Minimum Temperature cannot exceed Maximum Temperature.")
        if min_hum is not None and max_hum is not None and min_hum > max_hum:
            raise ValueError("Minimum Humidity cannot exceed Maximum Humidity.")

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "MANUFACTURER", manufacturer_id, "Manufacturer")

        product_id = next_pk(cursor, "PHARMACEUTICAL_PRODUCT")
        cursor.execute(
            """
            INSERT INTO PHARMACEUTICAL_PRODUCT (
                PRODUCT_ID, MANUFACTURER_ID, PRODUCT_NAME, GENERIC_NAME,
                DOSAGE_FORM, STRENGTH, PRODUCT_TYPE, STORAGE_CATEGORY,
                SHELF_LIFE_DAYS, REGULATORY_STATUS
            ) VALUES (
                :product_id, :manufacturer_id, :product_name, :generic_name,
                :dosage_form, :strength, :product_type, :storage_category,
                :shelf_life_days, :regulatory_status
            )
            """,
            {
                "product_id": product_id,
                "manufacturer_id": manufacturer_id,
                "product_name": product_name,
                "generic_name": generic_name,
                "dosage_form": dosage_form,
                "strength": strength,
                "product_type": product_type,
                "storage_category": storage_category,
                "shelf_life_days": shelf_life_days,
                "regulatory_status": regulatory_status,
            },
        )

        if min_temp is not None or max_temp is not None or storage_instr:
            cond_id = next_pk(cursor, "STORAGE_CONDITION")
            cursor.execute(
                """
                INSERT INTO STORAGE_CONDITION (
                    CONDITION_ID, PRODUCT_ID, MINIMUM_TEMPERATURE, MAXIMUM_TEMPERATURE,
                    MINIMUM_HUMIDITY, MAXIMUM_HUMIDITY, LIGHT_SENSITIVITY, STORAGE_INSTRUCTIONS
                ) VALUES (
                    :condition_id, :product_id, :min_temp, :max_temp,
                    :min_hum, :max_hum, :light_sens, :storage_instr
                )
                """,
                {
                    "condition_id": cond_id,
                    "product_id": product_id,
                    "min_temp": min_temp if min_temp is not None else 2.0,
                    "max_temp": max_temp if max_temp is not None else 8.0,
                    "min_hum": min_hum if min_hum is not None else 35.0,
                    "max_hum": max_hum if max_hum is not None else 60.0,
                    "light_sens": light_sens,
                    "storage_instr": storage_instr or f"Maintain {storage_category} chain conditions.",
                },
            )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Product '{product_name}' (#PRD-{product_id}) created.", "product_id": product_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating pharmaceutical product")


@app.route("/api/manufacturers", methods=["GET"])
@permission_required("products:view")
def api_manufacturers():
    """List licensed pharmaceutical manufacturers."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.MANUFACTURER_ID, m.MANUFACTURER_NAME, m.LICENSE_NUMBER,
                   m.CONTACT_NUMBER, m.EMAIL, m.ADDRESS, m.COUNTRY, m.REGULATORY_AUTHORITY,
                   (SELECT COUNT(*) FROM PHARMACEUTICAL_PRODUCT p WHERE p.MANUFACTURER_ID = m.MANUFACTURER_ID) AS PRODUCT_COUNT
            FROM MANUFACTURER m
            ORDER BY m.MANUFACTURER_ID DESC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading manufacturers")


@app.route("/api/manufacturers", methods=["POST"])
@permission_required("products:create")
def api_create_manufacturer():
    """Register a new pharmaceutical manufacturer."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        name = parse_text(body.get("manufacturer_name"), "Manufacturer Name", 100)
        license_no = parse_text(body.get("license_number"), "License Number", 50)
        contact = parse_text(body.get("contact_number"), "Contact Number", 20, required=False)
        email = parse_text(body.get("email"), "Contact Email", 100, required=False)
        address = parse_text(body.get("address"), "Facility Address", 200, required=False)
        country = parse_text(body.get("country"), "Country", 50)
        authority = parse_text(body.get("regulatory_authority"), "Regulatory Authority", 100)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_unique_value(cursor, "MANUFACTURER", "LICENSE_NUMBER", license_no, "License Number")

        mfg_id = next_pk(cursor, "MANUFACTURER")
        cursor.execute(
            """
            INSERT INTO MANUFACTURER (
                MANUFACTURER_ID, MANUFACTURER_NAME, LICENSE_NUMBER,
                CONTACT_NUMBER, EMAIL, ADDRESS, COUNTRY, REGULATORY_AUTHORITY
            ) VALUES (
                :mfg_id, :name, :license_no, :contact, :email, :address, :country, :authority
            )
            """,
            {
                "mfg_id": mfg_id,
                "name": name,
                "license_no": license_no,
                "contact": contact,
                "email": email,
                "address": address,
                "country": country,
                "authority": authority,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Manufacturer '{name}' registered.", "manufacturer_id": mfg_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating manufacturer")


@app.route("/api/batches", methods=["GET"])
@permission_required("products:view")
def api_batches():
    """List product batches with product info and latest quality test results."""
    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT b.BATCH_ID, b.PRODUCT_ID, b.BATCH_NUMBER, b.MANUFACTURING_DATE,
                   b.EXPIRY_DATE, b.QUANTITY_PRODUCED, b.BATCH_STATUS, b.QUALITY_STATUS,
                   p.PRODUCT_NAME, p.GENERIC_NAME, p.STORAGE_CATEGORY,
                   m.MANUFACTURER_NAME,
                   qt.TEST_ID, qt.TEST_TYPE, qt.TEST_RESULT, qt.TEST_DATE, qt.TESTED_BY, qt.REMARKS AS TEST_REMARKS
            FROM PRODUCT_BATCH b
            JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
            LEFT JOIN MANUFACTURER m ON p.MANUFACTURER_ID = m.MANUFACTURER_ID
            LEFT JOIN (
                SELECT TEST_ID, BATCH_ID, TEST_TYPE, TEST_RESULT, TEST_DATE, TESTED_BY, REMARKS,
                       ROW_NUMBER() OVER (PARTITION BY BATCH_ID ORDER BY TEST_DATE DESC, TEST_ID DESC) AS rn
                FROM QUALITY_TEST
            ) qt ON b.BATCH_ID = qt.BATCH_ID AND qt.rn = 1
            WHERE 1=1
        """
        params = {}
        if status:
            sql += " AND UPPER(b.BATCH_STATUS) = :status"
            params["status"] = status.upper()
        if search:
            sql += " AND (UPPER(b.BATCH_NUMBER) LIKE :search OR UPPER(p.PRODUCT_NAME) LIKE :search OR UPPER(m.MANUFACTURER_NAME) LIKE :search)"
            params["search"] = f"%{search.upper()}%"
        sql += " ORDER BY b.EXPIRY_DATE ASC, b.BATCH_ID DESC"

        cursor.execute(sql, params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading batches")


@app.route("/api/batches", methods=["POST"])
@permission_required("products:create")
def api_create_batch():
    """Create a new pharmaceutical production batch."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        product_id = parse_number(body.get("product_id"), "Product", allow_float=False, min_val=1)
        batch_number = parse_text(body.get("batch_number"), "Batch Number", 50)
        mfg_date = parse_iso_date(body.get("manufacturing_date"), "Manufacturing Date")
        exp_date = parse_iso_date(body.get("expiry_date"), "Expiry Date")
        qty = parse_number(body.get("quantity_produced"), "Quantity Produced", allow_float=False, min_val=1, max_val=10000000)
        batch_status = parse_text(body.get("batch_status") or "Available", "Batch Status", 30)
        quality_status = parse_text(body.get("quality_status") or "Pending", "Quality Status", 30)

        if exp_date <= mfg_date:
            raise ValueError("Expiry Date must be later than Manufacturing Date.")

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "PHARMACEUTICAL_PRODUCT", product_id, "Product")
        ensure_unique_value(cursor, "PRODUCT_BATCH", "BATCH_NUMBER", batch_number, "Batch Number")

        batch_id = next_pk(cursor, "PRODUCT_BATCH")
        cursor.execute(
            """
            INSERT INTO PRODUCT_BATCH (
                BATCH_ID, PRODUCT_ID, BATCH_NUMBER, MANUFACTURING_DATE,
                EXPIRY_DATE, QUANTITY_PRODUCED, BATCH_STATUS, QUALITY_STATUS
            ) VALUES (
                :batch_id, :product_id, :batch_number, :mfg_date,
                :exp_date, :qty, :batch_status, :quality_status
            )
            """,
            {
                "batch_id": batch_id,
                "product_id": product_id,
                "batch_number": batch_number,
                "mfg_date": mfg_date,
                "exp_date": exp_date,
                "qty": qty,
                "batch_status": batch_status,
                "quality_status": quality_status,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Batch '{batch_number}' created.", "batch_id": batch_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating product batch")


@app.route("/api/batches/<int:batch_id>", methods=["PATCH"])
@permission_required("products:transition", "products:edit")
def api_update_batch(batch_id):
    """Update batch status and/or quality status."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        batch_status = parse_text(body.get("batch_status"), "Batch Status", 30)
        quality_status = parse_text(body.get("quality_status"), "Quality Status", 30)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "PRODUCT_BATCH", batch_id, "Product Batch")
        cursor.execute(
            """
            UPDATE PRODUCT_BATCH
            SET BATCH_STATUS = :batch_status,
                QUALITY_STATUS = :quality_status
            WHERE BATCH_ID = :batch_id
            """,
            {"batch_status": batch_status, "quality_status": quality_status, "batch_id": batch_id},
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Batch #{batch_id} updated successfully."})
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Updating batch status")


@app.route("/api/quality-tests", methods=["GET"])
@permission_required("products:view")
def api_quality_tests():
    """List quality control tests linked to batches and products."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT qt.TEST_ID, qt.BATCH_ID, qt.TEST_DATE, qt.TEST_TYPE,
                   qt.TEST_RESULT, qt.TESTED_BY, qt.REMARKS,
                   b.BATCH_NUMBER, p.PRODUCT_NAME
            FROM QUALITY_TEST qt
            JOIN PRODUCT_BATCH b ON qt.BATCH_ID = b.BATCH_ID
            JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
            ORDER BY qt.TEST_DATE DESC, qt.TEST_ID DESC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading quality tests")


@app.route("/api/quality-tests", methods=["POST"])
@permission_required("products:create")
def api_create_quality_test():
    """Record a quality control test and synchronize batch quality status if requested."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        batch_id = parse_number(body.get("batch_id"), "Batch", allow_float=False, min_val=1)
        test_date = parse_iso_date(body.get("test_date") or date.today().isoformat(), "Test Date")
        test_type = parse_text(body.get("test_type"), "Test Type", 50)
        test_result = parse_text(body.get("test_result"), "Test Result", 30)
        tested_by = parse_text(body.get("tested_by"), "Certified Tester", 100)
        remarks = parse_text(body.get("remarks"), "Remarks", 300, required=False)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "PRODUCT_BATCH", batch_id, "Product Batch")

        test_id = next_pk(cursor, "QUALITY_TEST")
        cursor.execute(
            """
            INSERT INTO QUALITY_TEST (
                TEST_ID, BATCH_ID, TEST_DATE, TEST_TYPE, TEST_RESULT, TESTED_BY, REMARKS
            ) VALUES (
                :test_id, :batch_id, :test_date, :test_type, :test_result, :tested_by, :remarks
            )
            """,
            {
                "test_id": test_id,
                "batch_id": batch_id,
                "test_date": test_date,
                "test_type": test_type,
                "test_result": test_result,
                "tested_by": tested_by,
                "remarks": remarks,
            },
        )

        # Keep PRODUCT_BATCH.QUALITY_STATUS aligned with latest QC test outcome
        if test_result.upper() in ("PASSED", "PENDING", "FAILED"):
            new_q = "Passed" if test_result.upper() == "PASSED" else ("Quarantined" if test_result.upper() == "FAILED" else "Pending")
            if test_result.upper() == "FAILED":
                cursor.execute(
                    "UPDATE PRODUCT_BATCH SET QUALITY_STATUS = 'Failed', BATCH_STATUS = 'Quarantined' WHERE BATCH_ID = :bid",
                    {"bid": batch_id},
                )
            else:
                cursor.execute(
                    "UPDATE PRODUCT_BATCH SET QUALITY_STATUS = :qs WHERE BATCH_ID = :bid",
                    {"qs": new_q, "bid": batch_id},
                )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Quality test #QT-{test_id} recorded.", "test_id": test_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Recording quality test")


@app.route("/api/storage-conditions", methods=["GET"])
@permission_required("products:view")
def api_storage_conditions():
    """List defined storage conditions for pharmaceutical products."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sc.CONDITION_ID, sc.PRODUCT_ID, p.PRODUCT_NAME, p.STORAGE_CATEGORY,
                   sc.MINIMUM_TEMPERATURE, sc.MAXIMUM_TEMPERATURE,
                   sc.MINIMUM_HUMIDITY, sc.MAXIMUM_HUMIDITY,
                   sc.LIGHT_SENSITIVITY, sc.STORAGE_INSTRUCTIONS
            FROM STORAGE_CONDITION sc
            JOIN PHARMACEUTICAL_PRODUCT p ON sc.PRODUCT_ID = p.PRODUCT_ID
            ORDER BY sc.CONDITION_ID DESC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading storage conditions")


# =============================================================================
# PAGE 3 APIs: Shipments & Fleet (Shipments, Items, Vehicles, Drivers, Routes, Stops)
# =============================================================================
@app.route("/api/shipments", methods=["GET"])
@permission_required("shipments:view")
def api_shipments():
    """List shipments with route, vehicle, driver, cargo count, and alert indicators, scoped by user access."""
    user = get_current_session_user()
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    search = request.args.get("q", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_shipment_scope_sql(user, shipment_alias="s")
        sql = """
            SELECT s.SHIPMENT_ID, s.SHIPMENT_DATE, s.EXPECTED_DELIVERY_DATE,
                   s.ACTUAL_DELIVERY_DATE, s.SHIPMENT_STATUS, s.PRIORITY_LEVEL,
                   s.TOTAL_WEIGHT, s.ORIGIN_TYPE, s.ORIGIN_ID, s.DESTINATION_TYPE, s.DESTINATION_ID,
                   r.ROUTE_ID, r.ORIGIN, r.DESTINATION, r.TOTAL_DISTANCE, r.ESTIMATED_DURATION,
                   v.VEHICLE_ID, v.REGISTRATION_NUMBER, v.VEHICLE_TYPE, v.REFRIGERATION_TYPE,
                   v.TEMPERATURE_MIN AS VEHICLE_TEMP_MIN, v.TEMPERATURE_MAX AS VEHICLE_TEMP_MAX,
                   d.DRIVER_ID, d.DRIVER_NAME, d.PHONE AS DRIVER_PHONE,
                   va.ASSIGNMENT_ID, va.ASSIGNMENT_STATUS,
                   (SELECT COUNT(*) FROM SHIPMENT_ITEM si WHERE si.SHIPMENT_ID = s.SHIPMENT_ID) AS ITEMS_COUNT,
                   (SELECT COUNT(*) FROM TEMPERATURE_ALERT ta WHERE ta.SHIPMENT_ID = s.SHIPMENT_ID AND UPPER(ta.ALERT_STATUS) = 'OPEN') AS OPEN_ALERTS_COUNT
            FROM SHIPMENT s
            LEFT JOIN ROUTE r ON s.ROUTE_ID = r.ROUTE_ID
            LEFT JOIN (
                SELECT va_inner.*, ROW_NUMBER() OVER (PARTITION BY SHIPMENT_ID ORDER BY ASSIGNMENT_ID DESC) AS rn
                FROM VEHICLE_ASSIGNMENT va_inner
            ) va ON s.SHIPMENT_ID = va.SHIPMENT_ID AND va.rn = 1
            LEFT JOIN VEHICLE v ON va.VEHICLE_ID = v.VEHICLE_ID
            LEFT JOIN DRIVER d ON va.DRIVER_ID = d.DRIVER_ID
            WHERE 1=1
        """
        params = {}
        if scope_clause:
            sql += f" {scope_clause}"
            params.update(scope_params)
        if status:
            sql += " AND UPPER(s.SHIPMENT_STATUS) = :status"
            params["status"] = status.upper()
        if priority:
            sql += " AND UPPER(s.PRIORITY_LEVEL) = :priority"
            params["priority"] = priority.upper()
        if search:
            sql += " AND (TO_CHAR(s.SHIPMENT_ID) LIKE :search OR UPPER(r.ORIGIN) LIKE :search OR UPPER(r.DESTINATION) LIKE :search OR UPPER(d.DRIVER_NAME) LIKE :search OR UPPER(v.REGISTRATION_NUMBER) LIKE :search)"
            params["search"] = f"%{search.upper()}%"
        sql += " ORDER BY s.SHIPMENT_ID DESC"

        cursor.execute(sql, params)
        raw_data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        data = sanitize_records_for_user(raw_data, user, "shipment")
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading shipments")


@app.route("/api/shipments/<int:shipment_id>/details", methods=["GET"])
@permission_required("shipments:view")
def api_shipment_details(shipment_id):
    """Fetch complete manifest cargo items and route stops for a shipment."""
    user = get_current_session_user()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "SHIPMENT", shipment_id, "Shipment")

        if not check_shipment_in_scope(cursor, user, shipment_id):
            cursor.close()
            conn.close()
            return jsonify({"error": "Forbidden", "message": "Access to this shipment is outside your departmental or regional authorization scope."}), 403

        cursor.execute(
            """
            SELECT si.SHIPMENT_ID, si.BATCH_ID, si.QUANTITY, si.PACKAGING_TYPE, si.HANDLING_INSTRUCTIONS,
                   b.BATCH_NUMBER, b.EXPIRY_DATE, p.PRODUCT_NAME, p.STORAGE_CATEGORY
            FROM SHIPMENT_ITEM si
            JOIN PRODUCT_BATCH b ON si.BATCH_ID = b.BATCH_ID
            JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
            WHERE si.SHIPMENT_ID = :sid
            ORDER BY si.BATCH_ID
            """,
            {"sid": shipment_id},
        )
        items = rows_to_dicts(cursor)

        cursor.execute(
            """
            SELECT rs.STOP_ID, rs.SEQUENCE_NUMBER, rs.STOP_NAME, rs.STOP_TYPE,
                   rs.PLANNED_ARRIVAL, rs.PLANNED_DEPARTURE, rs.ACTUAL_ARRIVAL, rs.ACTUAL_DEPARTURE
            FROM SHIPMENT s
            JOIN ROUTE_STOP rs ON s.ROUTE_ID = rs.ROUTE_ID
            WHERE s.SHIPMENT_ID = :sid
            ORDER BY rs.SEQUENCE_NUMBER ASC
            """,
            {"sid": shipment_id},
        )
        stops = rows_to_dicts(cursor)

        cursor.close()
        conn.close()
        return jsonify({"items": items, "stops": stops})
    except Exception as exc:
        return safe_api_error(exc, "Loading shipment manifest details")


@app.route("/api/shipments", methods=["POST"])
@permission_required("shipments:create")
def api_create_shipment():
    """Dispatch a new shipment with optional cargo batch item and vehicle/driver assignment."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        route_id = parse_number(body.get("route_id"), "Transit Route", allow_float=False, min_val=1)
        ship_date = parse_iso_date(body.get("shipment_date") or date.today().isoformat(), "Shipment Date")
        exp_deliv = parse_iso_date(body.get("expected_delivery_date"), "Expected Delivery Date")
        priority = parse_text(body.get("priority_level") or "High", "Priority Level", 20)
        status = parse_text(body.get("shipment_status") or "Dispatched", "Shipment Status", 30)
        total_weight = parse_number(body.get("total_weight"), "Total Cargo Weight (kg)", min_val=0.5, max_val=50000)
        origin_id = parse_number(body.get("origin_id") or 1, "Origin Warehouse", allow_float=False, min_val=1)
        dest_id = parse_number(body.get("destination_id") or 1, "Destination Facility", allow_float=False, min_val=1)

        batch_id = parse_number(body.get("batch_id"), "Cargo Batch", required=False, allow_float=False, min_val=1)
        item_qty = parse_number(body.get("item_quantity"), "Cargo Quantity", required=False, allow_float=False, min_val=1)
        packaging = parse_text(body.get("packaging_type"), "Packaging Type", 50, required=False) or "Insulated Cryo-Container"
        handling = parse_text(body.get("handling_instructions"), "Handling Instructions", 300, required=False) or "Keep upright within certified cold range."

        vehicle_id = parse_number(body.get("vehicle_id"), "Assigned Vehicle", required=False, allow_float=False, min_val=1)
        driver_id = parse_number(body.get("driver_id"), "Assigned Driver", required=False, allow_float=False, min_val=1)

        if exp_deliv < ship_date:
            raise ValueError("Expected Delivery Date cannot precede Shipment Date.")

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "ROUTE", route_id, "Route")
        ensure_fk_exists(cursor, "WAREHOUSE", origin_id, "Origin Warehouse")
        ensure_fk_exists(cursor, "HEALTHCARE_FACILITY", dest_id, "Destination Facility")
        if batch_id:
            ensure_fk_exists(cursor, "PRODUCT_BATCH", batch_id, "Product Batch")
        if vehicle_id:
            ensure_fk_exists(cursor, "VEHICLE", vehicle_id, "Vehicle")
        if driver_id:
            ensure_fk_exists(cursor, "DRIVER", driver_id, "Driver")

        shipment_id = next_pk(cursor, "SHIPMENT")
        actual_deliv = exp_deliv if status.upper() == "DELIVERED" else None
        cursor.execute(
            """
            INSERT INTO SHIPMENT (
                SHIPMENT_ID, SHIPMENT_DATE, EXPECTED_DELIVERY_DATE, ACTUAL_DELIVERY_DATE,
                ORIGIN_TYPE, ORIGIN_ID, DESTINATION_TYPE, DESTINATION_ID,
                SHIPMENT_STATUS, PRIORITY_LEVEL, TOTAL_WEIGHT, ROUTE_ID
            ) VALUES (
                :shipment_id, :ship_date, :exp_deliv, :actual_deliv,
                'Warehouse', :origin_id, 'Healthcare Facility', :dest_id,
                :status, :priority, :total_weight, :route_id
            )
            """,
            {
                "shipment_id": shipment_id,
                "ship_date": ship_date,
                "exp_deliv": exp_deliv,
                "actual_deliv": actual_deliv,
                "origin_id": origin_id,
                "dest_id": dest_id,
                "status": status,
                "priority": priority,
                "total_weight": total_weight,
                "route_id": route_id,
            },
        )

        if batch_id and item_qty:
            cursor.execute(
                """
                INSERT INTO SHIPMENT_ITEM (
                    SHIPMENT_ID, BATCH_ID, QUANTITY, PACKAGING_TYPE, HANDLING_INSTRUCTIONS
                ) VALUES (
                    :shipment_id, :batch_id, :qty, :packaging, :handling
                )
                """,
                {
                    "shipment_id": shipment_id,
                    "batch_id": batch_id,
                    "qty": item_qty,
                    "packaging": packaging,
                    "handling": handling,
                },
            )

        if vehicle_id and driver_id:
            assign_id = next_pk(cursor, "VEHICLE_ASSIGNMENT")
            cursor.execute(
                """
                INSERT INTO VEHICLE_ASSIGNMENT (
                    ASSIGNMENT_ID, SHIPMENT_ID, VEHICLE_ID, DRIVER_ID,
                    ASSIGNMENT_DATE, START_TIME, ASSIGNMENT_STATUS
                ) VALUES (
                    :assign_id, :shipment_id, :vehicle_id, :driver_id,
                    :assign_date, SYSTIMESTAMP, :assign_status
                )
                """,
                {
                    "assign_id": assign_id,
                    "shipment_id": shipment_id,
                    "vehicle_id": vehicle_id,
                    "driver_id": driver_id,
                    "assign_date": ship_date,
                    "assign_status": "Completed" if status.upper() == "DELIVERED" else "Assigned",
                },
            )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Shipment #SHP-{shipment_id} dispatched.", "shipment_id": shipment_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating shipment")


@app.route("/api/shipments/<int:shipment_id>", methods=["PATCH"])
@permission_required("shipments:transition", "shipments:edit")
def api_update_shipment(shipment_id):
    """Update shipment status, priority, and optional vehicle/driver assignment."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        status = parse_text(body.get("shipment_status"), "Shipment Status", 30)
        priority = parse_text(body.get("priority_level"), "Priority Level", 20)
        actual_date = parse_iso_date(body.get("actual_delivery_date"), "Actual Delivery Date", required=False)
        vehicle_id = parse_number(body.get("vehicle_id"), "Vehicle", required=False, allow_float=False, min_val=1)
        driver_id = parse_number(body.get("driver_id"), "Driver", required=False, allow_float=False, min_val=1)

        if status.upper() == "DELIVERED" and not actual_date:
            actual_date = date.today()

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "SHIPMENT", shipment_id, "Shipment")
        if vehicle_id:
            ensure_fk_exists(cursor, "VEHICLE", vehicle_id, "Vehicle")
        if driver_id:
            ensure_fk_exists(cursor, "DRIVER", driver_id, "Driver")

        cursor.execute(
            """
            UPDATE SHIPMENT
            SET SHIPMENT_STATUS = :status,
                PRIORITY_LEVEL = :priority,
                ACTUAL_DELIVERY_DATE = :actual_date
            WHERE SHIPMENT_ID = :shipment_id
            """,
            {
                "status": status,
                "priority": priority,
                "actual_date": actual_date,
                "shipment_id": shipment_id,
            },
        )

        if vehicle_id and driver_id:
            cursor.execute("SELECT ASSIGNMENT_ID FROM VEHICLE_ASSIGNMENT WHERE SHIPMENT_ID = :sid ORDER BY ASSIGNMENT_ID DESC FETCH FIRST 1 ROWS ONLY", {"sid": shipment_id})
            existing_va = cursor.fetchone()
            va_status = "Completed" if status.upper() == "DELIVERED" else "Assigned"
            if existing_va:
                cursor.execute(
                    """
                    UPDATE VEHICLE_ASSIGNMENT
                    SET VEHICLE_ID = :vid, DRIVER_ID = :did, ASSIGNMENT_STATUS = :vastat
                    WHERE ASSIGNMENT_ID = :aid
                    """,
                    {"vid": vehicle_id, "did": driver_id, "vastat": va_status, "aid": existing_va[0]},
                )
            else:
                assign_id = next_pk(cursor, "VEHICLE_ASSIGNMENT")
                cursor.execute(
                    """
                    INSERT INTO VEHICLE_ASSIGNMENT (
                        ASSIGNMENT_ID, SHIPMENT_ID, VEHICLE_ID, DRIVER_ID,
                        ASSIGNMENT_DATE, START_TIME, ASSIGNMENT_STATUS
                    ) VALUES (
                        :aid, :sid, :vid, :did, TRUNC(SYSDATE), SYSTIMESTAMP, :vastat
                    )
                    """,
                    {"aid": assign_id, "sid": shipment_id, "vid": vehicle_id, "did": driver_id, "vastat": va_status},
                )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Shipment #SHP-{shipment_id} updated."})
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Updating shipment")


@app.route("/api/shipment-items", methods=["GET"])
@permission_required("shipments:view")
def api_shipment_items():
    """List cargo batch items across shipments."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT si.SHIPMENT_ID, si.BATCH_ID, si.QUANTITY, si.PACKAGING_TYPE, si.HANDLING_INSTRUCTIONS,
                   b.BATCH_NUMBER, b.EXPIRY_DATE, p.PRODUCT_NAME, p.STORAGE_CATEGORY,
                   s.SHIPMENT_STATUS, r.ORIGIN, r.DESTINATION
            FROM SHIPMENT_ITEM si
            JOIN PRODUCT_BATCH b ON si.BATCH_ID = b.BATCH_ID
            JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
            JOIN SHIPMENT s ON si.SHIPMENT_ID = s.SHIPMENT_ID
            LEFT JOIN ROUTE r ON s.ROUTE_ID = r.ROUTE_ID
            ORDER BY si.SHIPMENT_ID DESC, si.BATCH_ID ASC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading shipment items")


@app.route("/api/vehicles", methods=["GET"])
@permission_required("shipments:view")
def api_vehicles():
    """List refrigerated fleet vehicles scoped by user authorization."""
    user = get_current_session_user()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_vehicle_scope_sql(user, vehicle_col="v.VEHICLE_ID")
        sql = """
            SELECT v.VEHICLE_ID, v.REGISTRATION_NUMBER, v.VEHICLE_TYPE, v.REFRIGERATION_TYPE,
                   v.TEMPERATURE_MIN, v.TEMPERATURE_MAX, v.CAPACITY, v.VEHICLE_STATUS,
                   v.LAST_MAINTENANCE_DATE,
                   (SELECT COUNT(*) FROM IOT_SENSOR s WHERE s.VEHICLE_ID = v.VEHICLE_ID) AS SENSOR_COUNT,
                   (SELECT COUNT(*) FROM VEHICLE_ASSIGNMENT va WHERE va.VEHICLE_ID = v.VEHICLE_ID) AS ASSIGNMENT_COUNT
            FROM VEHICLE v
            WHERE 1=1
        """
        if scope_clause:
            sql += f" {scope_clause}"
        sql += " ORDER BY v.VEHICLE_ID DESC"
        cursor.execute(sql, scope_params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading fleet vehicles")


@app.route("/api/vehicles", methods=["POST"])
@permission_required("shipments:create")
def api_create_vehicle():
    """Register a new refrigerated fleet vehicle."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        reg_no = parse_text(body.get("registration_number"), "Registration Number", 30)
        v_type = parse_text(body.get("vehicle_type"), "Vehicle Type", 50)
        ref_type = parse_text(body.get("refrigeration_type"), "Refrigeration Type", 50)
        t_min = parse_number(body.get("temperature_min"), "Minimum Temperature (°C)", min_val=-90, max_val=40)
        t_max = parse_number(body.get("temperature_max"), "Maximum Temperature (°C)", min_val=-90, max_val=40)
        capacity = parse_number(body.get("capacity"), "Cargo Capacity (kg)", min_val=50, max_val=100000)
        status = parse_text(body.get("vehicle_status") or "Available", "Vehicle Status", 30)
        maint_date = parse_iso_date(body.get("last_maintenance_date") or date.today().isoformat(), "Last Maintenance Date")

        if t_min > t_max:
            raise ValueError("Minimum Temperature cannot exceed Maximum Temperature.")

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_unique_value(cursor, "VEHICLE", "REGISTRATION_NUMBER", reg_no, "Registration Number")

        vid = next_pk(cursor, "VEHICLE")
        cursor.execute(
            """
            INSERT INTO VEHICLE (
                VEHICLE_ID, REGISTRATION_NUMBER, VEHICLE_TYPE, REFRIGERATION_TYPE,
                TEMPERATURE_MIN, TEMPERATURE_MAX, CAPACITY, VEHICLE_STATUS, LAST_MAINTENANCE_DATE
            ) VALUES (
                :vid, :reg_no, :v_type, :ref_type, :t_min, :t_max, :capacity, :status, :maint_date
            )
            """,
            {
                "vid": vid,
                "reg_no": reg_no,
                "v_type": v_type,
                "ref_type": ref_type,
                "t_min": t_min,
                "t_max": t_max,
                "capacity": capacity,
                "status": status,
                "maint_date": maint_date,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Vehicle '{reg_no}' added to fleet.", "vehicle_id": vid}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Registering vehicle")


@app.route("/api/drivers", methods=["GET"])
@permission_required("shipments:view")
def api_drivers():
    """List certified cold-chain transport drivers with sensitive field masking."""
    user = get_current_session_user()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.DRIVER_ID, d.DRIVER_NAME, d.LICENSE_NUMBER, d.PHONE,
                   d.LICENSE_EXPIRY, d.CERTIFICATION, d.EMPLOYMENT_STATUS,
                   (SELECT COUNT(*) FROM VEHICLE_ASSIGNMENT va WHERE va.DRIVER_ID = d.DRIVER_ID) AS TRIPS_COUNT
            FROM DRIVER d
            ORDER BY d.DRIVER_ID DESC
        """)
        raw_data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        data = sanitize_records_for_user(raw_data, user, "driver")
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading drivers")


@app.route("/api/drivers", methods=["POST"])
@permission_required("shipments:create")
def api_create_driver():
    """Register a certified cold-chain driver."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        name = parse_text(body.get("driver_name"), "Driver Name", 100)
        lic = parse_text(body.get("license_number"), "License Number", 50)
        phone = parse_text(body.get("phone"), "Phone Number", 20)
        expiry = parse_iso_date(body.get("license_expiry"), "License Expiry Date")
        cert = parse_text(body.get("certification") or "GDP Cold-Chain Handling", "Certification", 100)
        status = parse_text(body.get("employment_status") or "Active", "Employment Status", 30)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_unique_value(cursor, "DRIVER", "LICENSE_NUMBER", lic, "License Number")

        did = next_pk(cursor, "DRIVER")
        cursor.execute(
            """
            INSERT INTO DRIVER (
                DRIVER_ID, DRIVER_NAME, LICENSE_NUMBER, PHONE,
                LICENSE_EXPIRY, CERTIFICATION, EMPLOYMENT_STATUS
            ) VALUES (
                :did, :name, :lic, :phone, :expiry, :cert, :status
            )
            """,
            {
                "did": did,
                "name": name,
                "lic": lic,
                "phone": phone,
                "expiry": expiry,
                "cert": cert,
                "status": status,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Driver '{name}' registered.", "driver_id": did}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Registering driver")


@app.route("/api/routes", methods=["GET"])
@permission_required("shipments:view")
def api_routes():
    """List logistics routes with route stop counts scoped by user authorization."""
    user = get_current_session_user()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_route_scope_sql(user, route_col="r.ROUTE_ID")
        sql = """
            SELECT r.ROUTE_ID, r.ORIGIN, r.DESTINATION, r.TOTAL_DISTANCE,
                   r.ESTIMATED_DURATION, r.ROUTE_TYPE, r.ROUTE_STATUS,
                   (SELECT COUNT(*) FROM ROUTE_STOP rs WHERE rs.ROUTE_ID = r.ROUTE_ID) AS STOPS_COUNT,
                   (SELECT COUNT(*) FROM SHIPMENT s WHERE s.ROUTE_ID = r.ROUTE_ID) AS SHIPMENTS_COUNT
            FROM ROUTE r
            WHERE 1=1
        """
        if scope_clause:
            sql += f" {scope_clause}"
        sql += " ORDER BY r.ROUTE_ID DESC"
        cursor.execute(sql, scope_params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading routes")


@app.route("/api/routes", methods=["POST"])
@permission_required("shipments:create")
def api_create_route():
    """Define a new cold-chain transit route and optional initial checkpoint stop."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        origin = parse_text(body.get("origin"), "Origin", 150)
        destination = parse_text(body.get("destination"), "Destination", 150)
        distance = parse_number(body.get("total_distance"), "Total Distance (km)", min_val=1, max_val=25000)
        duration = parse_number(body.get("estimated_duration"), "Estimated Duration (hrs)", min_val=0.5, max_val=500)
        route_type = parse_text(body.get("route_type") or "Expressway", "Route Type", 50)
        route_status = parse_text(body.get("route_status") or "Active", "Route Status", 30)
        first_stop = parse_text(body.get("initial_stop_name"), "Initial Checkpoint Stop", 100, required=False)

        conn = get_db_connection()
        cursor = conn.cursor()
        rid = next_pk(cursor, "ROUTE")
        cursor.execute(
            """
            INSERT INTO ROUTE (
                ROUTE_ID, ORIGIN, DESTINATION, TOTAL_DISTANCE,
                ESTIMATED_DURATION, ROUTE_TYPE, ROUTE_STATUS
            ) VALUES (
                :rid, :origin, :destination, :distance, :duration, :route_type, :route_status
            )
            """,
            {
                "rid": rid,
                "origin": origin,
                "destination": destination,
                "distance": distance,
                "duration": duration,
                "route_type": route_type,
                "route_status": route_status,
            },
        )
        if first_stop:
            sid = next_pk(cursor, "ROUTE_STOP")
            cursor.execute(
                """
                INSERT INTO ROUTE_STOP (
                    STOP_ID, ROUTE_ID, STOP_NAME, STOP_TYPE, SEQUENCE_NUMBER,
                    PLANNED_ARRIVAL, PLANNED_DEPARTURE
                ) VALUES (
                    :sid, :rid, :sname, 'Checkpoint', 1, SYSTIMESTAMP, SYSTIMESTAMP + INTERVAL '1' HOUR
                )
                """,
                {"sid": sid, "rid": rid, "sname": first_stop},
            )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Route '{origin} -> {destination}' created.", "route_id": rid}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating transit route")


@app.route("/api/route-stops", methods=["GET"])
@permission_required("shipments:view")
def api_route_stops():
    """List route checkpoints and stops."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rs.STOP_ID, rs.ROUTE_ID, rs.STOP_NAME, rs.STOP_TYPE, rs.SEQUENCE_NUMBER,
                   rs.PLANNED_ARRIVAL, rs.PLANNED_DEPARTURE, rs.ACTUAL_ARRIVAL, rs.ACTUAL_DEPARTURE,
                   r.ORIGIN, r.DESTINATION
            FROM ROUTE_STOP rs
            JOIN ROUTE r ON rs.ROUTE_ID = r.ROUTE_ID
            ORDER BY rs.ROUTE_ID ASC, rs.SEQUENCE_NUMBER ASC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading route stops")


# =============================================================================
# PAGE 4 APIs: Cold-Chain Monitoring (IoT Sensors, Sensor Readings, Alerts)
# =============================================================================
@app.route("/api/monitoring/sensors", methods=["GET"])
@permission_required("monitoring:view")
def api_sensors():
    """List IoT sensors with assigned vehicles and latest recorded readings."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.SENSOR_ID, s.VEHICLE_ID, s.SENSOR_TYPE, s.SERIAL_NUMBER,
                   s.MANUFACTURER, s.INSTALLATION_DATE, s.CALIBRATION_DATE,
                   s.CALIBRATION_EXPIRY, s.SENSOR_STATUS, s.ACCURACY,
                   v.REGISTRATION_NUMBER, v.VEHICLE_TYPE, v.TEMPERATURE_MIN, v.TEMPERATURE_MAX,
                   sr.READING_ID, sr.READING_TIMESTAMP, sr.TEMPERATURE, sr.HUMIDITY,
                   sr.BATTERY_LEVEL, sr.LATITUDE, sr.LONGITUDE
            FROM IOT_SENSOR s
            LEFT JOIN VEHICLE v ON s.VEHICLE_ID = v.VEHICLE_ID
            LEFT JOIN (
                SELECT sr_inner.*, ROW_NUMBER() OVER (PARTITION BY SENSOR_ID ORDER BY READING_TIMESTAMP DESC, READING_ID DESC) AS rn
                FROM SENSOR_READING sr_inner
            ) sr ON s.SENSOR_ID = sr.SENSOR_ID AND sr.rn = 1
            ORDER BY s.SENSOR_ID DESC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading IoT sensors")


@app.route("/api/monitoring/sensors", methods=["POST"])
@permission_required("monitoring:create")
def api_create_sensor():
    """Register a new calibrated IoT sensor node."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        serial = parse_text(body.get("serial_number"), "Serial Number", 50)
        sensor_type = parse_text(body.get("sensor_type") or "Temperature and Humidity", "Sensor Type", 50)
        manufacturer = parse_text(body.get("manufacturer"), "Sensor Manufacturer", 100)
        vehicle_id = parse_number(body.get("vehicle_id"), "Assigned Vehicle", required=False, allow_float=False, min_val=1)
        accuracy = parse_number(body.get("accuracy") or 0.2, "Accuracy (±°C)", min_val=0.01, max_val=5.0)
        cal_date = parse_iso_date(body.get("calibration_date") or date.today().isoformat(), "Calibration Date")
        cal_exp = parse_iso_date(body.get("calibration_expiry"), "Calibration Expiry Date")
        status = parse_text(body.get("sensor_status") or "Active", "Sensor Status", 30)

        if cal_exp <= cal_date:
            raise ValueError("Calibration Expiry Date must be after Calibration Date.")

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_unique_value(cursor, "IOT_SENSOR", "SERIAL_NUMBER", serial, "Serial Number")
        if vehicle_id:
            ensure_fk_exists(cursor, "VEHICLE", vehicle_id, "Vehicle")

        sensor_id = next_pk(cursor, "IOT_SENSOR")
        cursor.execute(
            """
            INSERT INTO IOT_SENSOR (
                SENSOR_ID, VEHICLE_ID, SENSOR_TYPE, SERIAL_NUMBER, MANUFACTURER,
                INSTALLATION_DATE, CALIBRATION_DATE, CALIBRATION_EXPIRY, SENSOR_STATUS, ACCURACY
            ) VALUES (
                :sid, :vid, :stype, :serial, :mfg,
                :inst_date, :cal_date, :cal_exp, :status, :accuracy
            )
            """,
            {
                "sid": sensor_id,
                "vid": vehicle_id,
                "stype": sensor_type,
                "serial": serial,
                "mfg": manufacturer,
                "inst_date": cal_date,
                "cal_date": cal_date,
                "cal_exp": cal_exp,
                "status": status,
                "accuracy": accuracy,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"IoT Sensor '{serial}' (#SNS-{sensor_id}) registered.", "sensor_id": sensor_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Registering IoT sensor")


@app.route("/api/monitoring/readings", methods=["GET"])
@permission_required("monitoring:view")
def api_sensor_readings():
    """List recorded sensor telemetry readings."""
    sensor_id = request.args.get("sensor_id", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT sr.READING_ID, sr.SENSOR_ID, sr.READING_TIMESTAMP,
                   sr.TEMPERATURE, sr.HUMIDITY, sr.LATITUDE, sr.LONGITUDE, sr.BATTERY_LEVEL,
                   s.SERIAL_NUMBER, s.SENSOR_TYPE, v.REGISTRATION_NUMBER
            FROM SENSOR_READING sr
            JOIN IOT_SENSOR s ON sr.SENSOR_ID = s.SENSOR_ID
            LEFT JOIN VEHICLE v ON s.VEHICLE_ID = v.VEHICLE_ID
            WHERE 1=1
        """
        params = {}
        if sensor_id:
            sql += " AND sr.SENSOR_ID = :sensor_id"
            params["sensor_id"] = int(sensor_id)
        sql += " ORDER BY sr.READING_TIMESTAMP DESC, sr.READING_ID DESC"

        cursor.execute(sql, params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading sensor readings")


@app.route("/api/monitoring/readings", methods=["POST"])
@permission_required("monitoring:create")
def api_create_sensor_reading():
    """Record a sensor measurement and automatically raise a temperature alert on excursion if requested."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        sensor_id = parse_number(body.get("sensor_id"), "IoT Sensor", allow_float=False, min_val=1)
        temp = parse_number(body.get("temperature"), "Recorded Temperature (°C)", min_val=-95, max_val=60)
        humidity = parse_number(body.get("humidity") if body.get("humidity") is not None else 45.0, "Relative Humidity (%)", min_val=0, max_val=100)
        battery = parse_number(body.get("battery_level") if body.get("battery_level") is not None else 92.0, "Battery Level (%)", min_val=0, max_val=100)
        lat = parse_number(body.get("latitude"), "Latitude", required=False, min_val=-90, max_val=90)
        lon = parse_number(body.get("longitude"), "Longitude", required=False, min_val=-180, max_val=180)
        shipment_id = parse_number(body.get("shipment_id"), "Linked Shipment", required=False, allow_float=False, min_val=1)
        exp_min = parse_number(body.get("expected_min") if body.get("expected_min") is not None else 2.0, "Expected Min (°C)", min_val=-95, max_val=50)
        exp_max = parse_number(body.get("expected_max") if body.get("expected_max") is not None else 8.0, "Expected Max (°C)", min_val=-95, max_val=50)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "IOT_SENSOR", sensor_id, "IoT Sensor")
        if shipment_id:
            ensure_fk_exists(cursor, "SHIPMENT", shipment_id, "Shipment")

        reading_id = next_pk(cursor, "SENSOR_READING")
        cursor.execute(
            """
            INSERT INTO SENSOR_READING (
                READING_ID, SENSOR_ID, READING_TIMESTAMP, TEMPERATURE,
                HUMIDITY, LATITUDE, LONGITUDE, BATTERY_LEVEL
            ) VALUES (
                :rid, :sid, SYSTIMESTAMP, :temp, :hum, :lat, :lon, :bat
            )
            """,
            {
                "rid": reading_id,
                "sid": sensor_id,
                "temp": temp,
                "hum": humidity,
                "lat": lat,
                "lon": lon,
                "bat": battery,
            },
        )

        alert_created = None
        if temp > exp_max or temp < exp_min:
            alert_id = next_pk(cursor, "TEMPERATURE_ALERT")
            deviation = abs(temp - exp_max) if temp > exp_max else abs(exp_min - temp)
            severity = "Critical" if deviation >= 4.0 else ("High" if deviation >= 2.0 else "Medium")
            alert_type = "High Temperature" if temp > exp_max else "LOW_TEMPERATURE"
            cursor.execute(
                """
                INSERT INTO TEMPERATURE_ALERT (
                    ALERT_ID, SENSOR_ID, SHIPMENT_ID, ALERT_TIME, ALERT_TYPE,
                    RECORDED_TEMPERATURE, EXPECTED_MIN, EXPECTED_MAX, SEVERITY, ALERT_STATUS
                ) VALUES (
                    :aid, :sid, :shid, SYSTIMESTAMP, :atype,
                    :rtemp, :emin, :emax, :sev, 'Open'
                )
                """,
                {
                    "aid": alert_id,
                    "sid": sensor_id,
                    "shid": shipment_id,
                    "atype": alert_type,
                    "rtemp": temp,
                    "emin": exp_min,
                    "emax": exp_max,
                    "sev": severity,
                },
            )
            alert_created = alert_id

        conn.commit()
        cursor.close()
        conn.close()
        msg = f"Telemetry reading #{reading_id} ({temp}°C) recorded."
        if alert_created:
            msg += f" Excursion detected: Alert #ALT-{alert_created} flagged Open."
        return jsonify({"message": msg, "reading_id": reading_id, "alert_id": alert_created}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Recording sensor reading")


@app.route("/api/monitoring/alerts", methods=["GET"])
@permission_required("monitoring:view")
def api_temperature_alerts():
    """List temperature excursions and environmental alerts scoped by user authorization."""
    user = get_current_session_user()
    status = request.args.get("status", "").strip()
    severity = request.args.get("severity", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_alert_scope_sql(user, alert_alias="ta")
        sql = """
            SELECT ta.ALERT_ID, ta.SENSOR_ID, ta.SHIPMENT_ID, ta.ALERT_TIME,
                   ta.ALERT_TYPE, ta.RECORDED_TEMPERATURE, ta.EXPECTED_MIN,
                   ta.EXPECTED_MAX, ta.SEVERITY, ta.ALERT_STATUS, ta.ACKNOWLEDGED_TIME,
                   s.SERIAL_NUMBER AS SENSOR_SERIAL,
                   sh.SHIPMENT_STATUS,
                   r.ORIGIN, r.DESTINATION,
                   cci.INCIDENT_ID
            FROM TEMPERATURE_ALERT ta
            LEFT JOIN IOT_SENSOR s ON ta.SENSOR_ID = s.SENSOR_ID
            LEFT JOIN SHIPMENT sh ON ta.SHIPMENT_ID = sh.SHIPMENT_ID
            LEFT JOIN ROUTE r ON sh.ROUTE_ID = r.ROUTE_ID
            LEFT JOIN COLD_CHAIN_INCIDENT cci ON ta.ALERT_ID = cci.ALERT_ID
            WHERE 1=1
        """
        params = {}
        if scope_clause:
            sql += f" {scope_clause}"
            params.update(scope_params)
        if status:
            sql += " AND UPPER(ta.ALERT_STATUS) = :status"
            params["status"] = status.upper()
        if severity:
            sql += " AND UPPER(ta.SEVERITY) = :severity"
            params["severity"] = severity.upper()
        sql += " ORDER BY ta.ALERT_TIME DESC, ta.ALERT_ID DESC"

        cursor.execute(sql, params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading temperature alerts")


@app.route("/api/monitoring/alerts/<int:alert_id>", methods=["PATCH"])
@permission_required("monitoring:transition")
def api_update_alert_status(alert_id):
    """Acknowledge or resolve a temperature excursion alert."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        new_status = parse_text(body.get("alert_status"), "Alert Status", 30)
        if new_status.upper() not in ("OPEN", "ACKNOWLEDGED", "RESOLVED"):
            raise ValueError("Alert Status must be Open, Acknowledged, or Resolved.")

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "TEMPERATURE_ALERT", alert_id, "Temperature Alert")

        if new_status.upper() in ("ACKNOWLEDGED", "RESOLVED"):
            cursor.execute(
                """
                UPDATE TEMPERATURE_ALERT
                SET ALERT_STATUS = :st,
                    ACKNOWLEDGED_TIME = NVL(ACKNOWLEDGED_TIME, SYSTIMESTAMP)
                WHERE ALERT_ID = :aid
                """,
                {"st": new_status, "aid": alert_id},
            )
        else:
            cursor.execute(
                "UPDATE TEMPERATURE_ALERT SET ALERT_STATUS = :st WHERE ALERT_ID = :aid",
                {"st": new_status, "aid": alert_id},
            )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Alert #ALT-{alert_id} marked '{new_status}'."})
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Updating temperature alert")


# =============================================================================
# PAGE 5 APIs: Inventory & Warehousing (Inventory, Transactions, Warehouses, Units)
# =============================================================================
@app.route("/api/inventory", methods=["GET"])
@permission_required("inventory:view")
def api_inventory():
    """List inventory lots with batch, product, storage unit, and warehouse details scoped by warehouse authorization."""
    user = get_current_session_user()
    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_warehouse_scope_sql(user, warehouse_col="w.WAREHOUSE_ID")
        sql = """
            SELECT inv.INVENTORY_ID, inv.QUANTITY_AVAILABLE, inv.QUANTITY_RESERVED,
                   (inv.QUANTITY_AVAILABLE + inv.QUANTITY_RESERVED) AS TOTAL_QUANTITY,
                   inv.LAST_UPDATED, inv.INVENTORY_STATUS,
                   b.BATCH_ID, b.BATCH_NUMBER, b.EXPIRY_DATE, b.BATCH_STATUS,
                   p.PRODUCT_ID, p.PRODUCT_NAME, p.GENERIC_NAME, p.STORAGE_CATEGORY,
                   su.STORAGE_UNIT_ID, su.UNIT_NAME, su.UNIT_TYPE,
                   su.MINIMUM_TEMPERATURE AS UNIT_MIN_TEMP, su.MAXIMUM_TEMPERATURE AS UNIT_MAX_TEMP,
                   w.WAREHOUSE_ID, w.WAREHOUSE_NAME, w.CITY AS WAREHOUSE_CITY
            FROM INVENTORY inv
            JOIN PRODUCT_BATCH b ON inv.BATCH_ID = b.BATCH_ID
            JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
            JOIN STORAGE_UNIT su ON inv.STORAGE_UNIT_ID = su.STORAGE_UNIT_ID
            JOIN WAREHOUSE w ON su.WAREHOUSE_ID = w.WAREHOUSE_ID
            WHERE 1=1
        """
        params = {}
        if scope_clause:
            sql += f" {scope_clause}"
            params.update(scope_params)
        if status:
            sql += " AND UPPER(inv.INVENTORY_STATUS) = :status"
            params["status"] = status.upper()
        if search:
            sql += " AND (UPPER(p.PRODUCT_NAME) LIKE :search OR UPPER(b.BATCH_NUMBER) LIKE :search OR UPPER(w.WAREHOUSE_NAME) LIKE :search OR UPPER(su.UNIT_NAME) LIKE :search)"
            params["search"] = f"%{search.upper()}%"
        sql += " ORDER BY inv.INVENTORY_ID DESC"

        cursor.execute(sql, params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading inventory")


@app.route("/api/inventory", methods=["POST"])
@permission_required("inventory:create")
def api_create_inventory():
    """Allocate a new inventory lot and record the corresponding STOCK_IN transaction atomically."""
    body = request.get_json(silent=True) or {}
    actor = get_current_session_user()
    conn = None
    try:
        batch_id = parse_number(body.get("batch_id"), "Product Batch", allow_float=False, min_val=1)
        unit_id = parse_number(body.get("storage_unit_id"), "Storage Unit", allow_float=False, min_val=1)
        qty_avail = parse_number(body.get("quantity_available"), "Initial Available Quantity", allow_float=False, min_val=1, max_val=10000000)
        qty_res = parse_number(body.get("quantity_reserved") or 0, "Reserved Quantity", allow_float=False, min_val=0, max_val=10000000)
        remarks = parse_text(body.get("remarks"), "Transaction Remarks", 300, required=False) or "Initial cold-storage stock allocation"

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "PRODUCT_BATCH", batch_id, "Product Batch")
        ensure_fk_exists(cursor, "STORAGE_UNIT", unit_id, "Storage Unit")

        inv_id = next_pk(cursor, "INVENTORY")
        cursor.execute(
            """
            INSERT INTO INVENTORY (
                INVENTORY_ID, BATCH_ID, STORAGE_UNIT_ID, QUANTITY_AVAILABLE,
                QUANTITY_RESERVED, LAST_UPDATED, INVENTORY_STATUS
            ) VALUES (
                :inv_id, :batch_id, :unit_id, :qty_avail, :qty_res, SYSDATE, 'Available'
            )
            """,
            {
                "inv_id": inv_id,
                "batch_id": batch_id,
                "unit_id": unit_id,
                "qty_avail": qty_avail,
                "qty_res": qty_res,
            },
        )

        trx_id = next_pk(cursor, "INVENTORY_TRANSACTION")
        cursor.execute(
            """
            INSERT INTO INVENTORY_TRANSACTION (
                TRANSACTION_ID, INVENTORY_ID, TRANSACTION_TYPE, QUANTITY,
                TRANSACTION_DATE, REFERENCE_TYPE, REFERENCE_ID, PERFORMED_BY, REMARKS
            ) VALUES (
                :trx_id, :inv_id, 'STOCK_IN', :qty, SYSDATE, 'BATCH', :batch_id, :actor_name, :remarks
            )
            """,
            {
                "trx_id": trx_id,
                "inv_id": inv_id,
                "qty": qty_avail + qty_res,
                "batch_id": batch_id,
                "actor_name": actor.get("full_name", "Operator")[:100],
                "remarks": remarks,
            },
        )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Inventory #INV-{inv_id} allocated and STOCK_IN transaction #TRX-{trx_id} logged.", "inventory_id": inv_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Allocating inventory")


@app.route("/api/inventory/transactions", methods=["GET"])
@permission_required("inventory:view")
def api_inventory_transactions():
    """List stock movement transactions scoped by warehouse authorization."""
    user = get_current_session_user()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_warehouse_scope_sql(user, warehouse_col="w.WAREHOUSE_ID")
        sql = """
            SELECT it.TRANSACTION_ID, it.INVENTORY_ID, it.TRANSACTION_TYPE,
                   it.QUANTITY, it.TRANSACTION_DATE, it.REFERENCE_TYPE,
                   it.REFERENCE_ID, it.PERFORMED_BY, it.REMARKS,
                   p.PRODUCT_NAME, b.BATCH_NUMBER, w.WAREHOUSE_NAME
            FROM INVENTORY_TRANSACTION it
            JOIN INVENTORY inv ON it.INVENTORY_ID = inv.INVENTORY_ID
            JOIN PRODUCT_BATCH b ON inv.BATCH_ID = b.BATCH_ID
            JOIN PHARMACEUTICAL_PRODUCT p ON b.PRODUCT_ID = p.PRODUCT_ID
            LEFT JOIN STORAGE_UNIT su ON inv.STORAGE_UNIT_ID = su.STORAGE_UNIT_ID
            LEFT JOIN WAREHOUSE w ON su.WAREHOUSE_ID = w.WAREHOUSE_ID
            WHERE 1=1
        """
        if scope_clause:
            sql += f" {scope_clause}"
        sql += " ORDER BY it.TRANSACTION_DATE DESC, it.TRANSACTION_ID DESC"
        cursor.execute(sql, scope_params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading inventory transactions")


@app.route("/api/inventory/transactions", methods=["POST"])
@permission_required("inventory:transition")
def api_record_inventory_transaction():
    """Execute a validated stock movement and record its audit transaction atomically."""
    body = request.get_json(silent=True) or {}
    actor = get_current_session_user()
    conn = None
    try:
        inv_id = parse_number(body.get("inventory_id"), "Inventory Record", allow_float=False, min_val=1)
        trx_type = parse_text(body.get("transaction_type"), "Transaction Type", 30).upper()
        qty = parse_number(body.get("quantity"), "Quantity", allow_float=False, min_val=1, max_val=10000000)
        ref_type = parse_text(body.get("reference_type") or "MANUAL", "Reference Type", 30)
        ref_id = parse_number(body.get("reference_id"), "Reference ID", required=False, allow_float=False, min_val=1)
        remarks = parse_text(body.get("remarks"), "Remarks", 300)

        if trx_type not in ("STOCK_IN", "STOCK_OUT", "RESERVATION", "RELEASE"):
            raise ValueError("Transaction Type must be STOCK_IN, STOCK_OUT, RESERVATION, or RELEASE.")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT QUANTITY_AVAILABLE, QUANTITY_RESERVED FROM INVENTORY WHERE INVENTORY_ID = :iid FOR UPDATE",
            {"iid": inv_id},
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Inventory record #{inv_id} does not exist.")

        avail, reserved = int(row[0] or 0), int(row[1] or 0)
        if trx_type == "STOCK_IN":
            avail += qty
        elif trx_type == "STOCK_OUT":
            if qty > avail:
                raise ValueError(f"Insufficient available quantity ({avail} units) for STOCK_OUT of {qty} units.")
            avail -= qty
        elif trx_type == "RESERVATION":
            if qty > avail:
                raise ValueError(f"Insufficient available quantity ({avail} units) to reserve {qty} units.")
            avail -= qty
            reserved += qty
        elif trx_type == "RELEASE":
            if qty > reserved:
                raise ValueError(f"Cannot release {qty} units; only {reserved} units are currently reserved.")
            reserved -= qty
            avail += qty

        inv_status = "Available" if avail > 0 else ("Reserved" if reserved > 0 else "Depleted")
        cursor.execute(
            """
            UPDATE INVENTORY
            SET QUANTITY_AVAILABLE = :avail,
                QUANTITY_RESERVED = :res,
                INVENTORY_STATUS = :st,
                LAST_UPDATED = SYSDATE
            WHERE INVENTORY_ID = :iid
            """,
            {"avail": avail, "res": reserved, "st": inv_status, "iid": inv_id},
        )

        trx_id = next_pk(cursor, "INVENTORY_TRANSACTION")
        cursor.execute(
            """
            INSERT INTO INVENTORY_TRANSACTION (
                TRANSACTION_ID, INVENTORY_ID, TRANSACTION_TYPE, QUANTITY,
                TRANSACTION_DATE, REFERENCE_TYPE, REFERENCE_ID, PERFORMED_BY, REMARKS
            ) VALUES (
                :tid, :iid, :ttype, :qty, SYSDATE, :rtype, :rid, :perf, :rem
            )
            """,
            {
                "tid": trx_id,
                "iid": inv_id,
                "ttype": trx_type,
                "qty": qty,
                "rtype": ref_type,
                "rid": ref_id,
                "perf": actor.get("full_name", "Operator")[:100],
                "rem": remarks,
            },
        )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "message": f"Transaction #TRX-{trx_id} ({trx_type} {qty} units) committed.",
            "transaction_id": trx_id,
            "quantity_available": avail,
            "quantity_reserved": reserved,
        }), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Recording inventory transaction")


@app.route("/api/warehouses", methods=["GET"])
@permission_required("inventory:view")
def api_warehouses():
    """List certified cold-chain warehouses scoped by user authorization."""
    user = get_current_session_user()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_warehouse_scope_sql(user, warehouse_col="w.WAREHOUSE_ID")
        sql = """
            SELECT w.WAREHOUSE_ID, w.WAREHOUSE_NAME, w.ADDRESS, w.CITY, w.STATE,
                   w.CAPACITY, w.WAREHOUSE_TYPE, w.CERTIFICATION_STATUS, w.MANAGER_NAME,
                   (SELECT COUNT(*) FROM STORAGE_UNIT su WHERE su.WAREHOUSE_ID = w.WAREHOUSE_ID) AS UNITS_COUNT
            FROM WAREHOUSE w
            WHERE 1=1
        """
        if scope_clause:
            sql += f" {scope_clause}"
        sql += " ORDER BY w.WAREHOUSE_ID DESC"
        cursor.execute(sql, scope_params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading warehouses")


@app.route("/api/warehouses", methods=["POST"])
@permission_required("inventory:create")
def api_create_warehouse():
    """Register a cold-storage warehouse facility."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        name = parse_text(body.get("warehouse_name"), "Warehouse Name", 100)
        address = parse_text(body.get("address"), "Address", 200)
        city = parse_text(body.get("city"), "City", 50)
        state = parse_text(body.get("state"), "State", 50)
        capacity = parse_number(body.get("capacity"), "Capacity (Units)", allow_float=False, min_val=100, max_val=50000000)
        w_type = parse_text(body.get("warehouse_type") or "Cold Storage", "Warehouse Type", 50)
        cert = parse_text(body.get("certification_status") or "Certified", "Certification Status", 30)
        manager = parse_text(body.get("manager_name"), "Manager Name", 100)

        conn = get_db_connection()
        cursor = conn.cursor()
        wid = next_pk(cursor, "WAREHOUSE")
        cursor.execute(
            """
            INSERT INTO WAREHOUSE (
                WAREHOUSE_ID, WAREHOUSE_NAME, ADDRESS, CITY, STATE,
                CAPACITY, WAREHOUSE_TYPE, CERTIFICATION_STATUS, MANAGER_NAME
            ) VALUES (
                :wid, :name, :address, :city, :state, :capacity, :w_type, :cert, :manager
            )
            """,
            {
                "wid": wid,
                "name": name,
                "address": address,
                "city": city,
                "state": state,
                "capacity": capacity,
                "w_type": w_type,
                "cert": cert,
                "manager": manager,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Warehouse '{name}' registered.", "warehouse_id": wid}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating warehouse")


@app.route("/api/storage-units", methods=["GET"])
@permission_required("inventory:view")
def api_storage_units():
    """List refrigerated storage chambers and units across warehouses."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT su.STORAGE_UNIT_ID, su.WAREHOUSE_ID, su.UNIT_NAME, su.UNIT_TYPE,
                   su.MINIMUM_TEMPERATURE, su.MAXIMUM_TEMPERATURE, su.CAPACITY,
                   su.CURRENT_STATUS, su.INSTALLATION_DATE,
                   w.WAREHOUSE_NAME, w.CITY
            FROM STORAGE_UNIT su
            LEFT JOIN WAREHOUSE w ON su.WAREHOUSE_ID = w.WAREHOUSE_ID
            ORDER BY su.STORAGE_UNIT_ID DESC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading storage units")


@app.route("/api/storage-units", methods=["POST"])
@permission_required("inventory:create")
def api_create_storage_unit():
    """Add a temperature-controlled storage unit to a warehouse."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        warehouse_id = parse_number(body.get("warehouse_id"), "Warehouse", allow_float=False, min_val=1)
        unit_name = parse_text(body.get("unit_name"), "Storage Unit Name", 100)
        unit_type = parse_text(body.get("unit_type") or "REFRIGERATED", "Unit Type", 50)
        min_t = parse_number(body.get("minimum_temperature"), "Min Temperature (°C)", min_val=-95, max_val=40)
        max_t = parse_number(body.get("maximum_temperature"), "Max Temperature (°C)", min_val=-95, max_val=40)
        capacity = parse_number(body.get("capacity"), "Unit Capacity", allow_float=False, min_val=10, max_val=10000000)
        status = parse_text(body.get("current_status") or "Operational", "Status", 30)

        if min_t > max_t:
            raise ValueError("Min Temperature cannot exceed Max Temperature.")

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "WAREHOUSE", warehouse_id, "Warehouse")

        su_id = next_pk(cursor, "STORAGE_UNIT")
        cursor.execute(
            """
            INSERT INTO STORAGE_UNIT (
                STORAGE_UNIT_ID, WAREHOUSE_ID, UNIT_NAME, UNIT_TYPE,
                MINIMUM_TEMPERATURE, MAXIMUM_TEMPERATURE, CAPACITY, CURRENT_STATUS, INSTALLATION_DATE
            ) VALUES (
                :suid, :wid, :uname, :utype, :mint, :maxt, :cap, :st, TRUNC(SYSDATE)
            )
            """,
            {
                "suid": su_id,
                "wid": warehouse_id,
                "uname": unit_name,
                "utype": unit_type,
                "mint": min_t,
                "maxt": max_t,
                "cap": capacity,
                "st": status,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Storage unit '{unit_name}' added.", "storage_unit_id": su_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating storage unit")


# =============================================================================
# PAGE 6 APIs: Incidents & Compliance
# =============================================================================
@app.route("/api/incidents", methods=["GET"])
@permission_required("incidents:view")
def api_incidents():
    """List cold-chain compliance incidents with corrective actions and resolutions."""
    status = request.args.get("status", "").strip()
    severity = request.args.get("severity", "").strip()
    search = request.args.get("q", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT cci.INCIDENT_ID, cci.ALERT_ID, cci.SHIPMENT_ID, cci.INCIDENT_TYPE,
                   cci.INCIDENT_DATE, cci.DESCRIPTION, cci.SEVERITY, cci.PRODUCT_IMPACT,
                   cci.RESOLUTION_STATUS, cci.RESOLUTION_DATE, cci.CORRECTIVE_ACTION,
                   ta.RECORDED_TEMPERATURE, ta.EXPECTED_MIN, ta.EXPECTED_MAX, ta.ALERT_TYPE,
                   sh.SHIPMENT_STATUS
            FROM COLD_CHAIN_INCIDENT cci
            LEFT JOIN TEMPERATURE_ALERT ta ON cci.ALERT_ID = ta.ALERT_ID
            LEFT JOIN SHIPMENT sh ON cci.SHIPMENT_ID = sh.SHIPMENT_ID
            WHERE 1=1
        """
        params = {}
        if status:
            sql += " AND UPPER(cci.RESOLUTION_STATUS) = :status"
            params["status"] = status.upper()
        if severity:
            sql += " AND UPPER(cci.SEVERITY) = :severity"
            params["severity"] = severity.upper()
        if search:
            sql += " AND (UPPER(cci.INCIDENT_TYPE) LIKE :search OR UPPER(cci.DESCRIPTION) LIKE :search OR UPPER(cci.CORRECTIVE_ACTION) LIKE :search OR TO_CHAR(cci.INCIDENT_ID) LIKE :search)"
            params["search"] = f"%{search.upper()}%"
        sql += " ORDER BY cci.INCIDENT_DATE DESC, cci.INCIDENT_ID DESC"

        cursor.execute(sql, params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading compliance incidents")


@app.route("/api/incidents", methods=["POST"])
@permission_required("incidents:create")
def api_create_incident():
    """Log a cold-chain compliance incident respecting ALERT_ID uniqueness."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        inc_type = parse_text(body.get("incident_type"), "Incident Type", 50)
        inc_date = parse_iso_date(body.get("incident_date") or date.today().isoformat(), "Incident Date")
        severity = parse_text(body.get("severity") or "High", "Severity", 20)
        description = parse_text(body.get("description"), "Incident Description", 500)
        product_impact = parse_text(body.get("product_impact"), "Product Impact Assessment", 300)
        res_status = parse_text(body.get("resolution_status") or "Open", "Resolution Status", 30)
        capa = parse_text(body.get("corrective_action"), "Corrective Action (CAPA)", 500, required=False)
        shipment_id = parse_number(body.get("shipment_id"), "Linked Shipment", required=False, allow_float=False, min_val=1)
        alert_id = parse_number(body.get("alert_id"), "Linked Temperature Alert", required=False, allow_float=False, min_val=1)

        conn = get_db_connection()
        cursor = conn.cursor()
        if shipment_id:
            ensure_fk_exists(cursor, "SHIPMENT", shipment_id, "Shipment")
        if alert_id:
            ensure_fk_exists(cursor, "TEMPERATURE_ALERT", alert_id, "Temperature Alert")
            ensure_unique_value(cursor, "COLD_CHAIN_INCIDENT", "ALERT_ID", alert_id, "Linked Temperature Alert")

        inc_id = next_pk(cursor, "COLD_CHAIN_INCIDENT")
        res_date = date.today() if res_status.upper() == "RESOLVED" else None
        cursor.execute(
            """
            INSERT INTO COLD_CHAIN_INCIDENT (
                INCIDENT_ID, ALERT_ID, SHIPMENT_ID, INCIDENT_TYPE, INCIDENT_DATE,
                DESCRIPTION, SEVERITY, PRODUCT_IMPACT, RESOLUTION_STATUS,
                RESOLUTION_DATE, CORRECTIVE_ACTION
            ) VALUES (
                :iid, :aid, :sid, :itype, :idate,
                :descr, :sev, :impact, :rstatus,
                :rdate, :capa
            )
            """,
            {
                "iid": inc_id,
                "aid": alert_id,
                "sid": shipment_id,
                "itype": inc_type,
                "idate": inc_date,
                "descr": description,
                "sev": severity,
                "impact": product_impact,
                "rstatus": res_status,
                "rdate": res_date,
                "capa": capa,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Incident #INC-{inc_id} logged.", "incident_id": inc_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Logging compliance incident")


@app.route("/api/incidents/<int:incident_id>", methods=["PATCH"])
@permission_required("incidents:transition", "incidents:edit")
def api_update_incident(incident_id):
    """Update incident investigation status, product impact, and corrective action."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        res_status = parse_text(body.get("resolution_status"), "Resolution Status", 30)
        severity = parse_text(body.get("severity"), "Severity", 20)
        product_impact = parse_text(body.get("product_impact"), "Product Impact", 300)
        capa = parse_text(body.get("corrective_action"), "Corrective Action", 500)

        res_date = date.today() if res_status.upper() == "RESOLVED" else None

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "COLD_CHAIN_INCIDENT", incident_id, "Incident")
        cursor.execute(
            """
            UPDATE COLD_CHAIN_INCIDENT
            SET RESOLUTION_STATUS = :rstatus,
                SEVERITY = :sev,
                PRODUCT_IMPACT = :impact,
                CORRECTIVE_ACTION = :capa,
                RESOLUTION_DATE = CASE WHEN UPPER(:rstatus) = 'RESOLVED' THEN NVL(RESOLUTION_DATE, :rdate) ELSE RESOLUTION_DATE END
            WHERE INCIDENT_ID = :iid
            """,
            {
                "rstatus": res_status,
                "sev": severity,
                "impact": product_impact,
                "capa": capa,
                "rdate": res_date,
                "iid": incident_id,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Incident #INC-{incident_id} updated."})
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Updating compliance incident")


# =============================================================================
# PAGE 7 APIs: Deliveries & Distribution (Deliveries, Facilities, Distribution Centers)
# =============================================================================
@app.route("/api/deliveries", methods=["GET"])
@permission_required("deliveries:view")
def api_deliveries():
    """List delivery records with healthcare facilities scoped and masked by user authorization."""
    user = get_current_session_user()
    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_delivery_scope_sql(user, deliv_alias="d")
        sql = """
            SELECT d.DELIVERY_ID, d.SHIPMENT_ID, d.DELIVERY_DATE, d.RECEIVED_BY,
                   d.DELIVERY_STATUS, d.QUANTITY_RECEIVED, d.QUANTITY_DAMAGED,
                   d.PROOF_OF_DELIVERY, d.REMARKS,
                   hf.FACILITY_ID, hf.FACILITY_NAME, hf.FACILITY_TYPE, hf.CITY AS FACILITY_CITY,
                   hf.STATE AS FACILITY_STATE, hf.CONTACT_NUMBER AS FACILITY_PHONE,
                   sh.SHIPMENT_DATE, sh.SHIPMENT_STATUS
            FROM DELIVERY d
            JOIN HEALTHCARE_FACILITY hf ON d.FACILITY_ID = hf.FACILITY_ID
            LEFT JOIN SHIPMENT sh ON d.SHIPMENT_ID = sh.SHIPMENT_ID
            WHERE 1=1
        """
        params = {}
        if scope_clause:
            sql += f" {scope_clause}"
            params.update(scope_params)
        if status:
            sql += " AND UPPER(d.DELIVERY_STATUS) = :status"
            params["status"] = status.upper()
        if search:
            sql += " AND (UPPER(hf.FACILITY_NAME) LIKE :search OR UPPER(d.RECEIVED_BY) LIKE :search OR UPPER(hf.CITY) LIKE :search OR TO_CHAR(d.SHIPMENT_ID) LIKE :search)"
            params["search"] = f"%{search.upper()}%"
        sql += " ORDER BY d.DELIVERY_DATE DESC, d.DELIVERY_ID DESC"

        cursor.execute(sql, params)
        raw_data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        data = sanitize_records_for_user(raw_data, user, "delivery")
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading deliveries")


@app.route("/api/deliveries", methods=["POST"])
@permission_required("deliveries:create")
def api_create_delivery():
    """Record a proof-of-delivery receipt respecting SHIPMENT_ID uniqueness."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        shipment_id = parse_number(body.get("shipment_id"), "Shipment", allow_float=False, min_val=1)
        facility_id = parse_number(body.get("facility_id"), "Healthcare Facility", allow_float=False, min_val=1)
        deliv_date = parse_iso_date(body.get("delivery_date") or date.today().isoformat(), "Delivery Date")
        received_by = parse_text(body.get("received_by"), "Receiving Personnel", 100)
        qty_rec = parse_number(body.get("quantity_received"), "Quantity Received", allow_float=False, min_val=0, max_val=10000000)
        qty_dmg = parse_number(body.get("quantity_damaged") or 0, "Quantity Damaged", allow_float=False, min_val=0, max_val=10000000)
        status = parse_text(body.get("delivery_status") or "Delivered", "Delivery Status", 30)
        pod = parse_text(body.get("proof_of_delivery"), "Proof of Delivery Reference", 300)
        remarks = parse_text(body.get("remarks"), "Audit Remarks", 500, required=False)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "SHIPMENT", shipment_id, "Shipment")
        ensure_fk_exists(cursor, "HEALTHCARE_FACILITY", facility_id, "Healthcare Facility")
        ensure_unique_value(cursor, "DELIVERY", "SHIPMENT_ID", shipment_id, "Shipment Delivery Receipt")

        deliv_id = next_pk(cursor, "DELIVERY")
        cursor.execute(
            """
            INSERT INTO DELIVERY (
                DELIVERY_ID, SHIPMENT_ID, FACILITY_ID, DELIVERY_DATE,
                RECEIVED_BY, DELIVERY_STATUS, QUANTITY_RECEIVED, QUANTITY_DAMAGED,
                PROOF_OF_DELIVERY, REMARKS
            ) VALUES (
                :did, :sid, :fid, :ddate, :rec_by, :st, :qrec, :qdmg, :pod, :rem
            )
            """,
            {
                "did": deliv_id,
                "sid": shipment_id,
                "fid": facility_id,
                "ddate": deliv_date,
                "rec_by": received_by,
                "st": status,
                "qrec": qty_rec,
                "qdmg": qty_dmg,
                "pod": pod,
                "rem": remarks,
            },
        )

        if status.upper() == "DELIVERED":
            cursor.execute(
                """
                UPDATE SHIPMENT
                SET SHIPMENT_STATUS = 'Delivered',
                    ACTUAL_DELIVERY_DATE = NVL(ACTUAL_DELIVERY_DATE, :ddate)
                WHERE SHIPMENT_ID = :sid
                """,
                {"ddate": deliv_date, "sid": shipment_id},
            )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Delivery receipt #DEL-{deliv_id} recorded.", "delivery_id": deliv_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Recording delivery receipt")


@app.route("/api/deliveries/<int:delivery_id>", methods=["PATCH"])
@permission_required("deliveries:transition", "deliveries:edit")
def api_update_delivery(delivery_id):
    """Update delivery receipt status, quantities, or POD reference."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        status = parse_text(body.get("delivery_status"), "Delivery Status", 30)
        qty_rec = parse_number(body.get("quantity_received"), "Quantity Received", allow_float=False, min_val=0, max_val=10000000)
        qty_dmg = parse_number(body.get("quantity_damaged"), "Quantity Damaged", allow_float=False, min_val=0, max_val=10000000)
        pod = parse_text(body.get("proof_of_delivery"), "Proof of Delivery", 300)
        remarks = parse_text(body.get("remarks"), "Remarks", 500, required=False)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_fk_exists(cursor, "DELIVERY", delivery_id, "Delivery")
        cursor.execute(
            """
            UPDATE DELIVERY
            SET DELIVERY_STATUS = :st,
                QUANTITY_RECEIVED = :qrec,
                QUANTITY_DAMAGED = :qdmg,
                PROOF_OF_DELIVERY = :pod,
                REMARKS = :rem
            WHERE DELIVERY_ID = :did
            """,
            {"st": status, "qrec": qty_rec, "qdmg": qty_dmg, "pod": pod, "rem": remarks, "did": delivery_id},
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Delivery #DEL-{delivery_id} updated."})
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Updating delivery")


@app.route("/api/facilities", methods=["GET"])
@permission_required("deliveries:view")
def api_facilities():
    """List recipient healthcare facilities scoped by user authorization."""
    user = get_current_session_user()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        scope_clause, scope_params = build_facility_scope_sql(user, facility_col="hf.FACILITY_ID")
        sql = """
            SELECT hf.FACILITY_ID, hf.FACILITY_NAME, hf.FACILITY_TYPE, hf.LICENSE_NUMBER,
                   hf.ADDRESS, hf.CITY, hf.STATE, hf.CONTACT_NUMBER,
                   hf.STORAGE_CAPABILITY, hf.FACILITY_STATUS,
                   (SELECT COUNT(*) FROM DELIVERY d WHERE d.FACILITY_ID = hf.FACILITY_ID) AS DELIVERIES_COUNT
            FROM HEALTHCARE_FACILITY hf
            WHERE 1=1
        """
        if scope_clause:
            sql += f" {scope_clause}"
        sql += " ORDER BY hf.FACILITY_ID DESC"
        cursor.execute(sql, scope_params)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading healthcare facilities")


@app.route("/api/facilities", methods=["POST"])
@permission_required("deliveries:create")
def api_create_facility():
    """Register a recipient hospital or clinic facility."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        name = parse_text(body.get("facility_name"), "Facility Name", 150)
        f_type = parse_text(body.get("facility_type") or "Multispecialty Hospital", "Facility Type", 50)
        lic = parse_text(body.get("license_number"), "License Number", 50)
        address = parse_text(body.get("address"), "Address", 200)
        city = parse_text(body.get("city"), "City", 50)
        state = parse_text(body.get("state"), "State", 50)
        phone = parse_text(body.get("contact_number"), "Contact Number", 20)
        storage_cap = parse_text(body.get("storage_capability") or "2°C to 8°C Medical Cold Room", "Storage Capability", 100)
        status = parse_text(body.get("facility_status") or "Active", "Status", 30)

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_unique_value(cursor, "HEALTHCARE_FACILITY", "LICENSE_NUMBER", lic, "Facility License Number")

        fid = next_pk(cursor, "HEALTHCARE_FACILITY")
        cursor.execute(
            """
            INSERT INTO HEALTHCARE_FACILITY (
                FACILITY_ID, FACILITY_NAME, FACILITY_TYPE, LICENSE_NUMBER,
                ADDRESS, CITY, STATE, CONTACT_NUMBER, STORAGE_CAPABILITY, FACILITY_STATUS
            ) VALUES (
                :fid, :name, :ftype, :lic, :addr, :city, :state, :phone, :scap, :st
            )
            """,
            {
                "fid": fid,
                "name": name,
                "ftype": f_type,
                "lic": lic,
                "addr": address,
                "city": city,
                "state": state,
                "phone": phone,
                "scap": storage_cap,
                "st": status,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Healthcare facility '{name}' registered.", "facility_id": fid}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Registering healthcare facility")


@app.route("/api/distribution-centers", methods=["GET"])
@permission_required("deliveries:view")
def api_distribution_centers():
    """List regional pharmaceutical distribution centers."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTRIBUTION_CENTER_ID, CENTER_NAME, ADDRESS, CITY, STATE,
                   CAPACITY, CONTACT_NUMBER, MANAGER_NAME, CERTIFICATION_STATUS
            FROM DISTRIBUTION_CENTER
            ORDER BY DISTRIBUTION_CENTER_ID DESC
        """)
        data = rows_to_dicts(cursor)
        cursor.close()
        conn.close()
        return maybe_paginate(data)
    except Exception as exc:
        return safe_api_error(exc, "Loading distribution centers")


@app.route("/api/distribution-centers", methods=["POST"])
@permission_required("deliveries:create")
def api_create_distribution_center():
    """Register a regional distribution center."""
    body = request.get_json(silent=True) or {}
    conn = None
    try:
        name = parse_text(body.get("center_name"), "Center Name", 100)
        address = parse_text(body.get("address"), "Address", 200)
        city = parse_text(body.get("city"), "City", 50)
        state = parse_text(body.get("state"), "State", 50)
        capacity = parse_number(body.get("capacity"), "Capacity (Units)", allow_float=False, min_val=100, max_val=50000000)
        phone = parse_text(body.get("contact_number"), "Contact Number", 20)
        manager = parse_text(body.get("manager_name"), "Manager Name", 100)
        cert = parse_text(body.get("certification_status") or "Certified", "Certification Status", 30)

        conn = get_db_connection()
        cursor = conn.cursor()
        dc_id = next_pk(cursor, "DISTRIBUTION_CENTER")
        cursor.execute(
            """
            INSERT INTO DISTRIBUTION_CENTER (
                DISTRIBUTION_CENTER_ID, CENTER_NAME, ADDRESS, CITY, STATE,
                CAPACITY, CONTACT_NUMBER, MANAGER_NAME, CERTIFICATION_STATUS
            ) VALUES (
                :dcid, :name, :addr, :city, :state, :cap, :phone, :mgr, :cert
            )
            """,
            {
                "dcid": dc_id,
                "name": name,
                "addr": address,
                "city": city,
                "state": state,
                "cap": capacity,
                "phone": phone,
                "mgr": manager,
                "cert": cert,
            },
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": f"Distribution center '{name}' registered.", "distribution_center_id": dc_id}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
            conn.close()
        return safe_api_error(exc, "Creating distribution center")


# =============================================================================
# PAGE 8 APIs: Reports & Analytics + CSV Export
# =============================================================================
@app.route("/api/reports/overview", methods=["GET"])
@permission_required("reports:view")
def api_reports_overview():
    """Return real Oracle analytical reports across logistics, quality, stock, and excursions."""
    expiry_days_raw = request.args.get("expiry_days", "").strip()
    expiry_days = int(expiry_days_raw) if expiry_days_raw.isdigit() else None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        reports = fetch_reports_overview(cursor, rows_to_dicts, expiry_window_days=expiry_days)
        cursor.close()
        conn.close()
        return jsonify(reports)
    except Exception as exc:
        return safe_api_error(exc, "Generating analytical reports")


@app.route("/api/reports/export/<report_key>", methods=["GET"])
@permission_required("reports:export")
def api_export_report_csv(report_key):
    """Export any supported analytical report directly from Oracle as UTF-8 CSV."""
    allowed_keys = {
        "shipment_summary",
        "batch_expiry",
        "inventory_availability",
        "excursion_summary",
        "incident_resolution",
        "delivery_performance",
    }
    if report_key not in allowed_keys:
        return jsonify({"error": "Invalid Report", "message": "Requested report key is not supported."}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        reports = fetch_reports_overview(cursor, rows_to_dicts)
        cursor.close()
        conn.close()

        rows = reports.get(report_key, [])
        output = io.StringIO()
        writer = csv.writer(output)
        if rows:
            headers = list(rows[0].keys())
            writer.writerow([h.upper() for h in headers])
            for r in rows:
                writer.writerow([r.get(h, "") for h in headers])
        else:
            writer.writerow(["NO_RECORDS"])

        filename = f"cryotrack_{report_key}_{date.today().isoformat()}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return safe_api_error(exc, "Exporting CSV report")


# =============================================================================
# PAGE 9 APIs: User & Access Management (Accounts, Invitations, Matrix, Scopes, Audit)
# =============================================================================
@app.route("/api/users", methods=["GET"])
@permission_required("users:manage")
def api_list_users():
    """Return user accounts permitted for viewer (Admins see all; dept managers see dept)."""
    user = get_current_session_user()
    dept = None if user.get("role") == "Administrator" else user.get("department")
    users = list_users_safe(department_filter=dept)
    return jsonify(users)


@app.route("/api/users", methods=["POST"])
@permission_required("users:manage")
def api_admin_create_user():
    """Provision a new CryoTrack user account directly (Administrator only)."""
    actor = get_current_session_user()
    if actor.get("role") != "Administrator":
        return jsonify({"error": "Forbidden", "message": "Direct user creation is restricted to platform Administrators. Use invitations for team onboarding."}), 403

    body = request.get_json(silent=True) or {}
    full_name = (body.get("full_name") or "").strip()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    role = (body.get("role") or "Viewer / Auditor").strip()
    department = (body.get("department") or "Quality Assurance").strip()

    if len(full_name) < 2:
        return jsonify({"error": "Validation Error", "message": "Full name must be at least 2 characters."}), 400

    ok, result = create_or_update_user(email, password, full_name=full_name, role=role, email=email, department=department)
    if not ok:
        return jsonify({"error": "Validation Error", "message": result}), 400
    return jsonify({"message": f"User '{result['email']}' provisioned as {result['role']} in {result['department']}.", "user": result}), 201


@app.route("/api/users/<path:identifier>", methods=["PATCH"])
@permission_required("users:manage")
def api_admin_update_user(identifier):
    """Update user role, status (Active/Disabled), department, or display name."""
    actor = get_current_session_user()
    body = request.get_json(silent=True) or {}
    ok, result = admin_update_user(
        target_identifier=identifier,
        actor_email=actor.get("email"),
        new_role=body.get("role"),
        new_department=body.get("department"),
        new_status=body.get("status"),
        full_name=body.get("full_name"),
    )
    if not ok:
        return jsonify({"error": "Operation Denied", "message": result}), 400
    return jsonify({"message": f"Account '{result['email']}' updated.", "user": result})


@app.route("/api/users/<int:user_id>/approve", methods=["POST"])
@permission_required("users:manage")
def api_approve_user(user_id):
    """Approve a user account stuck in 'Pending Approval' status."""
    actor = get_current_session_user()
    if actor.get("role") != "Administrator":
        return jsonify({"error": "Forbidden", "message": "Account approvals are strictly restricted to Administrators."}), 403

    ok, result = approve_user_account(actor, user_id)
    if not ok:
        return jsonify({"error": "Operation Denied", "message": result}), 400
    return jsonify({"message": result})


@app.route("/api/users/<int:user_id>/scopes", methods=["GET"])
@permission_required("users:manage")
def api_get_user_scopes(user_id):
    """Get assigned record scopes for a user."""
    from auth import get_user_record_scopes
    scopes = get_user_record_scopes(user_id)
    return jsonify({"user_id": user_id, "scopes": scopes})


@app.route("/api/users/<int:user_id>/scopes", methods=["POST"])
@permission_required("users:manage")
def api_assign_user_scopes(user_id):
    """Assign or replace record authorization scopes for a user."""
    from auth import set_user_record_scopes
    actor = get_current_session_user()
    if actor.get("role") != "Administrator":
        return jsonify({"error": "Forbidden", "message": "Only Administrators can modify record authorization scopes."}), 403

    body = request.get_json(silent=True) or {}
    scopes = body.get("scopes", [])
    ok, msg = set_user_record_scopes(actor, user_id, scopes)
    if not ok:
        return jsonify({"error": "Validation Error", "message": msg}), 400
    return jsonify({"message": msg, "user_id": user_id})


@app.route("/api/invitations", methods=["GET"])
@permission_required("invitations:issue")
def api_list_invitations():
    """List invitations within caller's delegation authority."""
    from auth import list_invitations
    actor = get_current_session_user()
    dept = None if actor.get("role") == "Administrator" else actor.get("department")
    invites = list_invitations(department_filter=dept)
    return jsonify(invites)


@app.route("/api/invitations", methods=["POST"])
@permission_required("invitations:issue")
def api_create_invitation():
    """Issue a secure invitation key for onboarding."""
    actor = get_current_session_user()
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    role = (body.get("role") or "Viewer / Auditor").strip()
    department = (body.get("department") or actor.get("department") or "Quality Assurance").strip()
    try:
        raw_days = body.get("expires_in_days")
        if raw_days is None or str(raw_days).strip() == "":
            expires_in_days = 7
        else:
            expires_in_days = int(raw_days)
        if expires_in_days < 1 or expires_in_days > 1825:
            return jsonify({"error": "Validation Error", "message": "Invitation expiration window must be between 1 day and 1825 days (5 years)."}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Validation Error", "message": "Invalid expiration duration parameter."}), 400

    ok, result = issue_invitation(
        actor_user=actor,
        intended_email=email,
        department=department,
        role=role,
        expires_days=expires_in_days,
    )
    if not ok:
        return jsonify({"error": "Invitation Failed", "message": result}), 400
    return jsonify({
        "message": f"Invitation key created for '{result['intended_email']}'.",
        "invitation": result,
    }), 201


@app.route("/api/invitations/<invitation_uuid>/revoke", methods=["POST"])
@permission_required("invitations:issue")
def api_revoke_invitation(invitation_uuid):
    """Revoke an outstanding invitation key."""
    actor = get_current_session_user()
    ok, msg = revoke_invitation(actor, invitation_uuid)
    if not ok:
        return jsonify({"error": "Revocation Failed", "message": msg}), 400
    return jsonify({"message": msg})


@app.route("/api/permissions/matrix", methods=["GET"])
@permission_required("users:manage")
def api_get_permissions_matrix():
    """Return the full 8-role x 31-permission matrix."""
    from auth import get_role_permissions_matrix
    matrix = get_role_permissions_matrix()
    return jsonify(matrix)


@app.route("/api/permissions/role", methods=["POST"])
@permission_required("users:manage")
def api_update_role_permissions():
    """Update permissions assigned to a role (Administrator only)."""
    from auth import set_role_permissions
    actor = get_current_session_user()
    if actor.get("role") != "Administrator":
        return jsonify({"error": "Forbidden", "message": "Only Administrators can modify role permission configurations."}), 403

    body = request.get_json(silent=True) or {}
    role_name = body.get("role")
    permissions = body.get("permissions", [])
    ok, msg = set_role_permissions(actor, role_name, permissions)
    if not ok:
        return jsonify({"error": "Update Failed", "message": msg}), 400
    return jsonify({"message": msg})


@app.route("/api/audit/events", methods=["GET"])
@permission_required("audit:view")
def api_get_audit_events():
    """Fetch immutable security audit trail."""
    from auth import list_audit_events
    actor = get_current_session_user()
    event_type = request.args.get("event_type", "").strip() or None
    limit = int(request.args.get("limit", 100))
    events = list_audit_events(limit=limit, event_type=event_type)
    return jsonify(events)


# =============================================================================
# PAGE 10 APIs: Settings (Own Profile & Password Management)
# =============================================================================
@app.route("/api/settings/profile", methods=["PATCH"])
@login_required
def api_update_own_profile():
    """Update the authenticated user's own display name."""
    if not verify_request_csrf():
        return jsonify({"error": "CSRF Validation Failed", "message": "Invalid security token."}), 403
    actor = get_current_session_user()
    body = request.get_json(silent=True) or {}
    ok, result = update_own_profile(actor.get("email"), body.get("full_name"))
    if not ok:
        return jsonify({"error": "Validation Error", "message": result}), 400
    return jsonify({"message": "Display profile updated.", "user": result})


@app.route("/api/settings/password", methods=["POST"])
@login_required
def api_change_own_password():
    """Change the authenticated user's own password."""
    if not verify_request_csrf():
        return jsonify({"error": "CSRF Validation Failed", "message": "Invalid security token."}), 403
    actor = get_current_session_user()
    body = request.get_json(silent=True) or {}
    ok, msg = change_own_password(
        actor_email=actor.get("email"),
        current_password=body.get("current_password", ""),
        new_password=body.get("new_password", ""),
        confirm_password=body.get("confirm_password", ""),
    )
    if not ok:
        return jsonify({"error": "Validation Error", "message": msg}), 400
    return jsonify({"message": msg})


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    print(f"Starting CryoTrack -- Pharmaceutical Cold-Chain Intelligence Platform on port {port} (Debug: {debug})...")
    app.run(host="0.0.0.0", port=port, debug=debug)
