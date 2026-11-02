"""CryoTrack — Server-Side Authentication, Invitation-Bound Onboarding, Rate Limiting & RBAC Persistence.

Backed by instance/cryotrack_auth.sqlite for zero-dependency, transactional security.
"""
import os
import re
import json
import time
import sqlite3
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import session, request, redirect, url_for, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash

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
)

INSTANCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
AUTH_DB_PATH = os.path.join(INSTANCE_DIR, "cryotrack_auth.sqlite")
LEGACY_USERS_FILE = os.path.join(INSTANCE_DIR, "users.json")

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def ensure_instance_dir():
    """Ensure the local gitignored instance directory exists."""
    if not os.path.exists(INSTANCE_DIR):
        os.makedirs(INSTANCE_DIR, exist_ok=True)


def get_auth_db():
    """Establish and return an optimized SQLite connection with row factory."""
    ensure_instance_dir()
    conn = sqlite3.connect(AUTH_DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_auth_db():
    """Ensure database schema is created and initialized."""
    conn = get_auth_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                department TEXT NOT NULL,
                role TEXT NOT NULL,
                is_department_manager INTEGER NOT NULL DEFAULT 0,
                delegated_roles_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'Pending Verification',
                email_verified INTEGER NOT NULL DEFAULT 0,
                email_verify_token_hash TEXT,
                email_verify_expires_at TEXT,
                approved_by TEXT,
                approved_at TEXT,
                auth_provider TEXT NOT NULL DEFAULT 'local',
                google_sub TEXT,
                password_hash TEXT NOT NULL DEFAULT '',
                session_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invitation_uid TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                intended_email TEXT NOT NULL,
                department TEXT NOT NULL,
                role TEXT NOT NULL,
                is_department_manager INTEGER NOT NULL DEFAULT 0,
                delegated_roles_json TEXT NOT NULL DEFAULT '[]',
                initial_scopes_json TEXT NOT NULL DEFAULT '[]',
                max_uses INTEGER NOT NULL DEFAULT 1,
                uses_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Active',
                expires_at TEXT NOT NULL,
                issued_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                redeemed_at TEXT,
                redeemed_by_user_id INTEGER,
                redeemed_by_email TEXT,
                FOREIGN KEY (redeemed_by_user_id) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role TEXT NOT NULL,
                permission_key TEXT NOT NULL,
                PRIMARY KEY (role, permission_key)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_record_scopes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                scope_type TEXT NOT NULL,
                scope_value TEXT NOT NULL,
                granted_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (user_id, scope_type, scope_value),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bucket_key TEXT NOT NULL,
                created_at_epoch REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_bucket ON rate_limits(bucket_key, created_at_epoch)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                actor_email TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                event_type TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                outcome TEXT NOT NULL,
                ip_address TEXT,
                details_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_time ON audit_events(id DESC)")

        # Initialize default permissions if table is empty
        cnt = conn.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]
        if cnt == 0:
            for role, perms in DEFAULT_ROLE_PERMISSIONS.items():
                for p in perms:
                    conn.execute("INSERT OR IGNORE INTO role_permissions (role, permission_key) VALUES (?, ?)", (role, p))

    conn.close()


# Automatically initialize schema on module import
init_auth_db()


