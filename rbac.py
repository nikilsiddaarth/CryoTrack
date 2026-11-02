"""CryoTrack — Role-Based, Department-Based, Action-Level & Record-Level Authorization."""

DEPARTMENTS = (
    "Administration & Governance",
    "Operations Management",
    "Shipping & Fleet",
    "Cold-Chain Monitoring",
    "Inventory & Warehousing",
    "Quality & Compliance",
    "Deliveries & Distribution",
    "Audit & Oversight",
)

VALID_ROLES = (
    "Administrator",
    "Operations Manager",
    "Shipping & Fleet Operator",
    "Cold-Chain Monitoring Operator",
    "Inventory & Warehouse Operator",
    "Quality & Compliance Operator",
    "Delivery Operator",
    "Viewer / Auditor",
)

ROLE_DEFAULT_DEPARTMENT = {
    "Administrator": "Administration & Governance",
    "Operations Manager": "Operations Management",
    "Shipping & Fleet Operator": "Shipping & Fleet",
    "Cold-Chain Monitoring Operator": "Cold-Chain Monitoring",
    "Inventory & Warehouse Operator": "Inventory & Warehousing",
    "Quality & Compliance Operator": "Quality & Compliance",
    "Delivery Operator": "Deliveries & Distribution",
    "Viewer / Auditor": "Audit & Oversight",
}

PRIVILEGED_ROLES = frozenset({"Administrator", "Operations Manager"})

PRIVILEGED_PERMISSIONS = frozenset({
    "permissions:manage",
    "users:manage",
    "invitations:issue",
    "accounts:approve",
})

RECORD_SCOPE_TYPES = (
    "ALL_RECORDS",
    "WAREHOUSE",
    "SHIPMENT",
    "ROUTE",
    "VEHICLE",
    "FACILITY",
)

PERMISSION_CATALOG = [
    {"key": "command_center:view", "group": "Module Access", "label": "View Cold-Chain Command Center"},
    {"key": "products:view", "group": "Module Access", "label": "View Products & Quality"},
    {"key": "shipments:view", "group": "Module Access", "label": "View Shipments & Fleet"},
    {"key": "monitoring:view", "group": "Module Access", "label": "View Cold-Chain Monitoring"},
    {"key": "inventory:view", "group": "Module Access", "label": "View Inventory & Warehousing"},
    {"key": "incidents:view", "group": "Module Access", "label": "View Incidents & Compliance"},
    {"key": "deliveries:view", "group": "Module Access", "label": "View Deliveries & Distribution"},
    {"key": "reports:view", "group": "Module Access", "label": "View Reports & Analytics"},
    {"key": "products:create", "group": "Products & Quality", "label": "Create Products, Batches, QC Tests & Manufacturers"},
    {"key": "products:edit", "group": "Products & Quality", "label": "Edit Product & Batch Metadata"},
    {"key": "products:transition", "group": "Products & Quality", "label": "Transition Batch & Quality Status"},
    {"key": "shipments:create", "group": "Shipments & Fleet", "label": "Dispatch Shipments & Register Vehicles/Drivers/Routes"},
    {"key": "shipments:edit", "group": "Shipments & Fleet", "label": "Edit Shipment Priority & Fleet Assignments"},
    {"key": "shipments:transition", "group": "Shipments & Fleet", "label": "Transition Shipment Status (Dispatched / Delivered)"},
    {"key": "monitoring:create", "group": "Cold-Chain Monitoring", "label": "Record Telemetry Readings & Register Sensors"},
    {"key": "monitoring:transition", "group": "Cold-Chain Monitoring", "label": "Acknowledge & Resolve Temperature Alerts"},
    {"key": "inventory:create", "group": "Inventory & Warehousing", "label": "Allocate Stock Lots & Register Warehouses/Units"},
    {"key": "inventory:transition", "group": "Inventory & Warehousing", "label": "Execute Stock Movements (In/Out/Reserve/Release)"},
    {"key": "incidents:create", "group": "Incidents & Compliance", "label": "Log & Escalate Compliance Incidents"},
    {"key": "incidents:edit", "group": "Incidents & Compliance", "label": "Update Impact Assessments & CAPA Details"},
    {"key": "incidents:transition", "group": "Incidents & Compliance", "label": "Transition Incident Resolution State"},
    {"key": "deliveries:create", "group": "Deliveries & Distribution", "label": "Record Delivery Receipts (POD) & Register Facilities"},
    {"key": "deliveries:edit", "group": "Deliveries & Distribution", "label": "Edit Delivery Quantities & POD Remarks"},
    {"key": "deliveries:transition", "group": "Deliveries & Distribution", "label": "Transition Delivery Custody Status"},
    {"key": "reports:export", "group": "Analytics & Data Protection", "label": "Export Analytical Reports (CSV)"},
    {"key": "sensitive_fields:view", "group": "Analytics & Data Protection", "label": "Access Sensitive Contact & License Fields"},
    {"key": "users:manage", "group": "Governance & Security", "label": "Manage Users, Roles, Suspension & Record Scopes"},
    {"key": "invitations:issue", "group": "Governance & Security", "label": "Issue & Revoke Onboarding Invitations"},
    {"key": "accounts:approve", "group": "Governance & Security", "label": "Approve Privileged Accounts & Verify Identity"},
    {"key": "permissions:manage", "group": "Governance & Security", "label": "Modify Role-to-Permission Matrix"},
    {"key": "audit:view", "group": "Governance & Security", "label": "Access Security & Operational Audit Logs"},
]

ALL_PERMISSION_KEYS = tuple(p["key"] for p in PERMISSION_CATALOG)

DEFAULT_ROLE_PERMISSIONS = {
    "Administrator": set(ALL_PERMISSION_KEYS),
    "Operations Manager": {
        "command_center:view", "products:view", "shipments:view", "monitoring:view",
        "inventory:view", "incidents:view", "deliveries:view", "reports:view",
        "products:create", "products:edit", "products:transition",
        "shipments:create", "shipments:edit", "shipments:transition",
        "monitoring:create", "monitoring:transition",
        "inventory:create", "inventory:transition",
        "incidents:create", "incidents:edit", "incidents:transition",
        "deliveries:create", "deliveries:edit", "deliveries:transition",
        "reports:export", "sensitive_fields:view", "audit:view",
    },
    "Shipping & Fleet Operator": {
        "command_center:view", "shipments:view", "deliveries:view", "monitoring:view", "incidents:view",
        "shipments:create", "shipments:edit", "shipments:transition",
    },
    "Cold-Chain Monitoring Operator": {
        "command_center:view", "monitoring:view", "shipments:view", "incidents:view",
        "monitoring:create", "monitoring:transition", "incidents:create",
    },
    "Inventory & Warehouse Operator": {
        "command_center:view", "inventory:view", "products:view",
        "inventory:create", "inventory:transition",
    },
    "Quality & Compliance Operator": {
        "command_center:view", "products:view", "incidents:view", "monitoring:view", "reports:view",
        "products:create", "products:edit", "products:transition",
        "incidents:create", "incidents:edit", "incidents:transition",
        "reports:export",
    },
    "Delivery Operator": {
        "command_center:view", "deliveries:view", "shipments:view",
        "deliveries:create", "deliveries:edit", "deliveries:transition",
    },
    "Viewer / Auditor": {
        "command_center:view", "products:view", "shipments:view", "monitoring:view",
        "inventory:view", "incidents:view", "deliveries:view", "reports:view",
    },
}