def compute_initials(full_name, email=""):
    """Compute 1-2 uppercase initials for user avatar."""
    cleaned = (full_name or "").strip()
    if cleaned:
        parts = [p for p in cleaned.split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return parts[0][:2].upper()
    if email:
        return email[:2].upper()
    return "CT"


def validate_email_format(email):
    """Validate standard work/institutional email syntax."""
    if not email or len(email) > 150:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_password_strength(password):
    """Enforce password complexity: >= 8 chars, at least 1 letter and 1 number."""
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 128:
        return False, "Password must not exceed 128 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return False, "Password must contain at least one letter and one number."
    return True, ""


# =============================================================================
# Security Logging & Rate Limiting
# =============================================================================
def log_audit_event(actor_email, actor_role, event_type, outcome, target_type=None, target_id=None, ip_address=None, details=None):
    """Record access control or authentication event into audit_events table."""
    try:
        conn = get_auth_db()
        with conn:
            conn.execute("""
                INSERT INTO audit_events
                (event_time, actor_email, actor_role, event_type, target_type, target_id, outcome, ip_address, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.utcnow().isoformat() + "Z",
                actor_email or "anonymous",
                actor_role or "None",
                event_type,
                target_type,
                str(target_id) if target_id is not None else None,
                outcome,
                ip_address or request.remote_addr if request else "system",
                json.dumps(details or {}),
            ))
        conn.close()
    except Exception as exc:
        # Never break application flow if audit write encounters a transient error
        print(f"CryoTrack Audit Logging Warning: {exc}")


def check_rate_limit(bucket_key, max_attempts=5, window_seconds=300):
    """Sliding-window database rate limiter to defend against brute-force attacks."""
    now = time.time()
    cutoff = now - window_seconds
    try:
        conn = get_auth_db()
        with conn:
            # Purge entries older than the evaluation window
            conn.execute("DELETE FROM rate_limits WHERE created_at_epoch < ?", (now - 3600,))
            recent_count = conn.execute(
                "SELECT COUNT(*) FROM rate_limits WHERE bucket_key = ? AND created_at_epoch >= ?",
                (bucket_key, cutoff),
            ).fetchone()[0]

            if recent_count >= max_attempts:
                conn.close()
                return False, int(window_seconds - (now - cutoff))

            conn.execute("INSERT INTO rate_limits (bucket_key, created_at_epoch) VALUES (?, ?)", (bucket_key, now))
        conn.close()
        return True, 0
    except Exception:
        return True, 0


# =============================================================================
# Session Builders & Verification
# =============================================================================
def _load_user_permissions(conn, role):
    """Fetch granted action-level permissions for a specific role."""
    rows = conn.execute("SELECT permission_key FROM role_permissions WHERE role = ?", (role,)).fetchall()
    if rows:
        return [r["permission_key"] for r in rows]
    return list(DEFAULT_ROLE_PERMISSIONS.get(role, []))


def _load_user_scopes(conn, user_id):
    """Fetch record scopes assigned to a user."""
    rows = conn.execute(
        "SELECT scope_type, scope_value FROM user_record_scopes WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return [{"scope_type": r["scope_type"], "scope_value": r["scope_value"]} for r in rows]


def _build_session_payload(user_row, conn=None):
    """Build live sanitized user dictionary for Flask session and templates."""
    should_close = False
    if conn is None:
        conn = get_auth_db()
        should_close = True

    role = normalize_role_name(user_row["role"])
    permissions = _load_user_permissions(conn, role)
    scopes = _load_user_scopes(conn, user_row["id"])

    if should_close:
        conn.close()

    full_name = user_row["full_name"] or "Authorized User"
    email = user_row["email"] or ""

    return {
        "id": user_row["id"],
        "username": user_row["username"],
        "email": email,
        "full_name": full_name,
        "department": user_row["department"],
        "role": role,
        "is_department_manager": bool(user_row["is_department_manager"]),
        "status": user_row["status"],
        "auth_provider": user_row["auth_provider"],
        "session_version": user_row["session_version"],
        "initials": compute_initials(full_name, email),
        "permissions": permissions,
        "record_scopes": scopes,
    }


def get_current_session_user():
    """Return live-verified session user dict, syncing role/status/version from database."""
    sess_user = session.get("user")
    if not sess_user or "id" not in sess_user:
        return None

    conn = get_auth_db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (sess_user["id"],),
    ).fetchone()

    if not row or row["status"] != "Active" or row["session_version"] != sess_user.get("session_version", 1):
        conn.close()
        session.clear()
        return None

    refreshed = _build_session_payload(row, conn)
    conn.close()
    session["user"] = refreshed
    return refreshed


# =============================================================================
# Authentication & Login
# =============================================================================
def authenticate_user(identifier, password, ip_address=None):
    """Authenticate user with email/username and salted password hash."""
    ident = (identifier or "").strip().lower()
    if not ident or not password:
        return None, "Please enter both your work email address and password."

    # Rate limiting on failed login attempts
    rate_key = f"login:{ip_address or 'client'}:{ident}"
    allowed, retry_after = check_rate_limit(rate_key, max_attempts=5, window_seconds=300)
    if not allowed:
        log_audit_event(ident, "None", "LOGIN_RATE_LIMITED", "DENIED", ip_address=ip_address)
        return None, f"Too many failed sign-in attempts. Please wait {retry_after} seconds before trying again."

    conn = get_auth_db()
    row = conn.execute(
        "SELECT * FROM users WHERE LOWER(email) = ? OR LOWER(username) = ?",
        (ident, ident),
    ).fetchone()

    if not row:
        conn.close()
        log_audit_event(ident, "None", "LOGIN_FAILED", "REJECTED", ip_address=ip_address, details={"reason": "User not found"})
        return None, "Invalid email address or password."

    status = row["status"]
    if status == "Pending Approval":
        conn.close()
        log_audit_event(row["email"], row["role"], "LOGIN_BLOCKED", "PENDING_APPROVAL", ip_address=ip_address)
        return None, "Your account is pending administrator approval before access can be granted. Please contact your CryoTrack Administrator."

    if status == "Disabled":
        conn.close()
        log_audit_event(row["email"], row["role"], "LOGIN_BLOCKED", "ACCOUNT_DISABLED", ip_address=ip_address)
        return None, "This CryoTrack account has been deactivated. Please contact your system administrator."

    pwd_hash = row["password_hash"]
    if not pwd_hash:
        conn.close()
        return None, "This account uses Google Sign-In. Please select 'Continue with Google'."

    if not check_password_hash(pwd_hash, password):
        conn.close()
        log_audit_event(row["email"], row["role"], "LOGIN_FAILED", "INVALID_PASSWORD", ip_address=ip_address)
        return None, "Invalid email address or password."

    # Update last login timestamp
    with conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (datetime.utcnow().isoformat() + "Z", row["id"]))

    payload = _build_session_payload(row, conn)
    conn.close()

    log_audit_event(payload["email"], payload["role"], "LOGIN_SUCCESS", "SUCCESS", target_type="user", target_id=payload["id"], ip_address=ip_address)
    return payload, None


# =============================================================================
# Invitation Issuance & Management
# =============================================================================
def issue_invitation(actor_user, intended_email, department, role, max_uses=1, expires_days=7, is_department_manager=False, delegated_roles=None, initial_scopes=None):
    """Issue a secure, cryptographically random onboarding invitation."""
    email_clean = (intended_email or "").strip().lower()
    if not validate_email_format(email_clean):
        return False, "Please provide a valid institutional or work email address."

    if department not in DEPARTMENTS:
        return False, f"Invalid department. Allowed departments: {', '.join(DEPARTMENTS)}."

    if role not in VALID_ROLES:
        return False, f"Invalid access role. Allowed roles: {', '.join(VALID_ROLES)}."
    norm_role = role

    # Verify authorization: Administrator OR Department Manager within permitted boundaries
    actor_role = normalize_role_name(actor_user.get("role"))
    if actor_role != "Administrator":
        if not actor_user.get("is_department_manager"):
            return False, "Only Administrators and authorized Department Managers may issue invitations."
        if actor_user.get("department") != department:
            return False, f"Department Managers may only issue invitations for their own department ({actor_user.get('department')})."
        if norm_role in PRIVILEGED_ROLES:
            return False, "Department Managers cannot delegate privileged Administrator or Operations Manager roles."

    # Generate high-entropy invitation token (format: CT-INV-XXXX-XXXX-XXXX)
    raw_secret = secrets.token_hex(16).upper()
    formatted_token = f"CT-INV-{raw_secret[:4]}-{raw_secret[4:8]}-{raw_secret[8:12]}-{raw_secret[12:16]}"
    token_hash = hashlib.sha256(formatted_token.encode("utf-8")).hexdigest()
    key_prefix = formatted_token[:10]
    inv_uid = f"inv_{secrets.token_hex(6)}"

    expires_at = (datetime.utcnow() + timedelta(days=max(1, int(expires_days)))).isoformat() + "Z"
    now_iso = datetime.utcnow().isoformat() + "Z"

    conn = get_auth_db()
    with conn:
        conn.execute("""
            INSERT INTO invitations
            (invitation_uid, key_prefix, token_hash, intended_email, department, role,
             is_department_manager, delegated_roles_json, initial_scopes_json, max_uses, uses_count,
             status, expires_at, issued_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'Active', ?, ?, ?)
        """, (
            inv_uid,
            key_prefix,
            token_hash,
            email_clean,
            department,
            norm_role,
            1 if is_department_manager else 0,
            json.dumps(delegated_roles or []),
            json.dumps(initial_scopes or []),
            max(1, int(max_uses)),
            expires_at,
            actor_user.get("email"),
            now_iso,
        ))
    conn.close()

    log_audit_event(
        actor_user.get("email"),
        actor_user.get("role"),
        "INVITATION_ISSUED",
        "SUCCESS",
        target_type="invitation",
        target_id=inv_uid,
        details={
            "intended_email": email_clean,
            "department": department,
            "role": norm_role,
            "expires_at": expires_at,
            "max_uses": max_uses,
        },
    )

    return True, {
        "invitation_uid": inv_uid,
        "invitation_key": formatted_token,
        "intended_email": email_clean,
        "department": department,
        "role": norm_role,
        "expires_at": expires_at,
        "max_uses": max_uses,
    }


def revoke_invitation(actor_user, invitation_uid):
    """Revoke an active invitation before it is redeemed."""
    conn = get_auth_db()
    row = conn.execute("SELECT * FROM invitations WHERE invitation_uid = ?", (invitation_uid,)).fetchone()
    if not row:
        conn.close()
        return False, "Invitation not found."

    actor_role = normalize_role_name(actor_user.get("role"))
    if actor_role != "Administrator":
        if not actor_user.get("is_department_manager") or actor_user.get("department") != row["department"]:
            conn.close()
            return False, "Insufficient permissions to revoke this invitation."

    with conn:
        conn.execute("UPDATE invitations SET status = 'Revoked' WHERE invitation_uid = ?", (invitation_uid,))
    conn.close()

    log_audit_event(
        actor_user.get("email"),
        actor_user.get("role"),
        "INVITATION_REVOKED",
        "SUCCESS",
        target_type="invitation",
        target_id=invitation_uid,
    )
    return True, "Invitation has been revoked successfully."


# =============================================================================
# Invitation-Bound Account Redemption & Registration
# =============================================================================
def register_with_invitation(full_name, email, password, confirm_password, raw_invitation_key, ip_address=None):
    """Secure invitation redemption and account provisioning workflow."""
    name_clean = (full_name or "").strip()
    email_clean = (email or "").strip().lower()
    key_clean = (raw_invitation_key or "").strip().upper()

    if len(name_clean) < 2 or len(name_clean) > 100:
        return False, "Full name must be between 2 and 100 characters."
    if not validate_email_format(email_clean):
        return False, "Please enter a valid institutional or work email address."
    if password != confirm_password:
        return False, "Password confirmation does not match."

    valid_pwd, pwd_msg = validate_password_strength(password)
    if not valid_pwd:
        return False, pwd_msg

    if not key_clean:
        return False, "A valid CryoTrack Invitation Key is required to create an account."

    # Rate limiting on invitation redemption
    rate_key = f"redeem:{ip_address or 'client'}:{email_clean}"
    allowed, retry_after = check_rate_limit(rate_key, max_attempts=5, window_seconds=300)
    if not allowed:
        return False, f"Too many registration attempts. Please wait {retry_after} seconds before retrying."

    token_hash = hashlib.sha256(key_clean.encode("utf-8")).hexdigest()

    conn = get_auth_db()
    # Execute redemption atomically with exclusive transaction
    try:
        with conn:
            # Check if email is already registered
            existing_user = conn.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email_clean,)).fetchone()
            if existing_user:
                return False, "An account with this email address is already registered. Please sign in."

            inv = conn.execute("SELECT * FROM invitations WHERE token_hash = ?", (token_hash,)).fetchone()
            if not inv:
                log_audit_event(email_clean, "Applicant", "INVITATION_REJECTED", "INVALID_TOKEN", ip_address=ip_address)
                return False, "The invitation key provided is invalid or unrecognized."

            if inv["status"] != "Active":
                return False, f"This invitation is no longer active (Status: {inv['status']})."

            now_iso = datetime.utcnow().isoformat() + "Z"
            if inv["expires_at"] <= now_iso:
                conn.execute("UPDATE invitations SET status = 'Expired' WHERE id = ?", (inv["id"],))
                return False, "This invitation has expired. Please request a new invitation from your administrator."

            if inv["uses_count"] >= inv["max_uses"]:
                conn.execute("UPDATE invitations SET status = 'Depleted' WHERE id = ?", (inv["id"],))
                return False, "This single-use invitation has already been redeemed."

            # Strict email-binding verification
            if inv["intended_email"].lower() != email_clean:
                log_audit_event(
                    email_clean,
                    "Applicant",
                    "INVITATION_EMAIL_MISMATCH",
                    "REJECTED",
                    target_type="invitation",
                    target_id=inv["invitation_uid"],
                    ip_address=ip_address,
                    details={"intended": inv["intended_email"], "submitted": email_clean},
                )
                return False, f"This invitation was issued specifically for {inv['intended_email']}. The submitted email does not match."

            # Derive Role, Department, and Privileged Status strictly from trusted invitation
            assigned_department = inv["department"]
            assigned_role = normalize_role_name(inv["role"])
            is_dept_mgr = bool(inv["is_department_manager"])

            # Account Activation Policy: Privileged roles require explicit Administrator approval
            is_priv = is_privileged_assignment(assigned_role, is_dept_mgr)
            initial_status = "Pending Approval" if is_priv else "Active"

            base_uname = re.sub(r"[^a-z0-9_]", "_", email_clean.split("@")[0]).strip("_") or "user"
            uname = base_uname
            if conn.execute("SELECT 1 FROM users WHERE username = ?", (uname,)).fetchone():
                uname = f"{base_uname}_{secrets.token_hex(2)}"

            cursor = conn.execute("""
                INSERT INTO users
                (username, email, full_name, department, role, is_department_manager,
                 delegated_roles_json, status, email_verified, auth_provider,
                 password_hash, session_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'local', ?, 1, ?)
            """, (
                uname,
                email_clean,
                name_clean,
                assigned_department,
                assigned_role,
                1 if is_dept_mgr else 0,
                inv["delegated_roles_json"],
                initial_status,
                generate_password_hash(password),
                now_iso,
            ))
            new_user_id = cursor.lastrowid

            # Apply initial record scopes if configured in invitation
            try:
                scopes = json.loads(inv["initial_scopes_json"])
                for sc in scopes:
                    conn.execute("""
                        INSERT OR IGNORE INTO user_record_scopes (user_id, scope_type, scope_value, granted_by, created_at)
                        VALUES (?, ?, ?, 'invitation', ?)
                    """, (new_user_id, sc.get("type", "ALL_RECORDS"), sc.get("value", "*"), now_iso))
            except Exception:
                pass

            # Update invitation usage atomically
            new_uses = inv["uses_count"] + 1
            new_inv_status = "Depleted" if new_uses >= inv["max_uses"] else "Active"
            conn.execute("""
                UPDATE invitations
                SET uses_count = ?, status = ?, redeemed_at = ?, redeemed_by_user_id = ?, redeemed_by_email = ?
                WHERE id = ?
            """, (new_uses, new_inv_status, now_iso, new_user_id, email_clean, inv["id"]))

        log_audit_event(
            email_clean,
            assigned_role,
            "ACCOUNT_PROVISIONED",
            "SUCCESS",
            target_type="user",
            target_id=new_user_id,
            ip_address=ip_address,
            details={
                "department": assigned_department,
                "role": assigned_role,
                "status": initial_status,
                "invitation_uid": inv["invitation_uid"],
            },
        )

        return True, {
            "id": new_user_id,
            "user_id": new_user_id,
            "status": initial_status,
            "role": assigned_role,
            "department": assigned_department,
            "email": email_clean,
            "full_name": name_clean,
        }

    except sqlite3.IntegrityError:
        return False, "A concurrent registration request already redeemed this invitation or registered this email."
    finally:
        conn.close()


# =============================================================================
# Google OAuth 2.0 / OIDC Integration
# =============================================================================
def authenticate_or_provision_google_user(email, full_name, google_sub):
    """Link or sign in a verified Google OpenID Connect claim."""
    email_clean = (email or "").strip().lower()
    if not validate_email_format(email_clean) or not google_sub:
        return None, "Verified Google identity claim was not provided."

    conn = get_auth_db()
    row = conn.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email_clean,)).fetchone()

    if row:
        # Existing account linkage
        if row["status"] != "Active":
            conn.close()
            return None, f"Your CryoTrack account is currently {row['status']}. Please contact an Administrator."

        with conn:
            conn.execute("""
                UPDATE users
                SET google_sub = ?, auth_provider = CASE WHEN password_hash != '' THEN 'hybrid' ELSE 'google' END,
                    last_login_at = ?
                WHERE id = ?
            """, (google_sub, datetime.utcnow().isoformat() + "Z", row["id"]))

        payload = _build_session_payload(row, conn)
        conn.close()
        log_audit_event(email_clean, payload["role"], "LOGIN_SUCCESS", "GOOGLE_OIDC", target_type="user", target_id=payload["id"])
        return payload, None

    # Google self-signup requires invitation verification: prevent uninvited administrative takeover
    conn.close()
    return None, "No CryoTrack account matches this Google email. You must register first with a valid Invitation Key."


# =============================================================================
# Administrative & Governance Operations
# =============================================================================
def list_users_safe(department_filter=None):
    """Return accounts safely for administrative and departmental overview, optionally filtered by department."""
    conn = get_auth_db()
    if department_filter:
        rows = conn.execute("""
            SELECT id, username, email, full_name, department, role, is_department_manager,
                   status, auth_provider, created_at, last_login_at
            FROM users
            WHERE department = ?
            ORDER BY CASE WHEN role = 'Administrator' THEN 0 ELSE 1 END, department ASC, full_name ASC
        """, (department_filter,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, username, email, full_name, department, role, is_department_manager,
                   status, auth_provider, created_at, last_login_at
            FROM users
            ORDER BY CASE WHEN role = 'Administrator' THEN 0 ELSE 1 END, department ASC, full_name ASC
        """).fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "user_id": r["id"],
            "username": r["username"],
            "email": r["email"],
            "full_name": r["full_name"],
            "department": r["department"],
            "role": normalize_role_name(r["role"]),
            "is_department_manager": bool(r["is_department_manager"]),
            "status": r["status"],
            "auth_provider": r["auth_provider"],
            "initials": compute_initials(r["full_name"], r["email"]),
            "created_at": r["created_at"],
            "last_login_at": r["last_login_at"],
        })
    conn.close()
    return result