ROLE_LANDING_TAB = {
    "Administrator": "tab-command-center",
    "Operations Manager": "tab-command-center",
    "Shipping & Fleet Operator": "tab-shipments",
    "Cold-Chain Monitoring Operator": "tab-monitoring",
    "Inventory & Warehouse Operator": "tab-inventory",
    "Quality & Compliance Operator": "tab-products",
    "Delivery Operator": "tab-deliveries",
    "Viewer / Auditor": "tab-command-center",
}

PAGE_PERMISSION_MAP = [
    ("tab-command-center", "command_center:view"),
    ("tab-products", "products:view"),
    ("tab-shipments", "shipments:view"),
    ("tab-monitoring", "monitoring:view"),
    ("tab-inventory", "inventory:view"),
    ("tab-incidents", "incidents:view"),
    ("tab-deliveries", "deliveries:view"),
    ("tab-reports", "reports:view"),
]


def normalize_role_name(raw_role):
    """Normalize legacy or custom role labels to strict CryoTrack RBAC roles."""
    if not raw_role:
        return "Viewer / Auditor"
    cleaned = str(raw_role).strip()
    if cleaned in VALID_ROLES:
        return cleaned
    low = cleaned.lower()
    if low == "administrator" or "admin" in low:
        return "Administrator"
    if low in ("viewer", "auditor", "viewer / auditor"):
        return "Viewer / Auditor"
    if low == "operator" or "operations manager" in low:
        return "Operations Manager"
    if "ship" in low or "fleet" in low:
        return "Shipping & Fleet Operator"
    if "monitor" in low or "sensor" in low or "telemetry" in low:
        return "Cold-Chain Monitoring Operator"
    if "invent" in low or "warehouse" in low:
        return "Inventory & Warehouse Operator"
    if "qualit" in low or "compli" in low:
        return "Quality & Compliance Operator"
    if "deliv" in low or "distribut" in low:
        return "Delivery Operator"
    return "Viewer / Auditor"


def is_privileged_assignment(role, is_department_manager=False, effective_permissions=None):
    """Determine whether an account assignment requires administrator review & approval."""
    norm_role = normalize_role_name(role)
    if norm_role in PRIVILEGED_ROLES or bool(is_department_manager):
        return True
    perms = set(effective_permissions) if effective_permissions else set(DEFAULT_ROLE_PERMISSIONS.get(norm_role, set()))
    return bool(perms & PRIVILEGED_PERMISSIONS)


def compute_allowed_tabs(effective_permissions):
    """Compute the list of tab identifiers accessible under the provided permission set."""
    perms = set(effective_permissions) if effective_permissions else set()
    tabs = [tab_id for tab_id, perm_key in PAGE_PERMISSION_MAP if perm_key in perms]
    if perms & {"users:manage", "invitations:issue", "accounts:approve", "permissions:manage", "audit:view"}:
        tabs.append("tab-users")
    tabs.append("tab-settings")
    return tabs


def resolve_landing_tab(role, effective_permissions):
    """Determine the most relevant authorized landing tab for the authenticated session."""
    allowed = compute_allowed_tabs(effective_permissions)
    norm = normalize_role_name(role)
    preferred = ROLE_LANDING_TAB.get(norm, "tab-command-center")
    if preferred in allowed:
        return preferred
    return allowed[0] if allowed else "tab-settings"


def mask_sensitive_value(val, kind="text"):
    """Partially redact PII / sensitive fields for unauthorized viewers."""
    if val is None or val == "":
        return val
    s = str(val).strip()
    if kind == "email" and "@" in s:
        local, domain = s.split("@", 1)
        prefix = local[:2] if len(local) >= 2 else local[:1]
        return f"{prefix}***@{domain}"
    if len(s) <= 4:
        return "Restricted"
    return f"{s[:2]}***{s[-2:]}"


def sanitize_records_for_user(records, user, entity_kind):
    """Redact sensitive fields in query output if user lacks sensitive_fields:view permission."""
    perms = set((user or {}).get("permissions") or ())
    if "sensitive_fields:view" in perms:
        return records

    masked = []
    for row in records:
        item = dict(row)
        if entity_kind == "driver":
            if "phone" in item:
                item["phone"] = mask_sensitive_value(item.get("phone"), "phone")
            if "driver_phone" in item:
                item["driver_phone"] = mask_sensitive_value(item.get("driver_phone"), "phone")
            if "license_number" in item:
                item["license_number"] = mask_sensitive_value(item.get("license_number"), "license")
        elif entity_kind == "shipment":
            if "driver_phone" in item:
                item["driver_phone"] = mask_sensitive_value(item.get("driver_phone"), "phone")
            if "driver_license" in item:
                item["driver_license"] = mask_sensitive_value(item.get("driver_license"), "license")
        elif entity_kind == "delivery":
            if "recipient_phone" in item:
                item["recipient_phone"] = mask_sensitive_value(item.get("recipient_phone"), "phone")
            if "signature_data" in item:
                item["signature_data"] = "[Secured Signature]"
        masked.append(item)
    return masked


def has_global_record_scope(user):
    """Return True if user possesses ALL_RECORDS scope or Administrator/Operations Manager role."""
    if not user:
        return False
    norm_role = normalize_role_name(user.get("role"))
    if norm_role in PRIVILEGED_ROLES:
        return True
    scopes = user.get("record_scopes") or []
    for sc in scopes:
        if sc.get("scope_type") == "ALL_RECORDS":
            return True
        if sc.get("scope_value") == "*":
            return True
    return False


def get_scope_int_ids(user, scope_type):
    """Retrieve list of integer IDs associated with the specified scope_type."""
    scopes = (user or {}).get("record_scopes") or []
    raw_vals = [sc.get("scope_value") for sc in scopes if sc.get("scope_type") == scope_type]
    ids = []
    for v in raw_vals:
        try:
            if v and str(v).isdigit():
                ids.append(int(v))
        except (ValueError, TypeError):
            continue
    return ids


def _in_clause(column_expr, int_ids, bind_prefix):
    """Build parameterized Oracle IN clause safely."""
    if not int_ids:
        return "1=0", {}
    params = {}
    placeholders = []
    for idx, val in enumerate(int_ids):
        key = f"{bind_prefix}_{idx}"
        placeholders.append(f":{key}")
        params[key] = int(val)
    return f"{column_expr} IN ({', '.join(placeholders)})", params


def build_shipment_scope_sql(user, shipment_alias="s", bind_prefix="sc_shp"):
    """Construct SQL filter clause and bind parameters for shipment scoping."""
    if has_global_record_scope(user):
        return "", {}

    clauses = []
    params = {}

    shp_ids = get_scope_int_ids(user, "SHIPMENT")
    if shp_ids:
        c, p = _in_clause(f"{shipment_alias}.SHIPMENT_ID", shp_ids, f"{bind_prefix}_id")
        clauses.append(c)
        params.update(p)

    rte_ids = get_scope_int_ids(user, "ROUTE")
    if rte_ids:
        c, p = _in_clause(f"{shipment_alias}.ROUTE_ID", rte_ids, f"{bind_prefix}_rte")
        clauses.append(c)
        params.update(p)

    wh_ids = get_scope_int_ids(user, "WAREHOUSE")
    if wh_ids:
        c, p = _in_clause(f"{shipment_alias}.ORIGIN_ID", wh_ids, f"{bind_prefix}_wh")
        clauses.append(f"(UPPER({shipment_alias}.ORIGIN_TYPE) = 'WAREHOUSE' AND {c})")
        params.update(p)

    fac_ids = get_scope_int_ids(user, "FACILITY")
    if fac_ids:
        c, p = _in_clause(f"{shipment_alias}.DESTINATION_ID", fac_ids, f"{bind_prefix}_fac")
        clauses.append(f"(UPPER({shipment_alias}.DESTINATION_TYPE) = 'HEALTHCARE FACILITY' AND {c})")
        params.update(p)

    veh_ids = get_scope_int_ids(user, "VEHICLE")
    if veh_ids:
        c, p = _in_clause("va_sc.VEHICLE_ID", veh_ids, f"{bind_prefix}_veh")
        clauses.append(f"EXISTS (SELECT 1 FROM VEHICLE_ASSIGNMENT va_sc WHERE va_sc.SHIPMENT_ID = {shipment_alias}.SHIPMENT_ID AND {c})")
        params.update(p)

    if not clauses:
        return " AND 1=0", {}
    return f" AND ({' OR '.join(clauses)})", params