def approve_user_account(actor_user, target_user_id):
    """Approve a pending privileged or departmental account."""
    conn = get_auth_db()
    target = conn.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
    if not target:
        conn.close()
        return False, "Target user account not found."

    if target["status"] != "Pending Approval":
        conn.close()
        return False, f"Account is not in Pending Approval status (Current: {target['status']})."

    now_iso = datetime.utcnow().isoformat() + "Z"
    with conn:
        conn.execute("""
            UPDATE users
            SET status = 'Active', approved_by = ?, approved_at = ?, session_version = session_version + 1
            WHERE id = ?
        """, (actor_user.get("email"), now_iso, target_user_id))
    conn.close()

    log_audit_event(
        actor_user.get("email"),
        actor_user.get("role"),
        "ACCOUNT_APPROVED",
        "SUCCESS",
        target_type="user",
        target_id=target_user_id,
        details={"approved_email": target["email"], "role": target["role"], "department": target["department"]},
    )
    return True, f"Account for {target['full_name']} has been approved and activated."


def admin_update_user(target_identifier, actor_email, new_role=None, new_status=None, full_name=None, new_department=None):
    """Update user role, status, department, or name with strict lockout safeguards."""
    conn = get_auth_db()
    ident = str(target_identifier).strip().lower()
    target = conn.execute(
        "SELECT * FROM users WHERE LOWER(email) = ? OR LOWER(username) = ? OR id = ?",
        (ident, ident, int(ident) if ident.isdigit() else -1),
    ).fetchone()

    if not target:
        conn.close()
        return False, "Target user account not found."

    is_self = (target["email"].lower() == (actor_email or "").lower())

    updates = {}
    if new_role is not None:
        norm_role = normalize_role_name(new_role)
        if norm_role not in VALID_ROLES:
            conn.close()
            return False, f"Invalid role. Allowed roles: {', '.join(VALID_ROLES)}."
        if is_self and norm_role != "Administrator":
            conn.close()
            return False, "You cannot demote your own active Administrator session."
        if target["role"] == "Administrator" and norm_role != "Administrator" and target["status"] == "Active":
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'Administrator' AND status = 'Active'"
            ).fetchone()[0]
            if active_admins <= 1:
                conn.close()
                return False, "Cannot demote the last remaining active Administrator account."
        updates["role"] = norm_role

    if new_status is not None:
        if new_status not in ("Active", "Disabled", "Pending Approval"):
            conn.close()
            return False, "Invalid account status. Allowed: Active, Disabled, Pending Approval."
        if is_self and new_status != "Active":
            conn.close()
            return False, "You cannot deactivate your own active session."
        if target["role"] == "Administrator" and target["status"] == "Active" and new_status != "Active":
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'Administrator' AND status = 'Active'"
            ).fetchone()[0]
            if active_admins <= 1:
                conn.close()
                return False, "Cannot deactivate the last remaining active Administrator account."
        updates["status"] = new_status

    if new_department is not None:
        if new_department not in DEPARTMENTS:
            conn.close()
            return False, f"Invalid department. Allowed: {', '.join(DEPARTMENTS)}."
        updates["department"] = new_department

    if full_name is not None:
        name_clean = full_name.strip()
        if len(name_clean) < 2 or len(name_clean) > 100:
            conn.close()
            return False, "Full name must be between 2 and 100 characters."
        updates["full_name"] = name_clean

    if not updates:
        conn.close()
        return True, _build_session_payload(target)

    set_clauses = [f"{k} = ?" for k in updates.keys()]
    params = list(updates.values())
    set_clauses.append("session_version = session_version + 1")
    params.append(target["id"])

    with conn:
        conn.execute(f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?", params)

    refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (target["id"],)).fetchone()
    payload = _build_session_payload(refreshed, conn)
    conn.close()

    log_audit_event(
        actor_email,
        "Administrator",
        "USER_UPDATED",
        "SUCCESS",
        target_type="user",
        target_id=target["id"],
        details=updates,
    )
    return True, payload