def build_warehouse_scope_sql(user, warehouse_col="w.WAREHOUSE_ID", bind_prefix="sc_wh"):
    """Construct SQL filter clause and bind parameters for warehouse scoping."""
    if has_global_record_scope(user):
        return "", {}

    wh_ids = get_scope_int_ids(user, "WAREHOUSE")
    if not wh_ids:
        return " AND 1=0", {}

    c, p = _in_clause(warehouse_col, wh_ids, bind_prefix)
    return f" AND {c}", p


def build_vehicle_scope_sql(user, vehicle_col="v.VEHICLE_ID", bind_prefix="sc_veh"):
    """Construct SQL filter clause and bind parameters for vehicle scoping."""
    if has_global_record_scope(user):
        return "", {}

    veh_ids = get_scope_int_ids(user, "VEHICLE")
    shp_ids = get_scope_int_ids(user, "SHIPMENT")
    clauses = []
    params = {}

    if veh_ids:
        c, p = _in_clause(vehicle_col, veh_ids, f"{bind_prefix}_v")
        clauses.append(c)
        params.update(p)

    if shp_ids:
        c, p = _in_clause("va_vsc.SHIPMENT_ID", shp_ids, f"{bind_prefix}_s")
        clauses.append(f"EXISTS (SELECT 1 FROM VEHICLE_ASSIGNMENT va_vsc WHERE va_vsc.VEHICLE_ID = {vehicle_col} AND {c})")
        params.update(p)

    if not clauses:
        return " AND 1=0", {}
    return f" AND ({' OR '.join(clauses)})", params


def build_route_scope_sql(user, route_col="r.ROUTE_ID", bind_prefix="sc_rte"):
    """Construct SQL filter clause and bind parameters for route scoping."""
    if has_global_record_scope(user):
        return "", {}

    rte_ids = get_scope_int_ids(user, "ROUTE")
    shp_ids = get_scope_int_ids(user, "SHIPMENT")
    clauses = []
    params = {}

    if rte_ids:
        c, p = _in_clause(route_col, rte_ids, f"{bind_prefix}_r")
        clauses.append(c)
        params.update(p)

    if shp_ids:
        c, p = _in_clause("sh_rsc.SHIPMENT_ID", shp_ids, f"{bind_prefix}_s")
        clauses.append(f"EXISTS (SELECT 1 FROM SHIPMENT sh_rsc WHERE sh_rsc.ROUTE_ID = {route_col} AND {c})")
        params.update(p)

    if not clauses:
        return " AND 1=0", {}
    return f" AND ({' OR '.join(clauses)})", params


def build_facility_scope_sql(user, facility_col="hf.FACILITY_ID", bind_prefix="sc_fac"):
    """Construct SQL filter clause and bind parameters for healthcare facility scoping."""
    if has_global_record_scope(user):
        return "", {}

    fac_ids = get_scope_int_ids(user, "FACILITY")
    shp_ids = get_scope_int_ids(user, "SHIPMENT")
    clauses = []
    params = {}

    if fac_ids:
        c, p = _in_clause(facility_col, fac_ids, f"{bind_prefix}_f")
        clauses.append(c)
        params.update(p)

    if shp_ids:
        c, p = _in_clause("d_fsc.SHIPMENT_ID", shp_ids, f"{bind_prefix}_s")
        clauses.append(f"EXISTS (SELECT 1 FROM DELIVERY d_fsc WHERE d_fsc.FACILITY_ID = {facility_col} AND {c})")
        params.update(p)

    if not clauses:
        return " AND 1=0", {}
    return f" AND ({' OR '.join(clauses)})", params


def build_delivery_scope_sql(user, deliv_alias="d", bind_prefix="sc_del"):
    """Construct SQL filter clause and bind parameters for delivery scoping."""
    if has_global_record_scope(user):
        return "", {}

    fac_ids = get_scope_int_ids(user, "FACILITY")
    shp_ids = get_scope_int_ids(user, "SHIPMENT")
    clauses = []
    params = {}

    if fac_ids:
        c, p = _in_clause(f"{deliv_alias}.FACILITY_ID", fac_ids, f"{bind_prefix}_f")
        clauses.append(c)
        params.update(p)

    if shp_ids:
        c, p = _in_clause(f"{deliv_alias}.SHIPMENT_ID", shp_ids, f"{bind_prefix}_s")
        clauses.append(c)
        params.update(p)

    if not clauses:
        return " AND 1=0", {}
    return f" AND ({' OR '.join(clauses)})", params


def build_alert_scope_sql(user, alert_alias="ta", sensor_alias="s", bind_prefix="sc_alt"):
    """Construct SQL filter clause and bind parameters for sensor and alert scoping."""
    if has_global_record_scope(user):
        return "", {}

    shp_ids = get_scope_int_ids(user, "SHIPMENT")
    veh_ids = get_scope_int_ids(user, "VEHICLE")
    clauses = []
    params = {}

    if shp_ids:
        c, p = _in_clause(f"{alert_alias}.SHIPMENT_ID", shp_ids, f"{bind_prefix}_s")
        clauses.append(c)
        params.update(p)

    if veh_ids:
        c, p = _in_clause(f"{sensor_alias}.VEHICLE_ID", veh_ids, f"{bind_prefix}_v")
        clauses.append(c)
        params.update(p)

    if not clauses:
        return " AND 1=0", {}
    return f" AND ({' OR '.join(clauses)})", params


def check_shipment_in_scope(cursor_or_user, user_or_id, shipment_id=None, cursor=None):
    """Verify that a specific shipment ID is within the authenticated user's record scope."""
    if cursor is not None:
        actual_cursor = cursor
        actual_user = cursor_or_user
        actual_shipment_id = user_or_id
    elif shipment_id is not None:
        actual_cursor = cursor_or_user
        actual_user = user_or_id
        actual_shipment_id = shipment_id
    else:
        raise ValueError("Invalid arguments to check_shipment_in_scope")

    if has_global_record_scope(actual_user):
        return True
    clause, params = build_shipment_scope_sql(actual_user, shipment_alias="s", bind_prefix="chk_shp")
    params["target_id"] = int(actual_shipment_id)
    actual_cursor.execute(f"SELECT COUNT(*) FROM SHIPMENT s WHERE s.SHIPMENT_ID = :target_id{clause}", params)
    row = actual_cursor.fetchone()
    return bool(row and row[0] > 0)


def check_warehouse_in_scope(user, warehouse_id):
    """Verify that a warehouse ID is within the user's record scope."""
    if has_global_record_scope(user):
        return True
    return int(warehouse_id) in get_scope_int_ids(user, "WAREHOUSE")


def check_facility_in_scope(user, facility_id):
    """Verify that a facility ID is within the user's record scope."""
    if has_global_record_scope(user):
        return True
    return int(facility_id) in get_scope_int_ids(user, "FACILITY")


def check_vehicle_in_scope(user, vehicle_id):
    """Verify that a vehicle ID is within the user's record scope."""
    if has_global_record_scope(user):
        return True
    return int(vehicle_id) in get_scope_int_ids(user, "VEHICLE")