def create_or_update_user(email_or_username, password, full_name="Authorized User", role="Administrator", email=None, department=None):
    """CLI / Bootstrap helper to create or update an administrator safely."""
    ident = (email_or_username or "").strip().lower()
    if not ident:
        return False, "Identifier is required."

    if "@" in ident:
        resolved_email = ident
        base_uname = re.sub(r"[^a-z0-9_]", "_", ident.split("@")[0]).strip("_") or "user"
    else:
        base_uname = re.sub(r"[^a-z0-9_]", "_", ident).strip("_") or "user"
        resolved_email = (email or f"{base_uname}@cryotrack.io").strip().lower()

    if not validate_email_format(resolved_email):
        return False, "Invalid email address format."

    valid_pwd, pwd_msg = validate_password_strength(password)
    if not valid_pwd:
        return False, pwd_msg

    norm_role = normalize_role_name(role)
    dept = department or ROLE_DEFAULT_DEPARTMENT.get(norm_role, "Administration & Governance")

    conn = get_auth_db()
    now_iso = datetime.utcnow().isoformat() + "Z"
    with conn:
        existing = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = ? OR LOWER(username) = ?",
            (resolved_email, base_uname),
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE users
                SET full_name = ?, department = ?, role = ?, status = 'Active', email_verified = 1,
                    password_hash = ?, session_version = session_version + 1
                WHERE id = ?
            """, (full_name, dept, norm_role, generate_password_hash(password), existing["id"]))
            user_id = existing["id"]
        else:
            cur = conn.execute("""
                INSERT INTO users
                (username, email, full_name, department, role, is_department_manager,
                 status, email_verified, auth_provider, password_hash, session_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'Active', 1, 'local', ?, 1, ?)
            """, (
                base_uname,
                resolved_email,
                full_name,
                dept,
                norm_role,
                1 if norm_role == "Administrator" else 0,
                generate_password_hash(password),
                now_iso,
            ))
            user_id = cur.lastrowid
            # Grant global scope to bootstrap admin
            conn.execute("""
                INSERT OR IGNORE INTO user_record_scopes (user_id, scope_type, scope_value, granted_by, created_at)
                VALUES (?, 'ALL_RECORDS', '*', 'bootstrap', ?)
            """, (user_id, now_iso))

        refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        payload = _build_session_payload(refreshed, conn)

    conn.close()
    return True, payload


# =============================================================================
# Own Profile & Password Operations
# =============================================================================
def update_own_profile(actor_email, full_name):
    """Allow an authenticated user to update their display name."""
    cleaned = (full_name or "").strip()
    if len(cleaned) < 2 or len(cleaned) > 100:
        return False, "Display name must be between 2 and 100 characters."

    conn = get_auth_db()
    with conn:
        conn.execute("UPDATE users SET full_name = ? WHERE LOWER(email) = ?", (cleaned, (actor_email or "").lower()))
        row = conn.execute("SELECT * FROM users WHERE LOWER(email) = ?", ((actor_email or "").lower(),)).fetchone()
        if not row:
            conn.close()
            return False, "Account not found."
        payload = _build_session_payload(row, conn)

    conn.close()
    session["user"] = payload
    return True, payload


def change_own_password(actor_email, current_password, new_password, confirm_password):
    """Allow an authenticated user to change their own password after verifying current credentials."""
    conn = get_auth_db()
    row = conn.execute("SELECT * FROM users WHERE LOWER(email) = ?", ((actor_email or "").lower(),)).fetchone()
    if not row:
        conn.close()
        return False, "Account not found."

    existing_hash = row["password_hash"]
    if existing_hash:
        if not current_password or not check_password_hash(existing_hash, current_password):
            conn.close()
            return False, "Current password is incorrect."

    if new_password != confirm_password:
        conn.close()
        return False, "New password and confirmation do not match."

    valid_pwd, msg = validate_password_strength(new_password)
    if not valid_pwd:
        conn.close()
        return False, msg

    with conn:
        conn.execute("""
            UPDATE users
            SET password_hash = ?, session_version = session_version + 1,
                auth_provider = CASE WHEN google_sub IS NOT NULL THEN 'hybrid' ELSE 'local' END
            WHERE id = ?
        """, (generate_password_hash(new_password), row["id"]))
    conn.close()

    log_audit_event(actor_email, row["role"], "PASSWORD_CHANGED", "SUCCESS", target_type="user", target_id=row["id"])
    return True, "Password updated successfully."


# =============================================================================
# CSRF Token Protection
# =============================================================================
def generate_csrf_token():
    """Generate and persist a cryptographic session CSRF token."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(24)
    return session["csrf_token"]


def validate_csrf_token(token):
    """Constant-time verification of submitted CSRF token."""
    stored = session.get("csrf_token")
    if not stored or not token or not isinstance(token, str):
        return False
    return secrets.compare_digest(stored, token)


def verify_request_csrf():
    """Verify CSRF token from X-CSRF-Token header, form body, or JSON payload."""
    token = request.headers.get("X-CSRF-Token")
    if not token and request.form:
        token = request.form.get("csrf_token")
    if not token and request.is_json:
        body = request.get_json(silent=True) or {}
        token = body.get("csrf_token")
    return validate_csrf_token(token)


# =============================================================================
# Route Protection Decorators
# =============================================================================
def login_required(f):
    """Protect web and API routes against unauthenticated or deactivated sessions."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_session_user()
        if not user:
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Authentication required. Please sign in to CryoTrack."
                }), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(*required_permissions, match_all=False):
    """Enforce fine-grained action permission check on web or API routes."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_session_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Unauthorized",
                        "message": "Authentication required. Please sign in to CryoTrack."
                    }), 401
                return redirect(url_for("login"))

            user_perms = set(user.get("permissions") or [])
            req_set = set(required_permissions)

            has_perm = req_set.issubset(user_perms) if match_all else bool(req_set & user_perms)
            if not has_perm:
                log_audit_event(
                    user.get("email"),
                    user.get("role"),
                    "PERMISSION_DENIED",
                    "FORBIDDEN",
                    details={"required": list(required_permissions), "path": request.path},
                )
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Forbidden",
                        "message": f"Insufficient permissions. Required: {', '.join(required_permissions)}."
                    }), 403
                return render_template(
                    "login.html",
                    error="Insufficient permissions to access that resource.",
                    csrf_token=generate_csrf_token(),
                ), 403

            # Verify CSRF on state-changing API methods
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
                if not verify_request_csrf():
                    return jsonify({
                        "error": "CSRF Validation Failed",
                        "message": "Security token missing or expired. Refresh the page and try again."
                    }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(*allowed_roles):
    """Enforce server-side role check with CSRF protection."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_session_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Unauthorized",
                        "message": "Authentication required. Please sign in to CryoTrack."
                    }), 401
                return redirect(url_for("login"))

            norm_role = normalize_role_name(user.get("role"))
            norm_allowed = [normalize_role_name(r) for r in allowed_roles]

            if norm_role not in norm_allowed:
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Forbidden",
                        "message": f"Insufficient permissions. Required role: {' or '.join(allowed_roles)}."
                    }), 403
                return render_template(
                    "login.html",
                    error="Insufficient permissions to access that resource.",
                    csrf_token=generate_csrf_token(),
                ), 403

            if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
                if not verify_request_csrf():
                    return jsonify({
                        "error": "CSRF Validation Failed",
                        "message": "Security token missing or expired. Refresh the page and try again."
                    }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_role_permissions_matrix():
    from rbac import VALID_ROLES, PERMISSION_CATALOG
    conn = get_auth_db()
    rows = conn.execute("SELECT role, permission_key FROM role_permissions").fetchall()
    conn.close()

    role_perms = {r: set() for r in VALID_ROLES}
    for row in rows:
        if row["role"] in role_perms:
            role_perms[row["role"]].add(row["permission_key"])

    roles_list = []
    for r in VALID_ROLES:
        roles_list.append({
            "name": r,
            "permissions": sorted(list(role_perms[r])),
        })

    perms_list = [
        {"key": p["key"], "name": p.get("label", p["key"]), "category": p.get("group", "General"), "description": p.get("label", "")}
        for p in PERMISSION_CATALOG
    ]

    return {
        "roles": roles_list,
        "permissions": perms_list,
    }


def set_role_permissions(actor_user, role_name, permission_keys):
    from rbac import VALID_ROLES, ALL_PERMISSION_KEYS
    if role_name not in VALID_ROLES:
        return False, "Invalid role specified."
    
    clean_perms = [p for p in permission_keys if p in ALL_PERMISSION_KEYS]
    conn = get_auth_db()
    with conn:
        conn.execute("DELETE FROM role_permissions WHERE role = ?", (role_name,))
        for pk in clean_perms:
            conn.execute("INSERT INTO role_permissions (role, permission_key) VALUES (?, ?)", (role_name, pk))
    conn.close()

    log_audit_event(
        actor_user.get("email"),
        actor_user.get("role"),
        "ROLE_PERMISSIONS_UPDATED",
        "SUCCESS",
        target_type="role",
        target_id=role_name,
        details={"permissions_count": len(clean_perms)},
    )
    return True, f"Permissions for {role_name} successfully updated."


def get_user_record_scopes(target_user_id):
    conn = get_auth_db()
    rows = conn.execute("SELECT id, scope_type, scope_value, granted_by, created_at FROM user_record_scopes WHERE user_id = ?", (target_user_id,)).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "scope_type": r["scope_type"],
            "target_id": r["scope_value"],
            "granted_by": r["granted_by"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def set_user_record_scopes(actor_user, target_user_id, scopes):
    from rbac import RECORD_SCOPE_TYPES
    conn = get_auth_db()
    target = conn.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
    if not target:
        conn.close()
        return False, "Target user not found."

    now_iso = datetime.utcnow().isoformat() + "Z"
    with conn:
        conn.execute("DELETE FROM user_record_scopes WHERE user_id = ?", (target_user_id,))
        for sc in scopes:
            st = sc.get("scope_type")
            sv = str(sc.get("target_id") or sc.get("scope_value") or "*").strip()
            if st in RECORD_SCOPE_TYPES:
                conn.execute(
                    "INSERT INTO user_record_scopes (user_id, scope_type, scope_value, granted_by, created_at) VALUES (?, ?, ?, ?, ?)",
                    (target_user_id, st, sv, actor_user.get("email"), now_iso)
                )
    conn.close()

    log_audit_event(
        actor_user.get("email"),
        actor_user.get("role"),
        "USER_SCOPES_UPDATED",
        "SUCCESS",
        target_type="user",
        target_id=target_user_id,
        details={"scopes_count": len(scopes)},
    )
    return True, f"Record authorization scopes updated for {target['full_name']}."


def list_invitations(department_filter=None):
    """List invitation records optionally filtered by department, transitioning expired records."""
    now_iso = datetime.utcnow().isoformat() + "Z"
    conn = get_auth_db()
    with conn:
        conn.execute("UPDATE invitations SET status = 'Expired' WHERE status = 'Active' AND expires_at <= ?", (now_iso,))
    if department_filter:
        rows = conn.execute(
            "SELECT id, invitation_uid, intended_email, department, role, max_uses, uses_count, status, expires_at, created_at, issued_by FROM invitations WHERE department = ? ORDER BY id DESC",
            (department_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, invitation_uid, intended_email, department, role, max_uses, uses_count, status, expires_at, created_at, issued_by FROM invitations ORDER BY id DESC"
        ).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "invitation_uuid": r["invitation_uid"],
            "intended_email": r["intended_email"],
            "department": r["department"],
            "assigned_role": r["role"],
            "max_uses": r["max_uses"],
            "uses_count": r["uses_count"],
            "status": r["status"],
            "expires_at": r["expires_at"],
            "created_at": r["created_at"],
            "created_by": r["issued_by"],
        })
    return result


def list_audit_events(limit=100, event_type=None):
    """List recent immutable security audit events."""
    conn = get_auth_db()
    if event_type:
        rows = conn.execute(
            "SELECT id, event_time, actor_email, actor_role, event_type, outcome, target_type, target_id, ip_address, details_json FROM audit_events WHERE event_type = ? ORDER BY id DESC LIMIT ?",
            (event_type, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, event_time, actor_email, actor_role, event_type, outcome, target_type, target_id, ip_address, details_json FROM audit_events ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "timestamp": r["event_time"],
            "actor_email": r["actor_email"],
            "actor_role": r["actor_role"],
            "event_type": r["event_type"],
            "status": r["outcome"],
            "target_identifier": f"{r['target_type']}:{r['target_id']}" if r["target_type"] else None,
            "ip_address": r["ip_address"],
            "details": r["details_json"],
        })
    return result
