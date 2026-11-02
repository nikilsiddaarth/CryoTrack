/* ==========================================================================
   CryoTrack — Pharmaceutical Cold-Chain Intelligence Platform
   Enterprise Frontend Application Controller (Navigation, Tables, Forms, API)
   ========================================================================== */

const CSRF_TOKEN = document.body.dataset.csrfToken || '';
const USER_ROLE = document.body.dataset.userRole || 'Viewer / Auditor';
const USER_EMAIL = document.body.dataset.userEmail || '';
const USER_DEPT = document.body.dataset.userDepartment || '';
const LANDING_TAB = document.body.dataset.landingTab || 'tab-command-center';
let USER_PERMS = [];
try {
  USER_PERMS = JSON.parse(document.body.dataset.userPermissions || '[]');
} catch (e) {
  USER_PERMS = [];
}

function hasPermission(permKey) {
  if (USER_ROLE === 'Administrator') return true;
  return USER_PERMS.includes(permKey);
}

const CAN_WRITE = hasPermission('shipments:create') || hasPermission('inventory:create') || hasPermission('products:create');
const IS_ADMIN = USER_ROLE === 'Administrator';
let currentUsersSubView = 'accounts';

const PAGE_METADATA = {
  'tab-command-center': {
    title: 'Cold-Chain Command Center',
    subtitle: 'Pharmaceutical Logistics & Environmental Intelligence',
  },
  'tab-products': {
    title: 'Products & Quality',
    subtitle: 'Formulations, Production Batches, Quality Control & Storage Conditions',
  },
  'tab-shipments': {
    title: 'Shipments & Fleet',
    subtitle: 'Dispatches, Cargo Manifests, Refrigerated Vehicles, Drivers & Routes',
  },
  'tab-monitoring': {
    title: 'Cold-Chain Monitoring',
    subtitle: 'IoT Sensor Nodes, Recorded Measurements & Excursion Alerts',
  },
  'tab-inventory': {
    title: 'Inventory & Warehousing',
    subtitle: 'Certified Cold Depots, Storage Units, Stock Allocations & Transactions',
  },
  'tab-incidents': {
    title: 'Incidents & Compliance',
    subtitle: 'Deviation Investigations, Linked Excursions & CAPA Resolution',
  },
  'tab-deliveries': {
    title: 'Deliveries & Distribution',
    subtitle: 'Hospital Proof-of-Delivery Receipts, Facilities & Regional Hubs',
  },
  'tab-reports': {
    title: 'Reports & Analytics',
    subtitle: 'SQL-Backed Shelf-Life, Excursion, Stock & Delivery Intelligence',
  },
  'tab-users': {
    title: 'User & Access Management',
    subtitle: 'Account Provisioning, Role-Based Access Governance & Status Control',
  },
  'tab-settings': {
    title: 'Settings',
    subtitle: 'Profile Identity, Credentials, Preferences & Service Health',
  },
};

// In-memory module stores and reusable table state (sort + pagination)
const store = {
  lookups: null,
  products: [],
  batches: [],
  qcTests: [],
  manufacturers: [],
  shipments: [],
  shipItems: [],
  vehicles: [],
  drivers: [],
  routes: [],
  routeStops: [],
  alerts: [],
  sensors: [],
  readings: [],
  inventory: [],
  transactions: [],
  warehouses: [],
  storageUnits: [],
  incidents: [],
  deliveries: [],
  facilities: [],
  distCenters: [],
  reports: null,
  users: [],
};

const tableState = {};
let defaultPageSize = parseInt(localStorage.getItem('cryotrack_page_size') || '15', 10) || 15;
let telemetryChartInstance = null;
let warehouseChartInstance = null;
let excursionChartInstance = null;

/* --------------------------------------------------------------------------
   1. Safe Escaping, Formatting & Toast Helpers
   -------------------------------------------------------------------------- */
function esc(val) {
  if (val === null || val === undefined) return '';
  return String(val)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDate(val) {
  if (!val) return '—';
  const d = new Date(val);
  if (Number.isNaN(d.getTime())) return esc(val);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatDateTime(val) {
  if (!val) return '—';
  const d = new Date(val);
  if (Number.isNaN(d.getTime())) return esc(val);
  return (
    d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) +
    ' ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  );
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function futureIso(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function getStatusBadge(status) {
  if (!status) return '<span class="badge badge-neutral">Unspecified</span>';
  const raw = String(status).trim();
  const s = raw.toUpperCase();
  if (['DELIVERED', 'PASSED', 'AVAILABLE', 'ACTIVE', 'RESOLVED', 'APPROVED', 'CERTIFIED', 'OPERATIONAL', 'COMPLETED'].includes(s)) {
    return `<span class="badge badge-success">&#10003; ${esc(raw)}</span>`;
  }
  if (['IN TRANSIT', 'DISPATCHED', 'IN_TRANSIT', 'PENDING', 'QUARANTINED', 'ASSIGNED', 'UNDER INVESTIGATION', 'UNDER REVIEW', 'RESERVED', 'ACKNOWLEDGED', 'MAINTENANCE'].includes(s)) {
    return `<span class="badge badge-warning">&#9679; ${esc(raw)}</span>`;
  }
  if (['FAILED', 'CRITICAL', 'HIGH', 'EXPIRED', 'OPEN', 'DAMAGED', 'DISABLED', 'INACTIVE', 'DEPLETED'].includes(s)) {
    return `<span class="badge badge-danger">&#9888; ${esc(raw)}</span>`;
  }
  return `<span class="badge badge-info">${esc(raw)}</span>`;
}

function getPriorityBadge(prio) {
  if (!prio) return '—';
  const p = String(prio).trim().toUpperCase();
  if (p === 'HIGH' || p === 'CRITICAL') return `<span class="badge badge-danger">&#9650; ${esc(prio)}</span>`;
  if (p === 'MEDIUM') return `<span class="badge badge-warning">&#9679; ${esc(prio)}</span>`;
  return `<span class="badge badge-neutral">${esc(prio)}</span>`;
}

function showToast(message, variant = 'info') {
  const stack = document.getElementById('toast-stack');
  if (!stack) return;
  const item = document.createElement('div');
  item.className = `toast-item toast-${variant}`;
  item.textContent = message;
  stack.appendChild(item);
  setTimeout(() => {
    item.style.opacity = '0';
    item.style.transition = 'opacity 0.25s ease';
    setTimeout(() => item.remove(), 260);
  }, 4000);
}

function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text)
      .then(function() { showToast("Invitation key copied to clipboard!", "success"); })
      .catch(function() { fallbackCopyText(text); });
  } else {
    fallbackCopyText(text);
  }
}

function fallbackCopyText(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    document.execCommand("copy");
    showToast("Invitation key copied to clipboard!", "success");
  } catch (e) {
    showToast("Failed to copy key automatically. Please select and copy manually.", "warning");
  }
  document.body.removeChild(ta);
}

async function apiRequest(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = Object.assign({ Accept: 'application/json' }, options.headers || {});
  if (method !== 'GET') {
    headers['X-CSRF-Token'] = CSRF_TOKEN;
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
  }
  const res = await fetch(url, Object.assign({}, options, { method, headers }));
  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Authentication required.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.message || data.error || `Request failed (${res.status})`);
  }
  return data;
}

async function ensureLookups(force = false) {
  if (!store.lookups || force) {
    store.lookups = await apiRequest('/api/lookups');
  }
  return store.lookups;
}

/* --------------------------------------------------------------------------
   2. Reusable Sortable + Paginated Enterprise Table Renderer
   -------------------------------------------------------------------------- */
function renderEnterpriseTable({
  containerId,
  tableKey,
  title,
  rows,
  columns,
  emptyText = 'No records match the current filter criteria.',
}) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!tableState[tableKey]) {
    tableState[tableKey] = { sortKey: null, sortDir: 'asc', page: 1 };
  }
  const st = tableState[tableKey];
  let working = Array.isArray(rows) ? [...rows] : [];

  if (st.sortKey) {
    const colDef = columns.find(c => c.key === st.sortKey);
    working.sort((a, b) => {
      let va = colDef && colDef.sortValue ? colDef.sortValue(a) : a[st.sortKey];
      let vb = colDef && colDef.sortValue ? colDef.sortValue(b) : b[st.sortKey];
      if (va === null || va === undefined) va = '';
      if (vb === null || vb === undefined) vb = '';
      if (typeof va === 'number' && typeof vb === 'number') {
        return st.sortDir === 'asc' ? va - vb : vb - va;
      }
      const na = Number(va);
      const nb = Number(vb);
      if (!Number.isNaN(na) && !Number.isNaN(nb) && va !== '' && vb !== '') {
        return st.sortDir === 'asc' ? na - nb : nb - na;
      }
      return st.sortDir === 'asc'
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
  }

  const total = working.length;
  const pageSize = defaultPageSize;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (st.page > totalPages) st.page = totalPages;
  if (st.page < 1) st.page = 1;

  const startIdx = (st.page - 1) * pageSize;
  const pageRows = working.slice(startIdx, startIdx + pageSize);

  const theadHtml = columns
    .map(col => {
      if (col.sortable === false) {
        return `<th>${esc(col.label)}</th>`;
      }
      const isSorted = st.sortKey === col.key;
      const cls = isSorted ? `sortable-th sorted-${st.sortDir}` : 'sortable-th';
      const arrow = isSorted ? (st.sortDir === 'asc' ? '&#9650;' : '&#9660;') : '&#8597;';
      return `<th class="${cls}" onclick="toggleTableSort('${esc(tableKey)}', '${esc(col.key)}')">${esc(col.label)}<span class="sort-indicator">${arrow}</span></th>`;
    })
    .join('');

  const tbodyHtml =
    pageRows.length === 0
      ? `<tr><td colspan="${columns.length}" class="empty-state">${esc(emptyText)}</td></tr>`
      : pageRows
          .map(
            row =>
              `<tr>${columns.map(col => `<td>${col.render ? col.render(row) : esc(row[col.key] ?? '—')}</td>`).join('')}</tr>`
          )
          .join('');

  const rangeStart = total === 0 ? 0 : startIdx + 1;
  const rangeEnd = Math.min(total, startIdx + pageSize);

  let pageBtns = '';
  for (let p = 1; p <= totalPages; p += 1) {
    if (totalPages <= 7 || p === 1 || p === totalPages || Math.abs(p - st.page) <= 1) {
      pageBtns += `<button type="button" class="page-btn ${p === st.page ? 'active' : ''}" onclick="setTablePage('${esc(tableKey)}', ${p})">${p}</button>`;
    } else if (Math.abs(p - st.page) === 2) {
      pageBtns += `<span style="padding:0 0.25rem;">&hellip;</span>`;
    }
  }

  container.innerHTML = `
    <div class="panel-header">
      <div class="panel-title"><span>${esc(title)}</span></div>
      <span class="detail-label">${total.toLocaleString()} record${total === 1 ? '' : 's'}</span>
    </div>
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr>${theadHtml}</tr></thead>
        <tbody>${tbodyHtml}</tbody>
      </table>
    </div>
    <div class="pagination-bar">
      <span>Showing <strong>${rangeStart}–${rangeEnd}</strong> of <strong>${total}</strong></span>
      <div class="pagination-controls">
        <button type="button" class="page-btn" ${st.page <= 1 ? 'disabled' : ''} onclick="setTablePage('${esc(tableKey)}', ${st.page - 1})">Prev</button>
        ${pageBtns}
        <button type="button" class="page-btn" ${st.page >= totalPages ? 'disabled' : ''} onclick="setTablePage('${esc(tableKey)}', ${st.page + 1})">Next</button>
      </div>
    </div>
  `;

  tableState[tableKey]._rerender = () =>
    renderEnterpriseTable({ containerId, tableKey, title, rows, columns, emptyText });
}

function toggleTableSort(tableKey, colKey) {
  const st = tableState[tableKey];
  if (!st) return;
  if (st.sortKey === colKey) {
    st.sortDir = st.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    st.sortKey = colKey;
    st.sortDir = 'asc';
  }
  st.page = 1;
  if (st._rerender) st._rerender();
}

function setTablePage(tableKey, pageNum) {
  const st = tableState[tableKey];
  if (!st) return;
  st.page = pageNum;
  if (st._rerender) st._rerender();
}

/* --------------------------------------------------------------------------
   3. Navigation, Sub-Views, Account Menu & Modal Controls
   -------------------------------------------------------------------------- */
function switchTab(tabId) {
  if (tabId === 'tab-users' && !hasPermission('users:view')) {
    showToast('Access to User & Access Management is restricted.', 'error');
    return;
  }

  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-link-btn').forEach(el => el.classList.remove('active'));

  const target = document.getElementById(tabId);
  if (target) target.classList.add('active');

  const btn = document.querySelector(`.nav-link-btn[data-tab="${tabId}"]`);
  if (btn) btn.classList.add('active');

  const meta = PAGE_METADATA[tabId] || PAGE_METADATA['tab-command-center'];
  const titleEl = document.getElementById('active-header-title');
  const subEl = document.getElementById('active-header-subtitle');
  if (titleEl) titleEl.textContent = meta.title;
  if (subEl) subEl.textContent = meta.subtitle;
  document.title = `${meta.title} — CryoTrack | Pharmaceutical Cold-Chain Intelligence Platform`;

  closeMobileSidebar();

  if (tabId === 'tab-command-center') loadCommandCenter();
  if (tabId === 'tab-products') loadProductsModule();
  if (tabId === 'tab-shipments') loadShipmentsModule();
  if (tabId === 'tab-monitoring') loadMonitoringModule();
  if (tabId === 'tab-inventory') loadInventoryModule();
  if (tabId === 'tab-incidents') loadIncidentsModule();
  if (tabId === 'tab-deliveries') loadDeliveriesModule();
  if (tabId === 'tab-reports') loadReportsModule();
  if (tabId === 'tab-users') loadUsersModule();
  if (tabId === 'tab-settings') checkSystemHealth(false);
}

function switchSubView(group, paneId, btnEl) {
  document.querySelectorAll(`.subview-pane[data-group="${group}"]`).forEach(p => p.classList.remove('active'));
  const target = document.getElementById(paneId);
  if (target) target.classList.add('active');
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.subtab-btn').forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');
  }
}

function openModal(title, htmlContent) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = htmlContent;
  document.getElementById('app-modal').classList.add('active');
}

function closeModal() {
  document.getElementById('app-modal').classList.remove('active');
}

function showFormError(msg) {
  const errEl = document.getElementById('modal-form-error');
  if (errEl) {
    errEl.textContent = msg;
    errEl.style.display = 'block';
  } else {
    showToast(msg, 'error');
  }
}

function closeAccountMenu() {
  const dd = document.getElementById('account-dropdown');
  const btn = document.getElementById('account-menu-btn');
  if (dd) dd.classList.remove('open');
  if (btn) btn.setAttribute('aria-expanded', 'false');
}

function closeMobileSidebar() {
  const sb = document.getElementById('app-sidebar');
  const bd = document.getElementById('sidebar-backdrop');
  if (sb) sb.classList.remove('mobile-open');
  if (bd) bd.classList.remove('active');
}

/* --------------------------------------------------------------------------
   4. PAGE 1: Cold-Chain Command Center
   -------------------------------------------------------------------------- */
async function loadCommandCenter() {
  try {
    const promises = [apiRequest('/api/dashboard/stats')];
    if (hasPermission('shipments:view')) {
      promises.push(apiRequest('/api/shipments').catch(() => []));
    } else {
      promises.push(Promise.resolve([]));
    }
    if (hasPermission('monitoring:view')) {
      promises.push(apiRequest('/api/monitoring/alerts?status=OPEN').catch(() => []));
      promises.push(apiRequest('/api/monitoring/readings').catch(() => []));
    } else {
      promises.push(Promise.resolve([]));
      promises.push(Promise.resolve([]));
    }

    const [stats, shipments, openAlerts, readings] = await Promise.all(promises);

    // Real sensor temperature & humidity summaries (distinguished from latest single sample)
    document.getElementById('card-temp-val').textContent =
      stats.avg_temperature !== null && stats.avg_temperature !== undefined ? Number(stats.avg_temperature).toFixed(1) : '—';
    document.getElementById('card-temp-range').textContent =
      stats.min_temperature !== null && stats.min_temperature !== undefined
        ? `Range: ${stats.min_temperature}°C – ${stats.max_temperature}°C`
        : (hasPermission('monitoring:view') ? 'No sensor readings' : 'Department Scoped');

    document.getElementById('card-humidity-val').textContent =
      stats.avg_humidity !== null && stats.avg_humidity !== undefined ? Number(stats.avg_humidity).toFixed(1) : '—';
    document.getElementById('card-humidity-sub').textContent =
      stats.readings_count !== null && stats.readings_count !== undefined ? `${stats.readings_count} recorded samples` : 'Department Scoped';

    if (stats.latest_temperature !== null && stats.latest_temperature !== undefined) {
      document.getElementById('hero-latest-reading').textContent =
        `${stats.latest_temperature}°C  |  ${stats.latest_humidity}% RH`;
      document.getElementById('hero-latest-meta').textContent =
        `Sensor ${stats.latest_sensor_serial} • ${formatDateTime(stats.latest_reading_time)}`;
    } else {
      document.getElementById('hero-latest-reading').textContent = hasPermission('monitoring:view') ? 'No samples logged' : 'Restricted';
      document.getElementById('hero-latest-meta').textContent = hasPermission('monitoring:view') ? 'Oracle SENSOR_READING empty' : 'Monitoring scope required';
    }

    document.getElementById('stat-in-transit').textContent =
      stats.in_transit_shipments !== null && stats.in_transit_shipments !== undefined ? stats.in_transit_shipments : '—';
    document.getElementById('stat-shipments-sub').textContent =
      stats.delivered_shipments !== null && stats.delivered_shipments !== undefined
        ? `${stats.delivered_shipments} of ${stats.total_shipments} Delivered`
        : 'Department Scoped';

    document.getElementById('stat-alerts').textContent =
      stats.open_alerts !== null && stats.open_alerts !== undefined ? stats.open_alerts : '—';
    document.getElementById('stat-alerts-sub').textContent =
      stats.critical_alerts !== null && stats.critical_alerts !== undefined ? `${stats.critical_alerts} Critical / High` : 'Department Scoped';
    const alertBadge = document.getElementById('stat-alerts-badge');
    if (stats.open_alerts === null || stats.open_alerts === undefined) {
      alertBadge.className = 'badge badge-neutral';
      alertBadge.textContent = 'Scoped';
    } else if (stats.open_alerts === 0) {
      alertBadge.className = 'badge badge-success';
      alertBadge.textContent = 'Clear';
    } else {
      alertBadge.className = 'badge badge-danger';
      alertBadge.textContent = 'Action Req';
    }

    document.getElementById('stat-inventory').textContent =
      stats.inventory_available !== null && stats.inventory_available !== undefined ? Number(stats.inventory_available).toLocaleString() : '—';
    document.getElementById('stat-reserved-sub').textContent =
      stats.inventory_reserved !== null && stats.inventory_reserved !== undefined ? `${Number(stats.inventory_reserved).toLocaleString()} Reserved` : 'Department Scoped';

    // Summary rows & sidebar badges
    document.getElementById('stat-products').textContent =
      stats.products_count !== null && stats.products_count !== undefined ? `${stats.products_count} Formulations` : 'Restricted';
    document.getElementById('stat-batches-sub').textContent =
      stats.available_batches !== null && stats.available_batches !== undefined ? `${stats.available_batches} / ${stats.batches_count} Available` : '—';
    document.getElementById('stat-qc-sub').textContent =
      stats.quality_tests_passed !== null && stats.quality_tests_passed !== undefined ? `${stats.quality_tests_passed} / ${stats.quality_tests_total} Passed` : '—';
    document.getElementById('stat-deliveries-sub').textContent =
      stats.total_units_delivered !== null && stats.total_units_delivered !== undefined ? `${Number(stats.total_units_delivered).toLocaleString()} (${stats.total_units_damaged} Dmg)` : '—';
    document.getElementById('stat-sensors').textContent =
      stats.active_sensors !== null && stats.active_sensors !== undefined ? `${stats.active_sensors} Active Nodes` : 'Restricted';
    document.getElementById('stat-incidents').textContent =
      stats.unresolved_incidents !== null && stats.unresolved_incidents !== undefined ? `${stats.unresolved_incidents} Open` : 'Restricted';

    document.getElementById('badge-prod-count').textContent = stats.products_count !== null && stats.products_count !== undefined ? stats.products_count : '—';
    document.getElementById('badge-ship-count').textContent = stats.total_shipments !== null && stats.total_shipments !== undefined ? stats.total_shipments : '—';
    document.getElementById('badge-alert-count').textContent = stats.open_alerts !== null && stats.open_alerts !== undefined ? stats.open_alerts : '—';
    document.getElementById('badge-incident-count').textContent = stats.unresolved_incidents !== null && stats.unresolved_incidents !== undefined ? stats.unresolved_incidents : '—';

    // System posture indicator
    const ring = document.getElementById('system-status-ring');
    const sTitle = document.getElementById('system-status-title');
    const sDesc = document.getElementById('system-status-desc');
    if (stats.critical_alerts > 0) {
      ring.className = 'status-circle-container alert-state';
      sTitle.textContent = 'Excursion Review Active';
      sDesc.textContent = `${stats.critical_alerts} high/critical temperature excursions and ${stats.unresolved_incidents || 0} open compliance incidents require review.`;
    } else if (stats.open_alerts > 0) {
      ring.className = 'status-circle-container warning-state';
      sTitle.textContent = 'Alerts Under Monitoring';
      sDesc.textContent = `${stats.open_alerts} open alerts logged across active sensor nodes.`;
    } else {
      ring.className = 'status-circle-container';
      sTitle.textContent = 'Cold-Chain Nominal';
      sDesc.textContent = 'All recorded cold-storage units and transit routes remain within certified bounds.';
    }

    // Recent shipments feed
    const shipTbody = document.getElementById('dashboard-shipments-tbody');
    if (!shipments.length) {
      shipTbody.innerHTML = '<tr><td colspan="7" class="empty-state">No shipments recorded.</td></tr>';
    } else {
      shipTbody.innerHTML = shipments.slice(0, 6).map(s => `
        <tr>
          <td><strong class="mono-id">#SHP-${esc(s.shipment_id)}</strong></td>
          <td>${esc(s.origin || '—')} &rarr; ${esc(s.destination || '—')}</td>
          <td><strong>${esc(s.registration_number || 'Unassigned')}</strong></td>
          <td>${esc(s.driver_name || 'Unassigned')}</td>
          <td>${getPriorityBadge(s.priority_level)}</td>
          <td>${getStatusBadge(s.shipment_status)}</td>
          <td>${formatDate(s.expected_delivery_date)}</td>
        </tr>
      `).join('');
    }

    // Open excursions feed
    const alertBox = document.getElementById('dashboard-alerts-container');
    if (!openAlerts.length) {
      alertBox.innerHTML = '<div class="empty-state">No open temperature excursions.</div>';
    } else {
      alertBox.innerHTML = openAlerts.slice(0, 5).map(a => `
        <div class="alert-feed-item severity-${esc((a.severity || 'high').toLowerCase())}">
          <div>
            <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.2rem;">
              <strong>${esc(a.alert_type)}</strong>
              ${getStatusBadge(a.severity)}
            </div>
            <div style="font-size:0.76rem; color:var(--text-muted);">
              Shipment <strong class="mono-id">#SHP-${esc(a.shipment_id || '—')}</strong> &bull; Sensor <code>${esc(a.sensor_serial || '#' + a.sensor_id)}</code><br>
              ${formatDateTime(a.alert_time)}
            </div>
          </div>
          <div style="text-align:right;">
            <span class="temp-pill temp-excursion-hot">${esc(a.recorded_temperature)}°C</span>
            <div style="font-size:0.7rem; color:var(--text-muted); margin-top:0.2rem;">
              Expected: ${esc(a.expected_min)}°C – ${esc(a.expected_max)}°C
            </div>
          </div>
        </div>
      `).join('');
    }

    renderCommandTelemetryChart(readings);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderCommandTelemetryChart(readings) {
  const ctx = document.getElementById('telemetryChart');
  if (!ctx || !window.Chart) return;

  const chronological = [...(readings || [])].slice(0, 20).reverse();
  const labels = chronological.map(r => {
    const d = new Date(r.reading_timestamp);
    return Number.isNaN(d.getTime())
      ? String(r.reading_id)
      : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  });
  const temps = chronological.map(r => Number(r.temperature));

  if (telemetryChartInstance) telemetryChartInstance.destroy();
  telemetryChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Recorded Temp (°C)',
          data: temps,
          borderColor: '#287FE5',
          backgroundColor: 'rgba(112, 217, 240, 0.22)',
          borderWidth: 2.5,
          pointBackgroundColor: '#102D49',
          pointBorderColor: '#70D9F0',
          pointBorderWidth: 1.8,
          pointRadius: 3.6,
          fill: true,
          tension: 0.32,
        },
        {
          label: 'Upper Limit (8°C)',
          data: chronological.map(() => 8.0),
          borderColor: '#B91F3A',
          borderWidth: 1.4,
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false,
        },
        {
          label: 'Lower Limit (2°C)',
          data: chronological.map(() => 2.0),
          borderColor: '#168C83',
          borderWidth: 1.4,
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#526C86', font: { size: 10 }, maxTicksLimit: 7 } },
        y: { grid: { color: '#E5EFFA' }, ticks: { color: '#526C86', font: { size: 11 }, callback: v => `${v}°C` } },
      },
    },
  });
}

/* --------------------------------------------------------------------------
   5. PAGE 2: Products & Quality (Batches, Products, QC Tests, Manufacturers)
   -------------------------------------------------------------------------- */
async function loadProductsModule(forceToast = false) {
  try {
    const [batches, products, qcTests, mfgs] = await Promise.all([
      apiRequest('/api/batches'),
      apiRequest('/api/products'),
      apiRequest('/api/quality-tests'),
      apiRequest('/api/manufacturers'),
    ]);
    store.batches = batches;
    store.products = products;
    store.qcTests = qcTests;
    store.manufacturers = mfgs;
    applyProductsFilter();
    if (forceToast) showToast('Products & Quality records synchronized.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function applyProductsFilter() {
  const q = (document.getElementById('prod-search')?.value || '').toLowerCase().trim();
  const cat = (document.getElementById('prod-category-filter')?.value || '').toLowerCase();
  const bStatus = (document.getElementById('batch-status-filter')?.value || '').toLowerCase();

  const fBatches = store.batches.filter(b => {
    const mq = !q || [b.batch_number, b.product_name, b.manufacturer_name, b.test_type].some(v => v && String(v).toLowerCase().includes(q));
    const mc = !cat || (b.storage_category && b.storage_category.toLowerCase() === cat);
    const ms = !bStatus || (b.batch_status && b.batch_status.toLowerCase() === bStatus);
    return mq && mc && ms;
  });

  renderEnterpriseTable({
    containerId: 'card-batches-table',
    tableKey: 'batches',
    title: 'Production Batches & Latest Quality Verification',
    rows: fBatches,
    columns: [
      { key: 'batch_number', label: 'Batch Number', render: r => `<code>${esc(r.batch_number)}</code>` },
      { key: 'product_name', label: 'Product', render: r => `<strong>${esc(r.product_name)}</strong>` },
      { key: 'manufacturer_name', label: 'Manufacturer' },
      { key: 'manufacturing_date', label: 'Mfg Date', render: r => formatDate(r.manufacturing_date) },
      { key: 'expiry_date', label: 'Expiry Date', render: r => formatDate(r.expiry_date) },
      { key: 'quantity_produced', label: 'Quantity', render: r => `<span class="tabular-nums">${Number(r.quantity_produced || 0).toLocaleString()}</span>` },
      { key: 'batch_status', label: 'Batch Status', render: r => getStatusBadge(r.batch_status) },
      { key: 'quality_status', label: 'Quality Status', render: r => getStatusBadge(r.quality_status) },
      { key: 'test_result', label: 'Latest QC Test', render: r => r.test_type ? `${esc(r.test_type)}: ${getStatusBadge(r.test_result)}` : '<span style="color:var(--text-faint)">No test</span>' },
      {
        key: 'actions',
        label: 'Actions',
        sortable: false,
        render: r => `
          <div style="display:flex; gap:0.35rem;">
            <button class="btn btn-outline btn-sm" onclick="inspectBatch(${r.batch_id})">Inspect</button>
            ${CAN_WRITE ? `<button class="btn btn-outline btn-sm" onclick="openEditBatchModal(${r.batch_id})">Update</button>` : ''}
          </div>
        `,
      },
    ],
  });

  const fProducts = store.products.filter(p => {
    const mq = !q || [p.product_name, p.generic_name, p.manufacturer_name, p.product_type].some(v => v && String(v).toLowerCase().includes(q));
    const mc = !cat || (p.storage_category && p.storage_category.toLowerCase() === cat);
    return mq && mc;
  });

  renderEnterpriseTable({
    containerId: 'card-products-table',
    tableKey: 'products',
    title: 'Pharmaceutical Products & Storage Conditions',
    rows: fProducts,
    columns: [
      { key: 'product_id', label: 'ID', render: r => `<span class="mono-id">#PRD-${r.product_id}</span>` },
      { key: 'product_name', label: 'Product Name', render: r => `<strong>${esc(r.product_name)}</strong><br><small style="color:var(--text-muted)">${esc(r.generic_name || '')}</small>` },
      { key: 'dosage_form', label: 'Dosage & Strength', render: r => `${esc(r.dosage_form || '—')} (${esc(r.strength || '—')})` },
      { key: 'product_type', label: 'Type' },
      { key: 'storage_category', label: 'Category', render: r => `<span class="badge badge-info">${esc(r.storage_category || '—')}</span>` },
      { key: 'minimum_temperature', label: 'Thermal Limits', render: r => r.minimum_temperature !== null ? `<span class="temp-pill temp-normal">${r.minimum_temperature}°C to ${r.maximum_temperature}°C</span>` : 'Ambient' },
      { key: 'shelf_life_days', label: 'Shelf Life', render: r => r.shelf_life_days ? `${r.shelf_life_days} days` : '—' },
      { key: 'manufacturer_name', label: 'Manufacturer' },
      { key: 'regulatory_status', label: 'Regulatory', render: r => getStatusBadge(r.regulatory_status) },
    ],
  });

  const fTests = store.qcTests.filter(t => !q || [t.batch_number, t.product_name, t.test_type, t.tested_by].some(v => v && String(v).toLowerCase().includes(q)));
  renderEnterpriseTable({
    containerId: 'card-qctests-table',
    tableKey: 'qctests',
    title: 'Quality Control Laboratory Tests',
    rows: fTests,
    columns: [
      { key: 'test_id', label: 'Test ID', render: r => `<span class="mono-id">#QT-${r.test_id}</span>` },
      { key: 'batch_number', label: 'Batch', render: r => `<code>${esc(r.batch_number)}</code>` },
      { key: 'product_name', label: 'Product', render: r => `<strong>${esc(r.product_name)}</strong>` },
      { key: 'test_type', label: 'Test Assay' },
      { key: 'test_date', label: 'Test Date', render: r => formatDate(r.test_date) },
      { key: 'test_result', label: 'Result', render: r => getStatusBadge(r.test_result) },
      { key: 'tested_by', label: 'Certified Analyst' },
      { key: 'remarks', label: 'Remarks', render: r => esc(r.remarks || '—') },
    ],
  });

  const fMfgs = store.manufacturers.filter(m => !q || [m.manufacturer_name, m.license_number, m.country, m.regulatory_authority].some(v => v && String(v).toLowerCase().includes(q)));
  renderEnterpriseTable({
    containerId: 'card-mfgs-table',
    tableKey: 'manufacturers',
    title: 'Licensed Pharmaceutical Manufacturers',
    rows: fMfgs,
    columns: [
      { key: 'manufacturer_id', label: 'ID', render: r => `<span class="mono-id">#MFG-${r.manufacturer_id}</span>` },
      { key: 'manufacturer_name', label: 'Manufacturer', render: r => `<strong>${esc(r.manufacturer_name)}</strong>` },
      { key: 'license_number', label: 'License No.', render: r => `<code>${esc(r.license_number)}</code>` },
      { key: 'country', label: 'Country' },
      { key: 'regulatory_authority', label: 'Authority' },
      { key: 'email', label: 'Contact', render: r => `${esc(r.email || '—')}<br><small style="color:var(--text-muted)">${esc(r.contact_number || '')}</small>` },
      { key: 'product_count', label: 'Products', render: r => `<span class="badge badge-neutral">${r.product_count}</span>` },
    ],
  });
}

function inspectBatch(batchId) {
  const b = store.batches.find(x => x.batch_id === batchId);
  if (!b) return;
  openModal(`Batch Audit Record — ${b.batch_number}`, `
    <div class="detail-grid">
      <div class="detail-item"><span class="detail-label">Batch Number</span><span class="detail-value"><code>${esc(b.batch_number)}</code></span></div>
      <div class="detail-item"><span class="detail-label">Product</span><span class="detail-value"><strong>${esc(b.product_name)}</strong> (${esc(b.generic_name || '')})</span></div>
      <div class="detail-item"><span class="detail-label">Manufacturer</span><span class="detail-value">${esc(b.manufacturer_name || '—')}</span></div>
      <div class="detail-item"><span class="detail-label">Storage Category</span><span class="detail-value">${esc(b.storage_category || '—')}</span></div>
      <div class="detail-item"><span class="detail-label">Manufacturing Date</span><span class="detail-value">${formatDate(b.manufacturing_date)}</span></div>
      <div class="detail-item"><span class="detail-label">Expiry Date</span><span class="detail-value">${formatDate(b.expiry_date)}</span></div>
      <div class="detail-item"><span class="detail-label">Quantity Produced</span><span class="detail-value">${Number(b.quantity_produced || 0).toLocaleString()} units</span></div>
      <div class="detail-item"><span class="detail-label">Batch Status</span><span class="detail-value">${getStatusBadge(b.batch_status)}</span></div>
      <div class="detail-item"><span class="detail-label">Quality Status</span><span class="detail-value">${getStatusBadge(b.quality_status)}</span></div>
      <div class="detail-item"><span class="detail-label">Latest Assay</span><span class="detail-value">${esc(b.test_type || 'None')} (${esc(b.test_result || 'N/A')})</span></div>
    </div>
    ${b.test_remarks ? `<div style="margin-top:1rem;"><span class="detail-label">Quality Remarks</span><p style="margin-top:0.35rem; padding:0.75rem; background:var(--bg-subtle); border-radius:8px; font-size:0.84rem;">${esc(b.test_remarks)}</p></div>` : ''}
  `);
}

async function openCreateBatchModal() {
  const lk = await ensureLookups();
  openModal('Create Production Batch', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateBatch(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Pharmaceutical Product <span class="req-star">*</span></label>
          <select id="f-batch-prod" class="form-control" required>
            ${lk.products.map(p => `<option value="${p.product_id}">${esc(p.product_name)} (${esc(p.storage_category)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Batch Number <span class="req-star">*</span></label>
          <input type="text" id="f-batch-num" class="form-control" placeholder="e.g. BATCH-CT-2026-09" required>
        </div>
        <div class="form-field">
          <label>Quantity Produced <span class="req-star">*</span></label>
          <input type="number" id="f-batch-qty" class="form-control" min="1" value="1500" required>
        </div>
        <div class="form-field">
          <label>Manufacturing Date <span class="req-star">*</span></label>
          <input type="date" id="f-batch-mfg" class="form-control" value="${todayIso()}" required>
        </div>
        <div class="form-field">
          <label>Expiry Date <span class="req-star">*</span></label>
          <input type="date" id="f-batch-exp" class="form-control" value="${futureIso(365)}" required>
        </div>
        <div class="form-field">
          <label>Batch Status</label>
          <select id="f-batch-status" class="form-control">
            <option value="Available">Available</option>
            <option value="Reserved">Reserved</option>
            <option value="Quarantined">Quarantined</option>
          </select>
        </div>
        <div class="form-field">
          <label>Quality Status</label>
          <select id="f-batch-qstatus" class="form-control">
            <option value="Passed">Passed</option>
            <option value="Pending">Pending</option>
          </select>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Batch to Oracle</button>
      </div>
    </form>
  `);
}

async function submitCreateBatch(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/batches', {
      method: 'POST',
      body: {
        product_id: document.getElementById('f-batch-prod').value,
        batch_number: document.getElementById('f-batch-num').value,
        quantity_produced: document.getElementById('f-batch-qty').value,
        manufacturing_date: document.getElementById('f-batch-mfg').value,
        expiry_date: document.getElementById('f-batch-exp').value,
        batch_status: document.getElementById('f-batch-status').value,
        quality_status: document.getElementById('f-batch-qstatus').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadProductsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

function openEditBatchModal(batchId) {
  const b = store.batches.find(x => x.batch_id === batchId);
  if (!b) return;
  openModal(`Update Batch Status — ${b.batch_number}`, `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitEditBatch(event, ${b.batch_id})">
      <div class="form-grid">
        <div class="form-field">
          <label>Batch Status <span class="req-star">*</span></label>
          <select id="f-eb-status" class="form-control">
            ${['Available', 'Reserved', 'In Transit', 'Quarantined'].map(s => `<option value="${s}" ${b.batch_status === s ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Quality Status <span class="req-star">*</span></label>
          <select id="f-eb-qstatus" class="form-control">
            ${['Passed', 'Pending', 'Failed'].map(s => `<option value="${s}" ${b.quality_status === s ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Update Batch</button>
      </div>
    </form>
  `);
}

async function submitEditBatch(e, batchId) {
  e.preventDefault();
  try {
    const res = await apiRequest(`/api/batches/${batchId}`, {
      method: 'PATCH',
      body: {
        batch_status: document.getElementById('f-eb-status').value,
        quality_status: document.getElementById('f-eb-qstatus').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await loadProductsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

async function openCreateProductModal() {
  const lk = await ensureLookups();
  openModal('Register Pharmaceutical Product & Storage Condition', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateProduct(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Product Name <span class="req-star">*</span></label>
          <input type="text" id="f-prd-name" class="form-control" placeholder="e.g. CryoVax mRNA Booster" required>
        </div>
        <div class="form-field">
          <label>Generic Name <span class="req-star">*</span></label>
          <input type="text" id="f-prd-gen" class="form-control" placeholder="e.g. Tozinameran Recombinant" required>
        </div>
        <div class="form-field">
          <label>Licensed Manufacturer <span class="req-star">*</span></label>
          <select id="f-prd-mfg" class="form-control" required>
            ${lk.manufacturers.map(m => `<option value="${m.manufacturer_id}">${esc(m.manufacturer_name)} (${esc(m.country)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Product Type <span class="req-star">*</span></label>
          <select id="f-prd-type" class="form-control">
            <option value="Vaccine">Vaccine</option>
            <option value="Biologic">Biologic</option>
            <option value="Antidiabetic">Antidiabetic</option>
            <option value="Antibiotic">Antibiotic</option>
            <option value="Anticoagulant">Anticoagulant</option>
          </select>
        </div>
        <div class="form-field">
          <label>Dosage Form <span class="req-star">*</span></label>
          <input type="text" id="f-prd-dosage" class="form-control" value="Injectable Vial" required>
        </div>
        <div class="form-field">
          <label>Strength <span class="req-star">*</span></label>
          <input type="text" id="f-prd-strength" class="form-control" placeholder="e.g. 30 mcg / 0.3 mL" required>
        </div>
        <div class="form-field">
          <label>Storage Category <span class="req-star">*</span></label>
          <select id="f-prd-cat" class="form-control">
            <option value="Refrigerated">Refrigerated</option>
            <option value="Room Temperature">Room Temperature</option>
          </select>
        </div>
        <div class="form-field">
          <label>Shelf Life (Days) <span class="req-star">*</span></label>
          <input type="number" id="f-prd-shelf" class="form-control" min="1" value="365" required>
        </div>
        <div class="form-field">
          <label>Min Temperature (°C)</label>
          <input type="number" step="0.1" id="f-prd-tmin" class="form-control" value="2.0">
        </div>
        <div class="form-field">
          <label>Max Temperature (°C)</label>
          <input type="number" step="0.1" id="f-prd-tmax" class="form-control" value="8.0">
        </div>
        <div class="form-field full-span">
          <label>Storage Instructions</label>
          <input type="text" id="f-prd-instr" class="form-control" value="Protect from light; do not freeze; keep within 2°C–8°C.">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Create Product</button>
      </div>
    </form>
  `);
}

async function submitCreateProduct(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/products', {
      method: 'POST',
      body: {
        product_name: document.getElementById('f-prd-name').value,
        generic_name: document.getElementById('f-prd-gen').value,
        manufacturer_id: document.getElementById('f-prd-mfg').value,
        product_type: document.getElementById('f-prd-type').value,
        dosage_form: document.getElementById('f-prd-dosage').value,
        strength: document.getElementById('f-prd-strength').value,
        storage_category: document.getElementById('f-prd-cat').value,
        shelf_life_days: document.getElementById('f-prd-shelf').value,
        minimum_temperature: document.getElementById('f-prd-tmin').value,
        maximum_temperature: document.getElementById('f-prd-tmax').value,
        storage_instructions: document.getElementById('f-prd-instr').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadProductsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

async function openCreateTestModal() {
  const lk = await ensureLookups();
  openModal('Log Quality Control Test', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateTest(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Target Batch <span class="req-star">*</span></label>
          <select id="f-qt-batch" class="form-control" required>
            ${lk.batches.map(b => `<option value="${b.batch_id}">${esc(b.batch_number)} — ${esc(b.product_name)}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Test Type / Assay <span class="req-star">*</span></label>
          <input type="text" id="f-qt-type" class="form-control" value="Sterility & Potency Assay" required>
        </div>
        <div class="form-field">
          <label>Test Result <span class="req-star">*</span></label>
          <select id="f-qt-res" class="form-control">
            <option value="Passed">Passed</option>
            <option value="Pending">Pending</option>
            <option value="Failed">Failed</option>
          </select>
        </div>
        <div class="form-field">
          <label>Test Date <span class="req-star">*</span></label>
          <input type="date" id="f-qt-date" class="form-control" value="${todayIso()}" required>
        </div>
        <div class="form-field">
          <label>Certified Analyst <span class="req-star">*</span></label>
          <input type="text" id="f-qt-by" class="form-control" placeholder="Dr. R. Menon, QA Lab" required>
        </div>
        <div class="form-field full-span">
          <label>Laboratory Remarks</label>
          <textarea id="f-qt-rem" class="form-control" placeholder="Endotoxin and thermal stability within USP limits."></textarea>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Record QC Result</button>
      </div>
    </form>
  `);
}

async function submitCreateTest(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/quality-tests', {
      method: 'POST',
      body: {
        batch_id: document.getElementById('f-qt-batch').value,
        test_type: document.getElementById('f-qt-type').value,
        test_result: document.getElementById('f-qt-res').value,
        test_date: document.getElementById('f-qt-date').value,
        tested_by: document.getElementById('f-qt-by').value,
        remarks: document.getElementById('f-qt-rem').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await loadProductsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

function openCreateManufacturerModal() {
  openModal('Register Licensed Manufacturer', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateManufacturer(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Manufacturer Name <span class="req-star">*</span></label>
          <input type="text" id="f-mfg-name" class="form-control" placeholder="Helix BioTherapeutics Ltd." required>
        </div>
        <div class="form-field">
          <label>License Number (Unique) <span class="req-star">*</span></label>
          <input type="text" id="f-mfg-lic" class="form-control" placeholder="LIC-MFG-2026-88" required>
        </div>
        <div class="form-field">
          <label>Country <span class="req-star">*</span></label>
          <input type="text" id="f-mfg-country" class="form-control" value="India" required>
        </div>
        <div class="form-field">
          <label>Regulatory Authority <span class="req-star">*</span></label>
          <input type="text" id="f-mfg-auth" class="form-control" value="CDSCO / WHO-GMP" required>
        </div>
        <div class="form-field">
          <label>Contact Email</label>
          <input type="email" id="f-mfg-email" class="form-control" placeholder="qa@helixbio.example">
        </div>
        <div class="form-field">
          <label>Contact Phone</label>
          <input type="text" id="f-mfg-phone" class="form-control" placeholder="+91-40-23456789">
        </div>
        <div class="form-field full-span">
          <label>Facility Address</label>
          <input type="text" id="f-mfg-addr" class="form-control" placeholder="Genome Valley Biotech Park, Hyderabad">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Manufacturer</button>
      </div>
    </form>
  `);
}

async function submitCreateManufacturer(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/manufacturers', {
      method: 'POST',
      body: {
        manufacturer_name: document.getElementById('f-mfg-name').value,
        license_number: document.getElementById('f-mfg-lic').value,
        country: document.getElementById('f-mfg-country').value,
        regulatory_authority: document.getElementById('f-mfg-auth').value,
        email: document.getElementById('f-mfg-email').value,
        contact_number: document.getElementById('f-mfg-phone').value,
        address: document.getElementById('f-mfg-addr').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadProductsModule();
  } catch (err) {
    showFormError(err.message);
  }
}

/* --------------------------------------------------------------------------
   6. PAGE 3: Shipments & Fleet (Shipments, Items, Vehicles, Drivers, Routes)
   -------------------------------------------------------------------------- */
async function loadShipmentsModule(forceToast = false) {
  try {
    const [shipments, items, vehicles, drivers, routes, stops] = await Promise.all([
      apiRequest('/api/shipments'),
      apiRequest('/api/shipment-items'),
      apiRequest('/api/vehicles'),
      apiRequest('/api/drivers'),
      apiRequest('/api/routes'),
      apiRequest('/api/route-stops'),
    ]);
    store.shipments = shipments;
    store.shipItems = items;
    store.vehicles = vehicles;
    store.drivers = drivers;
    store.routes = routes;
    store.routeStops = stops;
    applyShipmentsFilter();
    if (forceToast) showToast('Shipments & Fleet records synchronized.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function applyShipmentsFilter() {
  const q = (document.getElementById('ship-search')?.value || '').toLowerCase().trim();
  const st = (document.getElementById('ship-status-filter')?.value || '').toLowerCase();
  const pr = (document.getElementById('ship-priority-filter')?.value || '').toLowerCase();

  const fShip = store.shipments.filter(s => {
    const mq = !q || [s.shipment_id, s.origin, s.destination, s.registration_number, s.driver_name].some(v => v && String(v).toLowerCase().includes(q));
    const ms = !st || (s.shipment_status && s.shipment_status.toLowerCase() === st);
    const mp = !pr || (s.priority_level && s.priority_level.toLowerCase() === pr);
    return mq && ms && mp;
  });

  renderEnterpriseTable({
    containerId: 'card-shipments-table',
    tableKey: 'shipments',
    title: 'Cold-Chain Shipment Dispatches & Assignments',
    rows: fShip,
    columns: [
      { key: 'shipment_id', label: 'Shipment', render: r => `<strong class="mono-id">#SHP-${r.shipment_id}</strong>` },
      { key: 'shipment_date', label: 'Ship Date', render: r => formatDate(r.shipment_date) },
      { key: 'expected_delivery_date', label: 'Expected', render: r => formatDate(r.expected_delivery_date) },
      { key: 'origin', label: 'Route', render: r => `<strong>${esc(r.origin || '—')}</strong> &rarr; ${esc(r.destination || '—')}<br><small style="color:var(--text-muted)">${r.total_distance ? r.total_distance + ' km' : ''}</small>` },
      { key: 'registration_number', label: 'Vehicle', render: r => `<strong>${esc(r.registration_number || 'Unassigned')}</strong><br><small style="color:var(--text-muted)">${esc(r.refrigeration_type || '')}</small>` },
      { key: 'driver_name', label: 'Driver', render: r => esc(r.driver_name || 'Unassigned') },
      { key: 'priority_level', label: 'Priority', render: r => getPriorityBadge(r.priority_level) },
      { key: 'shipment_status', label: 'Status', render: r => getStatusBadge(r.shipment_status) },
      { key: 'open_alerts_count', label: 'Alerts', render: r => r.open_alerts_count > 0 ? `<span class="badge badge-danger">&#9888; ${r.open_alerts_count} Open</span>` : '<span class="badge badge-success">&#10003; Clear</span>' },
      {
        key: 'actions',
        label: 'Actions',
        sortable: false,
        render: r => `
          <div style="display:flex; gap:0.35rem;">
            <button class="btn btn-outline btn-sm" onclick="inspectShipmentManifest(${r.shipment_id})">Manifest</button>
            ${CAN_WRITE ? `<button class="btn btn-outline btn-sm" onclick="openUpdateShipmentModal(${r.shipment_id})">Update</button>` : ''}
          </div>
        `,
      },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-shipitems-table',
    tableKey: 'shipitems',
    title: 'Shipment Cargo Items (Batch Manifest Allocations)',
    rows: store.shipItems.filter(i => !q || [i.shipment_id, i.batch_number, i.product_name, i.packaging_type].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'shipment_id', label: 'Shipment', render: r => `<strong class="mono-id">#SHP-${r.shipment_id}</strong>` },
      { key: 'batch_number', label: 'Batch', render: r => `<code>${esc(r.batch_number)}</code>` },
      { key: 'product_name', label: 'Product', render: r => `<strong>${esc(r.product_name)}</strong>` },
      { key: 'quantity', label: 'Quantity', render: r => `<span class="tabular-nums">${Number(r.quantity || 0).toLocaleString()}</span>` },
      { key: 'packaging_type', label: 'Packaging' },
      { key: 'handling_instructions', label: 'Handling Instructions' },
      { key: 'shipment_status', label: 'Transit Status', render: r => getStatusBadge(r.shipment_status) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-vehicles-table',
    tableKey: 'vehicles',
    title: 'Refrigerated Transport Fleet',
    rows: store.vehicles.filter(v => !q || [v.registration_number, v.vehicle_type, v.refrigeration_type].some(x => x && String(x).toLowerCase().includes(q))),
    columns: [
      { key: 'vehicle_id', label: 'ID', render: r => `<span class="mono-id">#VEH-${r.vehicle_id}</span>` },
      { key: 'registration_number', label: 'Registration', render: r => `<code>${esc(r.registration_number)}</code>` },
      { key: 'vehicle_type', label: 'Vehicle Type' },
      { key: 'refrigeration_type', label: 'Cooling System' },
      { key: 'temperature_min', label: 'Thermal Range', render: r => `<span class="temp-pill temp-normal">${r.temperature_min}°C to ${r.temperature_max}°C</span>` },
      { key: 'capacity', label: 'Capacity', render: r => `${Number(r.capacity || 0).toLocaleString()} kg` },
      { key: 'last_maintenance_date', label: 'Last Maintained', render: r => formatDate(r.last_maintenance_date) },
      { key: 'vehicle_status', label: 'Status', render: r => getStatusBadge(r.vehicle_status) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-drivers-table',
    tableKey: 'drivers',
    title: 'GDP-Certified Cold-Chain Drivers',
    rows: store.drivers.filter(d => !q || [d.driver_name, d.license_number, d.certification].some(x => x && String(x).toLowerCase().includes(q))),
    columns: [
      { key: 'driver_id', label: 'ID', render: r => `<span class="mono-id">#DRV-${r.driver_id}</span>` },
      { key: 'driver_name', label: 'Driver Name', render: r => `<strong>${esc(r.driver_name)}</strong>` },
      { key: 'license_number', label: 'License No.', render: r => `<code>${esc(r.license_number)}</code>` },
      { key: 'phone', label: 'Contact Phone' },
      { key: 'certification', label: 'Certification' },
      { key: 'license_expiry', label: 'License Expiry', render: r => formatDate(r.license_expiry) },
      { key: 'trips_count', label: 'Assignments', render: r => `<span class="badge badge-neutral">${r.trips_count}</span>` },
      { key: 'employment_status', label: 'Status', render: r => getStatusBadge(r.employment_status) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-routes-table',
    tableKey: 'routes',
    title: 'Certified Cold-Chain Transit Corridors',
    rows: store.routes.filter(r => !q || [r.origin, r.destination, r.route_type].some(x => x && String(x).toLowerCase().includes(q))),
    columns: [
      { key: 'route_id', label: 'Route ID', render: r => `<span class="mono-id">#RTE-${r.route_id}</span>` },
      { key: 'origin', label: 'Origin', render: r => `<strong>${esc(r.origin)}</strong>` },
      { key: 'destination', label: 'Destination', render: r => `<strong>${esc(r.destination)}</strong>` },
      { key: 'total_distance', label: 'Distance', render: r => `${r.total_distance} km` },
      { key: 'estimated_duration', label: 'Est. Duration', render: r => `${r.estimated_duration} hrs` },
      { key: 'route_type', label: 'Corridor Type' },
      { key: 'stops_count', label: 'Checkpoints', render: r => `<span class="badge badge-info">${r.stops_count} stops</span>` },
      { key: 'route_status', label: 'Status', render: r => getStatusBadge(r.route_status) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-routestops-table',
    tableKey: 'routestops',
    title: 'Route Checkpoints & Scheduled Stops',
    rows: store.routeStops,
    columns: [
      { key: 'route_id', label: 'Route', render: r => `<span class="mono-id">#RTE-${r.route_id}</span> (${esc(r.origin)} &rarr; ${esc(r.destination)})` },
      { key: 'sequence_number', label: 'Seq #' },
      { key: 'stop_name', label: 'Stop Name', render: r => `<strong>${esc(r.stop_name)}</strong>` },
      { key: 'stop_type', label: 'Stop Type' },
      { key: 'planned_arrival', label: 'Planned Arrival', render: r => formatDateTime(r.planned_arrival) },
      { key: 'actual_arrival', label: 'Actual Arrival', render: r => formatDateTime(r.actual_arrival) },
    ],
  });
}

async function inspectShipmentManifest(shipmentId) {
  const s = store.shipments.find(x => x.shipment_id === shipmentId);
  if (!s) return;
  try {
    const details = await apiRequest(`/api/shipments/${shipmentId}/details`);
    const itemsHtml = details.items.length
      ? details.items.map(i => `<li><code>${esc(i.batch_number)}</code> — <strong>${esc(i.product_name)}</strong>: ${Number(i.quantity).toLocaleString()} units (${esc(i.packaging_type || 'Insulated')})</li>`).join('')
      : '<li>No batch items linked to this manifest.</li>';
    const stopsHtml = details.stops.length
      ? details.stops.map(st => `<li>Seq ${st.sequence_number}: <strong>${esc(st.stop_name)}</strong> (${esc(st.stop_type)})</li>`).join('')
      : '<li>Direct corridor — no intermediate stops logged.</li>';

    openModal(`Shipment Manifest — #SHP-${s.shipment_id}`, `
      <div class="detail-grid">
        <div class="detail-item"><span class="detail-label">Status</span><span class="detail-value">${getStatusBadge(s.shipment_status)}</span></div>
        <div class="detail-item"><span class="detail-label">Priority</span><span class="detail-value">${getPriorityBadge(s.priority_level)}</span></div>
        <div class="detail-item"><span class="detail-label">Corridor</span><span class="detail-value">${esc(s.origin || '—')} &rarr; ${esc(s.destination || '—')}</span></div>
        <div class="detail-item"><span class="detail-label">Cargo Weight</span><span class="detail-value">${s.total_weight || '—'} kg</span></div>
        <div class="detail-item"><span class="detail-label">Departure / Expected</span><span class="detail-value">${formatDate(s.shipment_date)} &rarr; ${formatDate(s.expected_delivery_date)}</span></div>
        <div class="detail-item"><span class="detail-label">Vehicle &amp; Driver</span><span class="detail-value">${esc(s.registration_number || 'Unassigned')} / ${esc(s.driver_name || 'Unassigned')}</span></div>
      </div>
      <div style="margin-top:1.1rem;">
        <span class="detail-label">Cargo Batch Allocations</span>
        <ul style="margin:0.4rem 0 0 1.2rem; font-size:0.84rem; line-height:1.6;">${itemsHtml}</ul>
      </div>
      <div style="margin-top:1rem;">
        <span class="detail-label">Route Checkpoints</span>
        <ul style="margin:0.4rem 0 0 1.2rem; font-size:0.84rem; line-height:1.6;">${stopsHtml}</ul>
      </div>
    `);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function openCreateShipmentModal() {
  const lk = await ensureLookups();
  openModal('Dispatch Cold-Chain Shipment', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateShipment(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Transit Route <span class="req-star">*</span></label>
          <select id="f-shp-route" class="form-control" required>
            ${lk.routes.map(r => `<option value="${r.route_id}">#RTE-${r.route_id}: ${esc(r.origin)} → ${esc(r.destination)} (${r.total_distance} km)</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Origin Warehouse <span class="req-star">*</span></label>
          <select id="f-shp-orig" class="form-control" required>
            ${lk.warehouses.map(w => `<option value="${w.warehouse_id}">${esc(w.warehouse_name)} (${esc(w.city)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Destination Facility <span class="req-star">*</span></label>
          <select id="f-shp-dest" class="form-control" required>
            ${lk.facilities.map(f => `<option value="${f.facility_id}">${esc(f.facility_name)} (${esc(f.city)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Shipment Date <span class="req-star">*</span></label>
          <input type="date" id="f-shp-date" class="form-control" value="${todayIso()}" required>
        </div>
        <div class="form-field">
          <label>Expected Delivery Date <span class="req-star">*</span></label>
          <input type="date" id="f-shp-exp" class="form-control" value="${futureIso(2)}" required>
        </div>
        <div class="form-field">
          <label>Priority Level</label>
          <select id="f-shp-prio" class="form-control">
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </div>
        <div class="form-field">
          <label>Total Cargo Weight (kg) <span class="req-star">*</span></label>
          <input type="number" step="0.5" id="f-shp-weight" class="form-control" value="420" min="1" required>
        </div>
        <div class="form-field">
          <label>Assign Refrigerated Vehicle</label>
          <select id="f-shp-veh" class="form-control">
            <option value="">— Optional —</option>
            ${lk.vehicles.map(v => `<option value="${v.vehicle_id}">${esc(v.registration_number)} (${esc(v.vehicle_type)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Assign Certified Driver</label>
          <select id="f-shp-drv" class="form-control">
            <option value="">— Optional —</option>
            ${lk.drivers.map(d => `<option value="${d.driver_id}">${esc(d.driver_name)} (${esc(d.license_number)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Allocate Cargo Batch</label>
          <select id="f-shp-batch" class="form-control">
            <option value="">— Optional —</option>
            ${lk.batches.map(b => `<option value="${b.batch_id}">${esc(b.batch_number)} — ${esc(b.product_name)}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Cargo Batch Quantity</label>
          <input type="number" id="f-shp-bqty" class="form-control" value="250" min="1">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Dispatch Shipment</button>
      </div>
    </form>
  `);
}

async function submitCreateShipment(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/shipments', {
      method: 'POST',
      body: {
        route_id: document.getElementById('f-shp-route').value,
        origin_id: document.getElementById('f-shp-orig').value,
        destination_id: document.getElementById('f-shp-dest').value,
        shipment_date: document.getElementById('f-shp-date').value,
        expected_delivery_date: document.getElementById('f-shp-exp').value,
        priority_level: document.getElementById('f-shp-prio').value,
        total_weight: document.getElementById('f-shp-weight').value,
        vehicle_id: document.getElementById('f-shp-veh').value || null,
        driver_id: document.getElementById('f-shp-drv').value || null,
        batch_id: document.getElementById('f-shp-batch').value || null,
        item_quantity: document.getElementById('f-shp-bqty').value || null,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadShipmentsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

async function openUpdateShipmentModal(shipmentId) {
  const s = store.shipments.find(x => x.shipment_id === shipmentId);
  if (!s) return;
  const lk = await ensureLookups();
  openModal(`Update Shipment & Assignment — #SHP-${s.shipment_id}`, `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitUpdateShipment(event, ${s.shipment_id})">
      <div class="form-grid">
        <div class="form-field">
          <label>Shipment Status <span class="req-star">*</span></label>
          <select id="f-ushp-status" class="form-control">
            ${['Dispatched', 'Delivered'].map(st => `<option value="${st}" ${s.shipment_status === st ? 'selected' : ''}>${st}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Priority Level <span class="req-star">*</span></label>
          <select id="f-ushp-prio" class="form-control">
            ${['High', 'Medium', 'Low'].map(p => `<option value="${p}" ${s.priority_level === p ? 'selected' : ''}>${p}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Assigned Vehicle</label>
          <select id="f-ushp-veh" class="form-control">
            <option value="">— Keep / Unchanged —</option>
            ${lk.vehicles.map(v => `<option value="${v.vehicle_id}" ${s.vehicle_id === v.vehicle_id ? 'selected' : ''}>${esc(v.registration_number)} (${esc(v.vehicle_type)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Assigned Driver</label>
          <select id="f-ushp-drv" class="form-control">
            <option value="">— Keep / Unchanged —</option>
            ${lk.drivers.map(d => `<option value="${d.driver_id}" ${s.driver_id === d.driver_id ? 'selected' : ''}>${esc(d.driver_name)}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Changes</button>
      </div>
    </form>
  `);
}

async function submitUpdateShipment(e, shipmentId) {
  e.preventDefault();
  try {
    const res = await apiRequest(`/api/shipments/${shipmentId}`, {
      method: 'PATCH',
      body: {
        shipment_status: document.getElementById('f-ushp-status').value,
        priority_level: document.getElementById('f-ushp-prio').value,
        vehicle_id: document.getElementById('f-ushp-veh').value || null,
        driver_id: document.getElementById('f-ushp-drv').value || null,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadShipmentsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

function openCreateVehicleModal() {
  openModal('Add Refrigerated Fleet Vehicle', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateVehicle(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Registration Number (Unique) <span class="req-star">*</span></label>
          <input type="text" id="f-veh-reg" class="form-control" placeholder="MH-12-CT-4090" required>
        </div>
        <div class="form-field">
          <label>Vehicle Type <span class="req-star">*</span></label>
          <select id="f-veh-type" class="form-control">
            <option value="Refrigerated Truck">Refrigerated Truck</option>
            <option value="Cold Chain Van">Cold Chain Van</option>
            <option value="Insulated Van">Insulated Van</option>
          </select>
        </div>
        <div class="form-field">
          <label>Refrigeration System <span class="req-star">*</span></label>
          <select id="f-veh-ref" class="form-control">
            <option value="Active Cooling">Active Cooling</option>
            <option value="Mechanical Refrigeration">Mechanical Refrigeration</option>
            <option value="Thermoelectric">Thermoelectric</option>
          </select>
        </div>
        <div class="form-field">
          <label>Payload Capacity (kg) <span class="req-star">*</span></label>
          <input type="number" id="f-veh-cap" class="form-control" value="2500" min="50" required>
        </div>
        <div class="form-field">
          <label>Min Temp (°C) <span class="req-star">*</span></label>
          <input type="number" step="0.1" id="f-veh-tmin" class="form-control" value="2.0" required>
        </div>
        <div class="form-field">
          <label>Max Temp (°C) <span class="req-star">*</span></label>
          <input type="number" step="0.1" id="f-veh-tmax" class="form-control" value="8.0" required>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Register Vehicle</button>
      </div>
    </form>
  `);
}

async function submitCreateVehicle(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/vehicles', {
      method: 'POST',
      body: {
        registration_number: document.getElementById('f-veh-reg').value,
        vehicle_type: document.getElementById('f-veh-type').value,
        refrigeration_type: document.getElementById('f-veh-ref').value,
        capacity: document.getElementById('f-veh-cap').value,
        temperature_min: document.getElementById('f-veh-tmin').value,
        temperature_max: document.getElementById('f-veh-tmax').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadShipmentsModule();
  } catch (err) {
    showFormError(err.message);
  }
}

function openCreateDriverModal() {
  openModal('Register Certified Cold-Chain Driver', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateDriver(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Driver Full Name <span class="req-star">*</span></label>
          <input type="text" id="f-drv-name" class="form-control" placeholder="Vikram Deshmukh" required>
        </div>
        <div class="form-field">
          <label>License Number (Unique) <span class="req-star">*</span></label>
          <input type="text" id="f-drv-lic" class="form-control" placeholder="DL-MH14-2026991" required>
        </div>
        <div class="form-field">
          <label>Contact Phone <span class="req-star">*</span></label>
          <input type="text" id="f-drv-phone" class="form-control" placeholder="+91-98201-55410" required>
        </div>
        <div class="form-field">
          <label>License Expiry Date <span class="req-star">*</span></label>
          <input type="date" id="f-drv-exp" class="form-control" value="${futureIso(1095)}" required>
        </div>
        <div class="form-field full-span">
          <label>Cold-Chain Certification</label>
          <input type="text" id="f-drv-cert" class="form-control" value="WHO-GDP Pharma Cold-Chain Carrier">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Driver</button>
      </div>
    </form>
  `);
}

async function submitCreateDriver(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/drivers', {
      method: 'POST',
      body: {
        driver_name: document.getElementById('f-drv-name').value,
        license_number: document.getElementById('f-drv-lic').value,
        phone: document.getElementById('f-drv-phone').value,
        license_expiry: document.getElementById('f-drv-exp').value,
        certification: document.getElementById('f-drv-cert').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadShipmentsModule();
  } catch (err) {
    showFormError(err.message);
  }
}

function openCreateRouteModal() {
  openModal('Define Cold-Chain Transit Route', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateRoute(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Origin City / Hub <span class="req-star">*</span></label>
          <input type="text" id="f-rte-orig" class="form-control" placeholder="Hyderabad BioHub" required>
        </div>
        <div class="form-field">
          <label>Destination City / Hub <span class="req-star">*</span></label>
          <input type="text" id="f-rte-dest" class="form-control" placeholder="Bengaluru MedCenter" required>
        </div>
        <div class="form-field">
          <label>Total Distance (km) <span class="req-star">*</span></label>
          <input type="number" step="0.1" id="f-rte-dist" class="form-control" value="575" min="1" required>
        </div>
        <div class="form-field">
          <label>Estimated Duration (Hours) <span class="req-star">*</span></label>
          <input type="number" step="0.5" id="f-rte-dur" class="form-control" value="9.5" min="0.5" required>
        </div>
        <div class="form-field">
          <label>Corridor Type</label>
          <select id="f-rte-type" class="form-control">
            <option value="Expressway">Expressway</option>
            <option value="Highway">Highway</option>
          </select>
        </div>
        <div class="form-field">
          <label>Initial Checkpoint Stop (Optional)</label>
          <input type="text" id="f-rte-stop" class="form-control" placeholder="Kurnool Cold Relay Station">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Route</button>
      </div>
    </form>
  `);
}

async function submitCreateRoute(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/routes', {
      method: 'POST',
      body: {
        origin: document.getElementById('f-rte-orig').value,
        destination: document.getElementById('f-rte-dest').value,
        total_distance: document.getElementById('f-rte-dist').value,
        estimated_duration: document.getElementById('f-rte-dur').value,
        route_type: document.getElementById('f-rte-type').value,
        initial_stop_name: document.getElementById('f-rte-stop').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadShipmentsModule();
  } catch (err) {
    showFormError(err.message);
  }
}

/* --------------------------------------------------------------------------
   7. PAGE 4: Cold-Chain Monitoring (Alerts, IoT Sensors, Telemetry Readings)
   -------------------------------------------------------------------------- */
async function loadMonitoringModule(forceToast = false) {
  try {
    const [alerts, sensors, readings] = await Promise.all([
      apiRequest('/api/monitoring/alerts'),
      apiRequest('/api/monitoring/sensors'),
      apiRequest('/api/monitoring/readings'),
    ]);
    store.alerts = alerts;
    store.sensors = sensors;
    store.readings = readings;
    applyMonitoringFilter();
    if (forceToast) showToast('Cold-chain sensor and alert records refreshed.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function applyMonitoringFilter() {
  const q = (document.getElementById('mon-search')?.value || '').toLowerCase().trim();
  const st = (document.getElementById('alert-status-filter')?.value || '').toLowerCase();
  const sev = (document.getElementById('alert-severity-filter')?.value || '').toLowerCase();

  const fAlerts = store.alerts.filter(a => {
    const mq = !q || [a.alert_id, a.sensor_serial, a.alert_type, a.origin, a.destination].some(v => v && String(v).toLowerCase().includes(q));
    const ms = !st || (a.alert_status && a.alert_status.toLowerCase() === st);
    const msev = !sev || (a.severity && a.severity.toLowerCase() === sev);
    return mq && ms && msev;
  });

  renderEnterpriseTable({
    containerId: 'card-alerts-table',
    tableKey: 'alerts',
    title: 'Temperature Excursions & Environmental Alerts',
    rows: fAlerts,
    columns: [
      { key: 'alert_id', label: 'Alert ID', render: r => `<strong class="mono-id">#ALT-${r.alert_id}</strong>` },
      { key: 'alert_time', label: 'Recorded Time', render: r => formatDateTime(r.alert_time) },
      { key: 'shipment_id', label: 'Shipment', render: r => r.shipment_id ? `<span class="mono-id">#SHP-${r.shipment_id}</span>` : '—' },
      { key: 'sensor_serial', label: 'Sensor', render: r => `<code>${esc(r.sensor_serial || '#' + r.sensor_id)}</code>` },
      { key: 'alert_type', label: 'Alert Type', render: r => `<strong>${esc(r.alert_type)}</strong>` },
      {
        key: 'recorded_temperature',
        label: 'Recorded Temp',
        render: r => {
          const rec = Number(r.recorded_temperature);
          const cls = rec > Number(r.expected_max) ? 'temp-excursion-hot' : (rec < Number(r.expected_min) ? 'temp-excursion-cold' : 'temp-normal');
          return `<span class="temp-pill ${cls}">${rec}°C</span>`;
        },
      },
      { key: 'expected_max', label: 'Expected Range', render: r => `${r.expected_min}°C – ${r.expected_max}°C` },
      { key: 'severity', label: 'Severity', render: r => getStatusBadge(r.severity) },
      { key: 'alert_status', label: 'Status', render: r => getStatusBadge(r.alert_status) },
      {
        key: 'actions',
        label: 'Workflow',
        sortable: false,
        render: r => {
          if (!CAN_WRITE) return '<span style="color:var(--text-faint); font-size:0.75rem;">View Only</span>';
          const up = String(r.alert_status || '').toUpperCase();
          if (up === 'OPEN') {
            return `
              <div style="display:flex; gap:0.35rem;">
                <button class="btn btn-outline btn-sm" onclick="updateAlertStatus(${r.alert_id}, 'Acknowledged')">Ack</button>
                <button class="btn btn-success btn-sm" onclick="updateAlertStatus(${r.alert_id}, 'Resolved')">Resolve</button>
              </div>
            `;
          }
          if (up === 'ACKNOWLEDGED') {
            return `<button class="btn btn-success btn-sm" onclick="updateAlertStatus(${r.alert_id}, 'Resolved')">Resolve</button>`;
          }
          return '<span style="color:var(--status-success); font-size:0.76rem; font-weight:600;">&#10003; Closed</span>';
        },
      },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-sensors-table',
    tableKey: 'sensors',
    title: 'Calibrated IoT Telemetry Sensor Nodes',
    rows: store.sensors.filter(s => !q || [s.serial_number, s.sensor_type, s.manufacturer, s.registration_number].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'sensor_id', label: 'Node ID', render: r => `<span class="mono-id">#SNS-${r.sensor_id}</span>` },
      { key: 'serial_number', label: 'Serial Number', render: r => `<code>${esc(r.serial_number)}</code>` },
      { key: 'sensor_type', label: 'Sensor Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'registration_number', label: 'Assigned Vehicle', render: r => esc(r.registration_number || 'Depot / Unassigned') },
      { key: 'temperature', label: 'Last Recorded Sample', render: r => r.temperature !== null ? `<span class="temp-pill temp-normal">${r.temperature}°C / ${r.humidity ?? '—'}% RH</span>` : 'No readings' },
      { key: 'calibration_expiry', label: 'Calibration Expiry', render: r => formatDate(r.calibration_expiry) },
      { key: 'sensor_status', label: 'Status', render: r => getStatusBadge(r.sensor_status) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-readings-table',
    tableKey: 'readings',
    title: 'Historical Recorded Sensor Readings',
    rows: store.readings.filter(r => !q || [r.serial_number, r.registration_number, r.sensor_type].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'reading_id', label: 'Sample ID', render: r => `<span class="mono-id">#SMP-${r.reading_id}</span>` },
      { key: 'reading_timestamp', label: 'Recorded Timestamp', render: r => formatDateTime(r.reading_timestamp) },
      { key: 'serial_number', label: 'Sensor Serial', render: r => `<code>${esc(r.serial_number || '#' + r.sensor_id)}</code>` },
      { key: 'registration_number', label: 'Vehicle', render: r => esc(r.registration_number || '—') },
      { key: 'temperature', label: 'Temperature', render: r => `<span class="temp-pill ${Number(r.temperature) > 8 || Number(r.temperature) < 2 ? 'temp-excursion-hot' : 'temp-normal'}">${r.temperature}°C</span>` },
      { key: 'humidity', label: 'Humidity', render: r => r.humidity !== null ? `${r.humidity}% RH` : '—' },
      { key: 'battery_level', label: 'Battery', render: r => r.battery_level !== null ? `${r.battery_level}%` : '—' },
    ],
  });
}

async function updateAlertStatus(alertId, nextStatus) {
  try {
    const res = await apiRequest(`/api/monitoring/alerts/${alertId}`, {
      method: 'PATCH',
      body: { alert_status: nextStatus },
    });
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadMonitoringModule();
    loadCommandCenter();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function openRecordReadingModal() {
  const lk = await ensureLookups();
  openModal('Record Sensor Telemetry Sample', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitRecordReading(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>IoT Sensor Node <span class="req-star">*</span></label>
          <select id="f-rd-sensor" class="form-control" required>
            ${lk.sensors.map(s => `<option value="${s.sensor_id}">${esc(s.serial_number)} (${esc(s.sensor_type)}${s.registration_number ? ' • ' + esc(s.registration_number) : ''})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Recorded Temperature (°C) <span class="req-star">*</span></label>
          <input type="number" step="0.1" id="f-rd-temp" class="form-control" value="4.8" required>
          <span class="form-helper">Values outside expected bounds automatically log an Open Excursion Alert.</span>
        </div>
        <div class="form-field">
          <label>Relative Humidity (% RH) <span class="req-star">*</span></label>
          <input type="number" step="0.1" id="f-rd-hum" class="form-control" value="46.0" min="0" max="100" required>
        </div>
        <div class="form-field">
          <label>Expected Min (°C)</label>
          <input type="number" step="0.1" id="f-rd-emin" class="form-control" value="2.0">
        </div>
        <div class="form-field">
          <label>Expected Max (°C)</label>
          <input type="number" step="0.1" id="f-rd-emax" class="form-control" value="8.0">
        </div>
        <div class="form-field">
          <label>Battery Level (%)</label>
          <input type="number" step="1" id="f-rd-bat" class="form-control" value="94" min="0" max="100">
        </div>
        <div class="form-field">
          <label>Linked Shipment (If In-Transit)</label>
          <select id="f-rd-shp" class="form-control">
            <option value="">— Optional —</option>
            ${lk.shipments.map(s => `<option value="${s.shipment_id}">#SHP-${s.shipment_id} (${esc(s.origin || '')} → ${esc(s.destination || '')})</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Telemetry Sample</button>
      </div>
    </form>
  `);
}

async function submitRecordReading(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/monitoring/readings', {
      method: 'POST',
      body: {
        sensor_id: document.getElementById('f-rd-sensor').value,
        temperature: document.getElementById('f-rd-temp').value,
        humidity: document.getElementById('f-rd-hum').value,
        expected_min: document.getElementById('f-rd-emin').value,
        expected_max: document.getElementById('f-rd-emax').value,
        battery_level: document.getElementById('f-rd-bat').value,
        shipment_id: document.getElementById('f-rd-shp').value || null,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadMonitoringModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

async function openCreateSensorModal() {
  const lk = await ensureLookups();
  openModal('Register Calibrated IoT Sensor Node', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateSensor(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Serial Number (Unique) <span class="req-star">*</span></label>
          <input type="text" id="f-sns-ser" class="form-control" placeholder="CRYO-SNS-2026-50" required>
        </div>
        <div class="form-field">
          <label>Sensor Type <span class="req-star">*</span></label>
          <select id="f-sns-type" class="form-control">
            <option value="Temperature and Humidity">Temperature and Humidity</option>
            <option value="Temperature">Temperature</option>
            <option value="Combined">Combined Multi-Probe</option>
          </select>
        </div>
        <div class="form-field">
          <label>Manufacturer <span class="req-star">*</span></label>
          <input type="text" id="f-sns-mfg" class="form-control" value="Sensitech ColdStream" required>
        </div>
        <div class="form-field">
          <label>Assigned Vehicle</label>
          <select id="f-sns-veh" class="form-control">
            <option value="">— Stationary / Unassigned —</option>
            ${lk.vehicles.map(v => `<option value="${v.vehicle_id}">${esc(v.registration_number)} (${esc(v.vehicle_type)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Calibration Date <span class="req-star">*</span></label>
          <input type="date" id="f-sns-cal" class="form-control" value="${todayIso()}" required>
        </div>
        <div class="form-field">
          <label>Calibration Expiry <span class="req-star">*</span></label>
          <input type="date" id="f-sns-exp" class="form-control" value="${futureIso(365)}" required>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Register Sensor</button>
      </div>
    </form>
  `);
}

async function submitCreateSensor(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/monitoring/sensors', {
      method: 'POST',
      body: {
        serial_number: document.getElementById('f-sns-ser').value,
        sensor_type: document.getElementById('f-sns-type').value,
        manufacturer: document.getElementById('f-sns-mfg').value,
        vehicle_id: document.getElementById('f-sns-veh').value || null,
        calibration_date: document.getElementById('f-sns-cal').value,
        calibration_expiry: document.getElementById('f-sns-exp').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadMonitoringModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

/* --------------------------------------------------------------------------
   8. PAGE 5: Inventory & Warehousing (Stock, Transactions, Warehouses, Units)
   -------------------------------------------------------------------------- */
async function loadInventoryModule(forceToast = false) {
  try {
    const [inventory, transactions, warehouses, units] = await Promise.all([
      apiRequest('/api/inventory'),
      apiRequest('/api/inventory/transactions'),
      apiRequest('/api/warehouses'),
      apiRequest('/api/storage-units'),
    ]);
    store.inventory = inventory;
    store.transactions = transactions;
    store.warehouses = warehouses;
    store.storageUnits = units;
    applyInventoryFilter();
    if (forceToast) showToast('Inventory & Cold Warehousing records synchronized.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function applyInventoryFilter() {
  const q = (document.getElementById('inv-search')?.value || '').toLowerCase().trim();
  const st = (document.getElementById('inv-status-filter')?.value || '').toLowerCase();

  const fInv = store.inventory.filter(i => {
    const mq = !q || [i.product_name, i.batch_number, i.warehouse_name, i.unit_name].some(v => v && String(v).toLowerCase().includes(q));
    const ms = !st || (i.inventory_status && i.inventory_status.toLowerCase() === st);
    return mq && ms;
  });

  renderEnterpriseTable({
    containerId: 'card-inventory-table',
    tableKey: 'inventory',
    title: 'Cold-Storage Inventory Lots (Available vs. Reserved)',
    rows: fInv,
    columns: [
      { key: 'inventory_id', label: 'Lot ID', render: r => `<strong class="mono-id">#INV-${r.inventory_id}</strong>` },
      { key: 'product_name', label: 'Product', render: r => `<strong>${esc(r.product_name)}</strong>` },
      { key: 'batch_number', label: 'Batch', render: r => `<code>${esc(r.batch_number)}</code>` },
      { key: 'warehouse_name', label: 'Warehouse', render: r => `${esc(r.warehouse_name)} (${esc(r.warehouse_city || '')})` },
      { key: 'unit_name', label: 'Storage Unit', render: r => `${esc(r.unit_name)}<br><small style="color:var(--text-muted)">${r.unit_min_temp}°C to ${r.unit_max_temp}°C</small>` },
      { key: 'quantity_available', label: 'Available', render: r => `<strong class="tabular-nums" style="color:var(--status-success)">${Number(r.quantity_available || 0).toLocaleString()}</strong>` },
      { key: 'quantity_reserved', label: 'Reserved', render: r => `<span class="tabular-nums">${Number(r.quantity_reserved || 0).toLocaleString()}</span>` },
      { key: 'total_quantity', label: 'Total Stock', render: r => `<strong class="tabular-nums">${Number(r.total_quantity || 0).toLocaleString()}</strong>` },
      { key: 'inventory_status', label: 'Status', render: r => getStatusBadge(r.inventory_status) },
      { key: 'last_updated', label: 'Updated', render: r => formatDate(r.last_updated) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-transactions-table',
    tableKey: 'transactions',
    title: 'Audited Stock Movement Ledger',
    rows: store.transactions.filter(t => !q || [t.product_name, t.batch_number, t.transaction_type, t.performed_by, t.remarks].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'transaction_id', label: 'Trx ID', render: r => `<span class="mono-id">#TRX-${r.transaction_id}</span>` },
      { key: 'transaction_date', label: 'Date', render: r => formatDate(r.transaction_date) },
      { key: 'product_name', label: 'Product & Batch', render: r => `<strong>${esc(r.product_name)}</strong> (<code>${esc(r.batch_number)}</code>)` },
      { key: 'transaction_type', label: 'Movement Type', render: r => `<span class="badge badge-info">${esc(r.transaction_type)}</span>` },
      { key: 'quantity', label: 'Quantity', render: r => `<strong class="tabular-nums">${Number(r.quantity || 0).toLocaleString()}</strong>` },
      { key: 'performed_by', label: 'Performed By' },
      { key: 'remarks', label: 'Audit Remarks', render: r => esc(r.remarks || '—') },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-warehouses-table',
    tableKey: 'warehouses',
    title: 'Certified Cold-Storage Warehouses',
    rows: store.warehouses.filter(w => !q || [w.warehouse_name, w.city, w.state, w.manager_name].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'warehouse_id', label: 'ID', render: r => `<span class="mono-id">#WH-${r.warehouse_id}</span>` },
      { key: 'warehouse_name', label: 'Warehouse Name', render: r => `<strong>${esc(r.warehouse_name)}</strong>` },
      { key: 'warehouse_type', label: 'Facility Class' },
      { key: 'city', label: 'Location', render: r => `${esc(r.city)}, ${esc(r.state)}` },
      { key: 'capacity', label: 'Capacity', render: r => `${Number(r.capacity || 0).toLocaleString()} units` },
      { key: 'units_count', label: 'Chambers', render: r => `<span class="badge badge-neutral">${r.units_count} units</span>` },
      { key: 'manager_name', label: 'Manager' },
      { key: 'certification_status', label: 'GDP Status', render: r => getStatusBadge(r.certification_status) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-units-table',
    tableKey: 'units',
    title: 'Temperature-Controlled Storage Chambers & Units',
    rows: store.storageUnits.filter(u => !q || [u.unit_name, u.unit_type, u.warehouse_name].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'storage_unit_id', label: 'Unit ID', render: r => `<span class="mono-id">#SU-${r.storage_unit_id}</span>` },
      { key: 'unit_name', label: 'Chamber Name', render: r => `<strong>${esc(r.unit_name)}</strong>` },
      { key: 'warehouse_name', label: 'Warehouse', render: r => `${esc(r.warehouse_name || '—')} (${esc(r.city || '')})` },
      { key: 'unit_type', label: 'Chamber Type' },
      { key: 'minimum_temperature', label: 'Thermal Setpoint', render: r => `<span class="temp-pill temp-normal">${r.minimum_temperature}°C to ${r.maximum_temperature}°C</span>` },
      { key: 'capacity', label: 'Capacity', render: r => `${Number(r.capacity || 0).toLocaleString()} units` },
      { key: 'current_status', label: 'Status', render: r => getStatusBadge(r.current_status) },
    ],
  });
}

async function openStockTransactionModal() {
  const lk = await ensureLookups(true);
  openModal('Record Audited Stock Movement Transaction', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitStockTransaction(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Target Inventory Lot <span class="req-star">*</span></label>
          <select id="f-trx-inv" class="form-control" required>
            ${lk.inventory_items.map(i => `<option value="${i.inventory_id}">#INV-${i.inventory_id}: ${esc(i.product_name)} (${esc(i.batch_number)}) — Avail: ${i.quantity_available}, Res: ${i.quantity_reserved}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Movement Type <span class="req-star">*</span></label>
          <select id="f-trx-type" class="form-control">
            <option value="STOCK_IN">STOCK_IN (Inbound Receipt)</option>
            <option value="STOCK_OUT">STOCK_OUT (Dispatch Release)</option>
            <option value="RESERVATION">RESERVATION (Reserve Quota)</option>
            <option value="RELEASE">RELEASE (Unreserve to Available)</option>
          </select>
        </div>
        <div class="form-field">
          <label>Quantity (Units) <span class="req-star">*</span></label>
          <input type="number" id="f-trx-qty" class="form-control" min="1" value="50" required>
        </div>
        <div class="form-field full-span">
          <label>Audit Remarks / Justification <span class="req-star">*</span></label>
          <input type="text" id="f-trx-rem" class="form-control" placeholder="e.g. Hospital order allocation verified under GDP protocol" required>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Commit Stock Transaction</button>
      </div>
    </form>
  `);
}

async function submitStockTransaction(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/inventory/transactions', {
      method: 'POST',
      body: {
        inventory_id: document.getElementById('f-trx-inv').value,
        transaction_type: document.getElementById('f-trx-type').value,
        quantity: document.getElementById('f-trx-qty').value,
        remarks: document.getElementById('f-trx-rem').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadInventoryModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

async function openAllocateInventoryModal() {
  const lk = await ensureLookups();
  openModal('Allocate New Cold-Storage Inventory Lot', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitAllocateInventory(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Product Batch <span class="req-star">*</span></label>
          <select id="f-ainv-batch" class="form-control" required>
            ${lk.batches.map(b => `<option value="${b.batch_id}">${esc(b.batch_number)} — ${esc(b.product_name)}</option>`).join('')}
          </select>
        </div>
        <div class="form-field full-span">
          <label>Storage Chamber / Unit <span class="req-star">*</span></label>
          <select id="f-ainv-unit" class="form-control" required>
            ${lk.storage_units.map(u => `<option value="${u.storage_unit_id}">${esc(u.warehouse_name || 'Depot')} • ${esc(u.unit_name)} (${esc(u.unit_type)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Initial Available Quantity <span class="req-star">*</span></label>
          <input type="number" id="f-ainv-avail" class="form-control" min="1" value="500" required>
        </div>
        <div class="form-field">
          <label>Initial Reserved Quantity</label>
          <input type="number" id="f-ainv-res" class="form-control" min="0" value="0">
        </div>
        <div class="form-field full-span">
          <label>Ledger Remarks</label>
          <input type="text" id="f-ainv-rem" class="form-control" value="Initial cold-chamber batch intake">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Allocate &amp; Log STOCK_IN</button>
      </div>
    </form>
  `);
}

async function submitAllocateInventory(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/inventory', {
      method: 'POST',
      body: {
        batch_id: document.getElementById('f-ainv-batch').value,
        storage_unit_id: document.getElementById('f-ainv-unit').value,
        quantity_available: document.getElementById('f-ainv-avail').value,
        quantity_reserved: document.getElementById('f-ainv-res').value,
        remarks: document.getElementById('f-ainv-rem').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadInventoryModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

async function openCreateStorageUnitModal() {
  const lk = await ensureLookups();
  openModal('Add Temperature-Controlled Storage Unit', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateStorageUnit(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Parent Warehouse <span class="req-star">*</span></label>
          <select id="f-su-wh" class="form-control" required>
            ${lk.warehouses.map(w => `<option value="${w.warehouse_id}">${esc(w.warehouse_name)} (${esc(w.city)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Chamber / Unit Name <span class="req-star">*</span></label>
          <input type="text" id="f-su-name" class="form-control" placeholder="Cryo-Vault B4" required>
        </div>
        <div class="form-field">
          <label>Unit Classification</label>
          <select id="f-su-type" class="form-control">
            <option value="REFRIGERATED">REFRIGERATED (2°C – 8°C)</option>
            <option value="VACCINE STORAGE">VACCINE STORAGE</option>
            <option value="FROZEN">FROZEN (-25°C to -15°C)</option>
            <option value="QUARANTINE">QUARANTINE</option>
          </select>
        </div>
        <div class="form-field">
          <label>Min Temperature (°C) <span class="req-star">*</span></label>
          <input type="number" step="0.1" id="f-su-min" class="form-control" value="2.0" required>
        </div>
        <div class="form-field">
          <label>Max Temperature (°C) <span class="req-star">*</span></label>
          <input type="number" step="0.1" id="f-su-max" class="form-control" value="8.0" required>
        </div>
        <div class="form-field full-span">
          <label>Unit Capacity (Units) <span class="req-star">*</span></label>
          <input type="number" id="f-su-cap" class="form-control" value="5000" min="10" required>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Storage Unit</button>
      </div>
    </form>
  `);
}

async function submitCreateStorageUnit(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/storage-units', {
      method: 'POST',
      body: {
        warehouse_id: document.getElementById('f-su-wh').value,
        unit_name: document.getElementById('f-su-name').value,
        unit_type: document.getElementById('f-su-type').value,
        minimum_temperature: document.getElementById('f-su-min').value,
        maximum_temperature: document.getElementById('f-su-max').value,
        capacity: document.getElementById('f-su-cap').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadInventoryModule();
  } catch (err) {
    showFormError(err.message);
  }
}

function openCreateWarehouseModal() {
  openModal('Register Cold-Chain Warehouse Facility', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateWarehouse(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Warehouse Name <span class="req-star">*</span></label>
          <input type="text" id="f-wh-name" class="form-control" placeholder="CryoTrack Southern Hub" required>
        </div>
        <div class="form-field">
          <label>Warehouse Type</label>
          <select id="f-wh-type" class="form-control">
            <option value="Cold Storage">Cold Storage</option>
            <option value="Distribution Warehouse">Distribution Warehouse</option>
            <option value="Regional Depot">Regional Depot</option>
          </select>
        </div>
        <div class="form-field">
          <label>City <span class="req-star">*</span></label>
          <input type="text" id="f-wh-city" class="form-control" placeholder="Chennai" required>
        </div>
        <div class="form-field">
          <label>State <span class="req-star">*</span></label>
          <input type="text" id="f-wh-state" class="form-control" placeholder="Tamil Nadu" required>
        </div>
        <div class="form-field full-span">
          <label>Street Address <span class="req-star">*</span></label>
          <input type="text" id="f-wh-addr" class="form-control" placeholder="Plot 14, Sriperumbudur Pharma Logistics Corridor" required>
        </div>
        <div class="form-field">
          <label>Total Capacity (Units) <span class="req-star">*</span></label>
          <input type="number" id="f-wh-cap" class="form-control" value="40000" min="100" required>
        </div>
        <div class="form-field">
          <label>Facility Manager <span class="req-star">*</span></label>
          <input type="text" id="f-wh-mgr" class="form-control" placeholder="S. Narayanan" required>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Register Warehouse</button>
      </div>
    </form>
  `);
}

async function submitCreateWarehouse(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/warehouses', {
      method: 'POST',
      body: {
        warehouse_name: document.getElementById('f-wh-name').value,
        warehouse_type: document.getElementById('f-wh-type').value,
        city: document.getElementById('f-wh-city').value,
        state: document.getElementById('f-wh-state').value,
        address: document.getElementById('f-wh-addr').value,
        capacity: document.getElementById('f-wh-cap').value,
        manager_name: document.getElementById('f-wh-mgr').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadInventoryModule();
  } catch (err) {
    showFormError(err.message);
  }
}

/* --------------------------------------------------------------------------
   9. PAGE 6: Incidents & Compliance
   -------------------------------------------------------------------------- */
async function loadIncidentsModule(forceToast = false) {
  try {
    store.incidents = await apiRequest('/api/incidents');
    applyIncidentsFilter();
    if (forceToast) showToast('Compliance incidents synchronized.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function applyIncidentsFilter() {
  const q = (document.getElementById('inc-search')?.value || '').toLowerCase().trim();
  const st = (document.getElementById('inc-status-filter')?.value || '').toLowerCase();
  const sev = (document.getElementById('inc-severity-filter')?.value || '').toLowerCase();

  const rows = store.incidents.filter(i => {
    const mq = !q || [i.incident_id, i.incident_type, i.description, i.corrective_action, i.product_impact].some(v => v && String(v).toLowerCase().includes(q));
    const ms = !st || (i.resolution_status && i.resolution_status.toLowerCase() === st);
    const msev = !sev || (i.severity && i.severity.toLowerCase() === sev);
    return mq && ms && msev;
  });

  renderEnterpriseTable({
    containerId: 'card-incidents-table',
    tableKey: 'incidents',
    title: 'Cold-Chain Deviations, Impact Assessments & Corrective Actions (CAPA)',
    rows,
    columns: [
      { key: 'incident_id', label: 'Incident', render: r => `<strong class="mono-id">#INC-${r.incident_id}</strong>` },
      { key: 'incident_date', label: 'Date', render: r => formatDate(r.incident_date) },
      { key: 'incident_type', label: 'Incident Type', render: r => `<strong>${esc(r.incident_type)}</strong>` },
      { key: 'shipment_id', label: 'Refs', render: r => `${r.shipment_id ? `<span class="mono-id">#SHP-${r.shipment_id}</span>` : '—'} ${r.alert_id ? `<br><small class="mono-id">#ALT-${r.alert_id}</small>` : ''}` },
      { key: 'severity', label: 'Severity', render: r => getStatusBadge(r.severity) },
      { key: 'product_impact', label: 'Product Impact', render: r => esc(r.product_impact || 'Under assessment') },
      { key: 'resolution_status', label: 'Resolution', render: r => getStatusBadge(r.resolution_status) },
      { key: 'corrective_action', label: 'Corrective Action', render: r => `<small>${esc(r.corrective_action || 'Pending CAPA')}</small>` },
      {
        key: 'actions',
        label: 'Actions',
        sortable: false,
        render: r => `
          <div style="display:flex; gap:0.35rem;">
            <button class="btn btn-outline btn-sm" onclick="inspectIncident(${r.incident_id})">Audit</button>
            ${CAN_WRITE ? `<button class="btn btn-outline btn-sm" onclick="openUpdateIncidentModal(${r.incident_id})">CAPA</button>` : ''}
          </div>
        `,
      },
    ],
  });
}

function inspectIncident(incId) {
  const inc = store.incidents.find(x => x.incident_id === incId);
  if (!inc) return;
  openModal(`Compliance Incident — #INC-${inc.incident_id}`, `
    <div class="detail-grid">
      <div class="detail-item"><span class="detail-label">Incident Type</span><span class="detail-value"><strong>${esc(inc.incident_type)}</strong></span></div>
      <div class="detail-item"><span class="detail-label">Incident Date</span><span class="detail-value">${formatDate(inc.incident_date)}</span></div>
      <div class="detail-item"><span class="detail-label">Severity</span><span class="detail-value">${getStatusBadge(inc.severity)}</span></div>
      <div class="detail-item"><span class="detail-label">Resolution Status</span><span class="detail-value">${getStatusBadge(inc.resolution_status)}</span></div>
      <div class="detail-item"><span class="detail-label">Linked Shipment</span><span class="detail-value">${inc.shipment_id ? '#SHP-' + inc.shipment_id : 'None'}</span></div>
      <div class="detail-item"><span class="detail-label">Linked Excursion Alert</span><span class="detail-value">${inc.alert_id ? `#ALT-${inc.alert_id} (${inc.recorded_temperature}°C)` : 'None'}</span></div>
    </div>
    <div style="margin-top:1rem;"><span class="detail-label">Description</span><p style="margin-top:0.3rem; font-size:0.85rem;">${esc(inc.description || '—')}</p></div>
    <div style="margin-top:0.9rem;"><span class="detail-label">Product Impact Assessment</span><p style="margin-top:0.3rem; font-size:0.85rem;">${esc(inc.product_impact || '—')}</p></div>
    <div style="margin-top:0.9rem;"><span class="detail-label">Corrective &amp; Preventive Action (CAPA)</span><p style="margin-top:0.3rem; padding:0.75rem; background:var(--bg-subtle); border-radius:8px; font-size:0.85rem;">${esc(inc.corrective_action || 'Pending CAPA entry')}</p></div>
  `);
}

async function openCreateIncidentModal() {
  const lk = await ensureLookups(true);
  const unlinkedAlerts = lk.alerts.filter(a => !a.has_incident);
  openModal('Log Cold-Chain Compliance Incident', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateIncident(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Incident Type <span class="req-star">*</span></label>
          <select id="f-inc-type" class="form-control">
            <option value="Temperature Excursion">Temperature Excursion</option>
            <option value="Cooling Deviation">Cooling Deviation</option>
            <option value="Sensor Failure">Sensor Failure</option>
          </select>
        </div>
        <div class="form-field">
          <label>Severity <span class="req-star">*</span></label>
          <select id="f-inc-sev" class="form-control">
            <option value="High">High</option>
            <option value="Critical">Critical</option>
            <option value="Medium">Medium</option>
          </select>
        </div>
        <div class="form-field">
          <label>Linked Shipment</label>
          <select id="f-inc-shp" class="form-control">
            <option value="">— Optional —</option>
            ${lk.shipments.map(s => `<option value="${s.shipment_id}">#SHP-${s.shipment_id} (${esc(s.origin || '')} → ${esc(s.destination || '')})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Unlinked Excursion Alert</label>
          <select id="f-inc-alt" class="form-control">
            <option value="">— None / Standalone Incident —</option>
            ${unlinkedAlerts.map(a => `<option value="${a.alert_id}">#ALT-${a.alert_id}: ${esc(a.alert_type)} (${a.recorded_temperature}°C)</option>`).join('')}
          </select>
        </div>
        <div class="form-field full-span">
          <label>Deviation Description <span class="req-star">*</span></label>
          <textarea id="f-inc-desc" class="form-control" placeholder="Describe root cause, duration, and environmental conditions..." required></textarea>
        </div>
        <div class="form-field full-span">
          <label>Product Impact Assessment <span class="req-star">*</span></label>
          <input type="text" id="f-inc-imp" class="form-control" placeholder="e.g. Stability budget evaluated; vials quarantined pending QA sign-off" required>
        </div>
        <div class="form-field full-span">
          <label>Initial Corrective Action (CAPA)</label>
          <input type="text" id="f-inc-capa" class="form-control" placeholder="e.g. Transferred payload to backup active-cooling container">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Log Incident</button>
      </div>
    </form>
  `);
}

async function submitCreateIncident(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/incidents', {
      method: 'POST',
      body: {
        incident_type: document.getElementById('f-inc-type').value,
        severity: document.getElementById('f-inc-sev').value,
        shipment_id: document.getElementById('f-inc-shp').value || null,
        alert_id: document.getElementById('f-inc-alt').value || null,
        description: document.getElementById('f-inc-desc').value,
        product_impact: document.getElementById('f-inc-imp').value,
        corrective_action: document.getElementById('f-inc-capa').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadIncidentsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

function openUpdateIncidentModal(incId) {
  const inc = store.incidents.find(x => x.incident_id === incId);
  if (!inc) return;
  openModal(`Update CAPA & Resolution — #INC-${inc.incident_id}`, `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitUpdateIncident(event, ${inc.incident_id})">
      <div class="form-grid">
        <div class="form-field">
          <label>Resolution Status <span class="req-star">*</span></label>
          <select id="f-uinc-status" class="form-control">
            ${['Open', 'Under Investigation', 'Under Review', 'Resolved'].map(s => `<option value="${s}" ${inc.resolution_status === s ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Severity <span class="req-star">*</span></label>
          <select id="f-uinc-sev" class="form-control">
            ${['Critical', 'High', 'Medium'].map(s => `<option value="${s}" ${inc.severity === s ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>
        <div class="form-field full-span">
          <label>Product Impact Assessment <span class="req-star">*</span></label>
          <input type="text" id="f-uinc-imp" class="form-control" value="${esc(inc.product_impact || '')}" required>
        </div>
        <div class="form-field full-span">
          <label>Corrective &amp; Preventive Action (CAPA) <span class="req-star">*</span></label>
          <textarea id="f-uinc-capa" class="form-control" required>${esc(inc.corrective_action || '')}</textarea>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Update Compliance Record</button>
      </div>
    </form>
  `);
}

async function submitUpdateIncident(e, incId) {
  e.preventDefault();
  try {
    const res = await apiRequest(`/api/incidents/${incId}`, {
      method: 'PATCH',
      body: {
        resolution_status: document.getElementById('f-uinc-status').value,
        severity: document.getElementById('f-uinc-sev').value,
        product_impact: document.getElementById('f-uinc-imp').value,
        corrective_action: document.getElementById('f-uinc-capa').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await loadIncidentsModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

/* --------------------------------------------------------------------------
   10. PAGE 7: Deliveries & Distribution (Deliveries, Facilities, Centers)
   -------------------------------------------------------------------------- */
async function loadDeliveriesModule(forceToast = false) {
  try {
    const [deliveries, facilities, distCenters] = await Promise.all([
      apiRequest('/api/deliveries'),
      apiRequest('/api/facilities'),
      apiRequest('/api/distribution-centers'),
    ]);
    store.deliveries = deliveries;
    store.facilities = facilities;
    store.distCenters = distCenters;
    applyDeliveriesFilter();
    if (forceToast) showToast('Deliveries & Distribution records synchronized.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function applyDeliveriesFilter() {
  const q = (document.getElementById('deliv-search')?.value || '').toLowerCase().trim();
  const st = (document.getElementById('deliv-status-filter')?.value || '').toLowerCase();

  const fDeliv = store.deliveries.filter(d => {
    const mq = !q || [d.delivery_id, d.shipment_id, d.facility_name, d.facility_city, d.received_by, d.proof_of_delivery].some(v => v && String(v).toLowerCase().includes(q));
    const ms = !st || (d.delivery_status && d.delivery_status.toLowerCase() === st);
    return mq && ms;
  });

  renderEnterpriseTable({
    containerId: 'card-deliveries-table',
    tableKey: 'deliveries',
    title: 'Healthcare Facility Delivery Receipts & POD Custody',
    rows: fDeliv,
    columns: [
      { key: 'delivery_id', label: 'Delivery ID', render: r => `<strong class="mono-id">#DEL-${r.delivery_id}</strong>` },
      { key: 'shipment_id', label: 'Shipment', render: r => `<span class="mono-id">#SHP-${r.shipment_id}</span>` },
      { key: 'facility_name', label: 'Healthcare Facility', render: r => `<strong>${esc(r.facility_name)}</strong><br><small style="color:var(--text-muted)">${esc(r.facility_city)}, ${esc(r.facility_state)}</small>` },
      { key: 'delivery_date', label: 'Delivery Date', render: r => formatDate(r.delivery_date) },
      { key: 'received_by', label: 'Received By' },
      { key: 'quantity_received', label: 'Received', render: r => `<strong class="tabular-nums">${Number(r.quantity_received || 0).toLocaleString()}</strong>` },
      { key: 'quantity_damaged', label: 'Damaged', render: r => Number(r.quantity_damaged) > 0 ? `<span class="badge badge-danger">${r.quantity_damaged} units</span>` : '<span class="badge badge-success">0 (Intact)</span>' },
      { key: 'proof_of_delivery', label: 'POD Code', render: r => `<code>${esc(r.proof_of_delivery || '—')}</code>` },
      { key: 'delivery_status', label: 'Status', render: r => getStatusBadge(r.delivery_status) },
      {
        key: 'actions',
        label: 'Actions',
        sortable: false,
        render: r => `
          <div style="display:flex; gap:0.35rem;">
            <button class="btn btn-outline btn-sm" onclick="inspectDelivery(${r.delivery_id})">POD</button>
            ${CAN_WRITE ? `<button class="btn btn-outline btn-sm" onclick="openUpdateDeliveryModal(${r.delivery_id})">Edit</button>` : ''}
          </div>
        `,
      },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-facilities-table',
    tableKey: 'facilities',
    title: 'Authorized Recipient Healthcare Facilities',
    rows: store.facilities.filter(f => !q || [f.facility_name, f.city, f.state, f.license_number].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'facility_id', label: 'ID', render: r => `<span class="mono-id">#FAC-${r.facility_id}</span>` },
      { key: 'facility_name', label: 'Facility Name', render: r => `<strong>${esc(r.facility_name)}</strong>` },
      { key: 'facility_type', label: 'Type' },
      { key: 'license_number', label: 'License No.', render: r => `<code>${esc(fLic(r))}</code>` },
      { key: 'city', label: 'City & State', render: r => `${esc(r.city)}, ${esc(r.state)}` },
      { key: 'storage_capability', label: 'Cold-Storage Capability' },
      { key: 'deliveries_count', label: 'Receipts', render: r => `<span class="badge badge-neutral">${r.deliveries_count}</span>` },
      { key: 'facility_status', label: 'Status', render: r => getStatusBadge(r.facility_status) },
    ],
  });

  renderEnterpriseTable({
    containerId: 'card-distcenters-table',
    tableKey: 'distcenters',
    title: 'Regional Pharmaceutical Distribution Centers',
    rows: store.distCenters.filter(c => !q || [c.center_name, c.city, c.state, c.manager_name].some(v => v && String(v).toLowerCase().includes(q))),
    columns: [
      { key: 'distribution_center_id', label: 'Center ID', render: r => `<span class="mono-id">#DC-${r.distribution_center_id}</span>` },
      { key: 'center_name', label: 'Distribution Center', render: r => `<strong>${esc(r.center_name)}</strong>` },
      { key: 'city', label: 'Location', render: r => `${esc(r.city)}, ${esc(r.state)}` },
      { key: 'capacity', label: 'Capacity', render: r => `${Number(r.capacity || 0).toLocaleString()} units` },
      { key: 'manager_name', label: 'Center Manager' },
      { key: 'contact_number', label: 'Contact' },
      { key: 'certification_status', label: 'Certification', render: r => getStatusBadge(r.certification_status) },
    ],
  });
}

function fLic(row) {
  return row.license_number || '—';
}

function inspectDelivery(delivId) {
  const d = store.deliveries.find(x => x.delivery_id === delivId);
  if (!d) return;
  openModal(`Proof of Delivery Receipt — #DEL-${d.delivery_id}`, `
    <div class="detail-grid">
      <div class="detail-item"><span class="detail-label">Delivery ID</span><span class="detail-value"><strong class="mono-id">#DEL-${d.delivery_id}</strong></span></div>
      <div class="detail-item"><span class="detail-label">Shipment Manifest</span><span class="detail-value"><strong class="mono-id">#SHP-${d.shipment_id}</strong></span></div>
      <div class="detail-item"><span class="detail-label">Healthcare Facility</span><span class="detail-value">${esc(d.facility_name)}</span></div>
      <div class="detail-item"><span class="detail-label">Location</span><span class="detail-value">${esc(d.facility_city)}, ${esc(d.facility_state)}</span></div>
      <div class="detail-item"><span class="detail-label">Delivery Date</span><span class="detail-value">${formatDate(d.delivery_date)}</span></div>
      <div class="detail-item"><span class="detail-label">Receiving Officer</span><span class="detail-value">${esc(d.received_by)}</span></div>
      <div class="detail-item"><span class="detail-label">Quantity Received</span><span class="detail-value">${Number(d.quantity_received || 0).toLocaleString()} units</span></div>
      <div class="detail-item"><span class="detail-label">Quantity Damaged</span><span class="detail-value">${Number(d.quantity_damaged || 0).toLocaleString()} units</span></div>
      <div class="detail-item"><span class="detail-label">POD Verification</span><span class="detail-value"><code>${esc(d.proof_of_delivery)}</code></span></div>
      <div class="detail-item"><span class="detail-label">Status</span><span class="detail-value">${getStatusBadge(d.delivery_status)}</span></div>
    </div>
    ${d.remarks ? `<div style="margin-top:1rem;"><span class="detail-label">Custody Remarks</span><p style="margin-top:0.35rem; padding:0.75rem; background:var(--bg-subtle); border-radius:8px; font-size:0.84rem;">${esc(d.remarks)}</p></div>` : ''}
  `);
}

async function openCreateDeliveryModal() {
  const lk = await ensureLookups(true);
  const undelivered = lk.shipments.filter(s => !s.has_delivery);
  if (!undelivered.length) {
    openModal('Record Delivery Receipt', `
      <p style="font-size:0.88rem; color:var(--text-secondary); line-height:1.55;">
        All existing shipments already have a verified Proof-of-Delivery record (Oracle enforces one delivery receipt per shipment). Dispatch a new shipment first under <strong>Shipments &amp; Fleet</strong>, then record its hospital receipt here.
      </p>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Close</button>
        <button type="button" class="btn btn-primary" onclick="closeModal(); switchTab('tab-shipments');">Go to Shipments &amp; Fleet</button>
      </div>
    `);
    return;
  }
  openModal('Record Healthcare Delivery Receipt (POD)', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateDelivery(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Pending Shipment <span class="req-star">*</span></label>
          <select id="f-del-shp" class="form-control" required>
            ${undelivered.map(s => `<option value="${s.shipment_id}">#SHP-${s.shipment_id} (${esc(s.origin || '')} → ${esc(s.destination || '')})</option>`).join('')}
          </select>
        </div>
        <div class="form-field full-span">
          <label>Recipient Healthcare Facility <span class="req-star">*</span></label>
          <select id="f-del-fac" class="form-control" required>
            ${lk.facilities.map(f => `<option value="${f.facility_id}">${esc(f.facility_name)} (${esc(f.city)}, ${esc(f.state)})</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Delivery Date <span class="req-star">*</span></label>
          <input type="date" id="f-del-date" class="form-control" value="${todayIso()}" required>
        </div>
        <div class="form-field">
          <label>Receiving Pharmacist / Officer <span class="req-star">*</span></label>
          <input type="text" id="f-del-recby" class="form-control" placeholder="Dr. K. Nair, Chief Pharmacist" required>
        </div>
        <div class="form-field">
          <label>Quantity Received <span class="req-star">*</span></label>
          <input type="number" id="f-del-qrec" class="form-control" value="250" min="0" required>
        </div>
        <div class="form-field">
          <label>Quantity Damaged</label>
          <input type="number" id="f-del-qdmg" class="form-control" value="0" min="0">
        </div>
        <div class="form-field full-span">
          <label>Proof of Delivery (POD) Reference <span class="req-star">*</span></label>
          <input type="text" id="f-del-pod" class="form-control" value="POD-SIG-${Date.now().toString().slice(-5)}" required>
        </div>
        <div class="form-field full-span">
          <label>Chain-of-Custody Remarks</label>
          <input type="text" id="f-del-rem" class="form-control" value="Seal intact; arrival core temperature verified within 2°C–8°C.">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Record Delivery Receipt</button>
      </div>
    </form>
  `);
}

async function submitCreateDelivery(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/deliveries', {
      method: 'POST',
      body: {
        shipment_id: document.getElementById('f-del-shp').value,
        facility_id: document.getElementById('f-del-fac').value,
        delivery_date: document.getElementById('f-del-date').value,
        received_by: document.getElementById('f-del-recby').value,
        quantity_received: document.getElementById('f-del-qrec').value,
        quantity_damaged: document.getElementById('f-del-qdmg').value,
        proof_of_delivery: document.getElementById('f-del-pod').value,
        remarks: document.getElementById('f-del-rem').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadDeliveriesModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

function openUpdateDeliveryModal(delivId) {
  const d = store.deliveries.find(x => x.delivery_id === delivId);
  if (!d) return;
  openModal(`Update Delivery POD — #DEL-${d.delivery_id}`, `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitUpdateDelivery(event, ${d.delivery_id})">
      <div class="form-grid">
        <div class="form-field">
          <label>Quantity Received <span class="req-star">*</span></label>
          <input type="number" id="f-udel-qrec" class="form-control" value="${d.quantity_received || 0}" min="0" required>
        </div>
        <div class="form-field">
          <label>Quantity Damaged <span class="req-star">*</span></label>
          <input type="number" id="f-udel-qdmg" class="form-control" value="${d.quantity_damaged || 0}" min="0" required>
        </div>
        <div class="form-field">
          <label>Delivery Status</label>
          <select id="f-udel-st" class="form-control">
            <option value="Delivered" ${d.delivery_status === 'Delivered' ? 'selected' : ''}>Delivered</option>
          </select>
        </div>
        <div class="form-field">
          <label>POD Reference <span class="req-star">*</span></label>
          <input type="text" id="f-udel-pod" class="form-control" value="${esc(d.proof_of_delivery || '')}" required>
        </div>
        <div class="form-field full-span">
          <label>Audit Remarks</label>
          <textarea id="f-udel-rem" class="form-control">${esc(d.remarks || '')}</textarea>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Update POD</button>
      </div>
    </form>
  `);
}

async function submitUpdateDelivery(e, delivId) {
  e.preventDefault();
  try {
    const res = await apiRequest(`/api/deliveries/${delivId}`, {
      method: 'PATCH',
      body: {
        delivery_status: document.getElementById('f-udel-st').value,
        quantity_received: document.getElementById('f-udel-qrec').value,
        quantity_damaged: document.getElementById('f-udel-qdmg').value,
        proof_of_delivery: document.getElementById('f-udel-pod').value,
        remarks: document.getElementById('f-udel-rem').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await loadDeliveriesModule();
    loadCommandCenter();
  } catch (err) {
    showFormError(err.message);
  }
}

function openCreateFacilityModal() {
  openModal('Register Healthcare Recipient Facility', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateFacility(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Facility Name <span class="req-star">*</span></label>
          <input type="text" id="f-fac-name" class="form-control" placeholder="Apollo Speciality Medical Institute" required>
        </div>
        <div class="form-field">
          <label>License Number (Unique) <span class="req-star">*</span></label>
          <input type="text" id="f-fac-lic" class="form-control" placeholder="HOSP-LIC-2026-44" required>
        </div>
        <div class="form-field">
          <label>Facility Type</label>
          <select id="f-fac-type" class="form-control">
            <option value="Multispecialty Hospital">Multispecialty Hospital</option>
            <option value="TEACHING HOSPITAL">Teaching Hospital</option>
            <option value="GOVERNMENT HOSPITAL">Government Hospital</option>
          </select>
        </div>
        <div class="form-field">
          <label>Contact Phone <span class="req-star">*</span></label>
          <input type="text" id="f-fac-phone" class="form-control" placeholder="+91-80-41209900" required>
        </div>
        <div class="form-field">
          <label>City <span class="req-star">*</span></label>
          <input type="text" id="f-fac-city" class="form-control" placeholder="Bengaluru" required>
        </div>
        <div class="form-field">
          <label>State <span class="req-star">*</span></label>
          <input type="text" id="f-fac-state" class="form-control" placeholder="Karnataka" required>
        </div>
        <div class="form-field full-span">
          <label>Address <span class="req-star">*</span></label>
          <input type="text" id="f-fac-addr" class="form-control" placeholder="Bannerghatta Road, Medical Campus" required>
        </div>
        <div class="form-field full-span">
          <label>Cold-Storage Capability</label>
          <input type="text" id="f-fac-cap" class="form-control" value="Walk-in 2°C–8°C Cold Room + Ultra-Low Freezer">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Register Facility</button>
      </div>
    </form>
  `);
}

async function submitCreateFacility(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/facilities', {
      method: 'POST',
      body: {
        facility_name: document.getElementById('f-fac-name').value,
        license_number: document.getElementById('f-fac-lic').value,
        facility_type: document.getElementById('f-fac-type').value,
        contact_number: document.getElementById('f-fac-phone').value,
        city: document.getElementById('f-fac-city').value,
        state: document.getElementById('f-fac-state').value,
        address: document.getElementById('f-fac-addr').value,
        storage_capability: document.getElementById('f-fac-cap').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await ensureLookups(true);
    await loadDeliveriesModule();
  } catch (err) {
    showFormError(err.message);
  }
}

function openCreateDistCenterModal() {
  openModal('Register Regional Distribution Center', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateDistCenter(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Center Name <span class="req-star">*</span></label>
          <input type="text" id="f-dc-name" class="form-control" placeholder="Western Cryo Distribution Hub" required>
        </div>
        <div class="form-field">
          <label>Manager Name <span class="req-star">*</span></label>
          <input type="text" id="f-dc-mgr" class="form-control" placeholder="A. Kulkarni" required>
        </div>
        <div class="form-field">
          <label>City <span class="req-star">*</span></label>
          <input type="text" id="f-dc-city" class="form-control" placeholder="Pune" required>
        </div>
        <div class="form-field">
          <label>State <span class="req-star">*</span></label>
          <input type="text" id="f-dc-state" class="form-control" placeholder="Maharashtra" required>
        </div>
        <div class="form-field">
          <label>Capacity (Units) <span class="req-star">*</span></label>
          <input type="number" id="f-dc-cap" class="form-control" value="35000" min="100" required>
        </div>
        <div class="form-field">
          <label>Contact Number <span class="req-star">*</span></label>
          <input type="text" id="f-dc-phone" class="form-control" placeholder="+91-20-66701122" required>
        </div>
        <div class="form-field full-span">
          <label>Address <span class="req-star">*</span></label>
          <input type="text" id="f-dc-addr" class="form-control" placeholder="Chakan Industrial Cold Park, Phase II" required>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Register Distribution Center</button>
      </div>
    </form>
  `);
}

async function submitCreateDistCenter(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/distribution-centers', {
      method: 'POST',
      body: {
        center_name: document.getElementById('f-dc-name').value,
        manager_name: document.getElementById('f-dc-mgr').value,
        city: document.getElementById('f-dc-city').value,
        state: document.getElementById('f-dc-state').value,
        capacity: document.getElementById('f-dc-cap').value,
        contact_number: document.getElementById('f-dc-phone').value,
        address: document.getElementById('f-dc-addr').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    await loadDeliveriesModule();
  } catch (err) {
    showFormError(err.message);
  }
}

/* --------------------------------------------------------------------------
   11. PAGE 8: Reports & Analytics + CSV Export
   -------------------------------------------------------------------------- */
async function loadReportsModule(forceToast = false) {
  try {
    const expDays = document.getElementById('report-expiry-window')?.value || '';
    const url = expDays ? `/api/reports/overview?expiry_days=${encodeURIComponent(expDays)}` : '/api/reports/overview';
    store.reports = await apiRequest(url);

    // Populate real KPI cards from Oracle report rows
    const delivRows = store.reports.delivery_performance || [];
    const totRec = delivRows.reduce((s, r) => s + Number(r.total_received || 0), 0);
    const totDmg = delivRows.reduce((s, r) => s + Number(r.total_damaged || 0), 0);
    const integrity = totRec + totDmg > 0 ? ((totRec / (totRec + totDmg)) * 100).toFixed(2) : '100.00';
    document.getElementById('rep-kpi-integrity').textContent = integrity;
    document.getElementById('rep-kpi-integrity-sub').textContent = `${totRec.toLocaleString()} intact / ${totDmg} damaged`;

    const nearExp = (store.reports.batch_expiry || []).filter(b => Number(b.days_to_expiry) <= 180).length;
    document.getElementById('rep-kpi-expiry').textContent = nearExp;

    const incRows = store.reports.incident_resolution || [];
    const totInc = incRows.reduce((s, r) => s + Number(r.incident_count || 0), 0);
    const resInc = incRows
      .filter(r => ['RESOLVED', 'CLOSED'].includes(String(r.resolution_status || '').toUpperCase()))
      .reduce((s, r) => s + Number(r.incident_count || 0), 0);
    document.getElementById('rep-kpi-incrate').textContent = totInc > 0 ? ((resInc / totInc) * 100).toFixed(1) : '0.0';
    document.getElementById('rep-kpi-incrate-sub').textContent = `${resInc} of ${totInc} resolved`;

    const totStock = (store.reports.inventory_availability || []).reduce((s, r) => s + Number(r.total_stock_units || 0), 0);
    document.getElementById('rep-kpi-stock').textContent = totStock.toLocaleString();

    renderReportCharts();
    renderSelectedReportTable();
    if (forceToast) showToast('Analytical SQL reports refreshed.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderReportCharts() {
  if (!window.Chart || !store.reports) return;

  const whCtx = document.getElementById('warehouseReportChart');
  const topWh = (store.reports.inventory_availability || []).filter(w => Number(w.total_stock_units) > 0).slice(0, 7);
  if (warehouseChartInstance) warehouseChartInstance.destroy();
  warehouseChartInstance = new Chart(whCtx, {
    type: 'bar',
    data: {
      labels: topWh.map(w => w.warehouse_name),
      datasets: [
        { label: 'Available', data: topWh.map(w => w.available_units), backgroundColor: '#102D49', borderRadius: 6 },
        { label: 'Reserved', data: topWh.map(w => w.reserved_units), backgroundColor: '#70D9F0', borderColor: '#287FE5', borderWidth: 1, borderRadius: 6 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: '#526C86', font: { size: 10 } } },
        y: { stacked: true, grid: { color: '#E5EFFA' }, ticks: { color: '#526C86' } },
      },
    },
  });

  const exCtx = document.getElementById('excursionReportChart');
  const sevTotals = {};
  (store.reports.excursion_summary || []).forEach(r => {
    const k = r.severity_group || 'OTHER';
    sevTotals[k] = (sevTotals[k] || 0) + Number(r.alert_count || 0);
  });
  const sevKeys = Object.keys(sevTotals);
  const sevColorMap = key => {
    const u = String(key || '').toUpperCase();
    if (u.includes('CRITICAL')) return '#B91F3A';
    if (u.includes('HIGH')) return '#F16F59';
    if (u.includes('MEDIUM') || u.includes('WARN')) return '#D99020';
    if (u.includes('LOW') || u.includes('INFO')) return '#287FE5';
    return '#173C59';
  };
  if (excursionChartInstance) excursionChartInstance.destroy();
  excursionChartInstance = new Chart(exCtx, {
    type: 'doughnut',
    data: {
      labels: sevKeys,
      datasets: [
        {
          data: sevKeys.map(k => sevTotals[k]),
          backgroundColor: sevKeys.map(sevColorMap),
          borderWidth: 2,
          borderColor: '#FFFFFF',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'right' } },
    },
  });
}

function renderSelectedReportTable() {
  if (!store.reports) return;
  const key = document.getElementById('report-selector')?.value || 'batch_expiry';
  const rows = store.reports[key] || [];

  const configs = {
    batch_expiry: {
      title: 'Product & Batch Shelf-Life Expiry Intelligence',
      columns: [
        { key: 'batch_number', label: 'Batch', render: r => `<code>${esc(r.batch_number)}</code>` },
        { key: 'product_name', label: 'Product', render: r => `<strong>${esc(r.product_name)}</strong>` },
        { key: 'manufacturer_name', label: 'Manufacturer' },
        { key: 'expiry_date', label: 'Expiry Date', render: r => formatDate(r.expiry_date) },
        { key: 'days_to_expiry', label: 'Days Remaining', render: r => `<strong class="mono-id">${r.days_to_expiry}d</strong>` },
        { key: 'expiry_risk', label: 'Risk Band', render: r => getStatusBadge(r.expiry_risk.includes('Expired') || r.expiry_risk.includes('Critical') ? 'High' : (r.expiry_risk.includes('Near') ? 'Pending' : 'Active')).replace(/High|Pending|Active/, esc(r.expiry_risk)) },
        { key: 'batch_status', label: 'Batch Status', render: r => getStatusBadge(r.batch_status) },
      ],
    },
    delivery_performance: {
      title: 'Healthcare Facility Delivery Performance & Damage Audit',
      columns: [
        { key: 'facility_name', label: 'Healthcare Facility', render: r => `<strong>${esc(r.facility_name)}</strong>` },
        { key: 'city', label: 'Location', render: r => `${esc(r.city)}, ${esc(r.state)}` },
        { key: 'deliveries_count', label: 'Deliveries' },
        { key: 'total_received', label: 'Units Received', render: r => Number(r.total_received).toLocaleString() },
        { key: 'total_damaged', label: 'Units Damaged', render: r => Number(r.total_damaged) > 0 ? `<strong style="color:var(--status-critical)">${r.total_damaged}</strong>` : '0' },
        { key: 'damage_rate_pct', label: 'Damage Rate', render: r => `${r.damage_rate_pct}%` },
      ],
    },
    inventory_availability: {
      title: 'Warehouse Inventory Availability & Chamber Count',
      columns: [
        { key: 'warehouse_name', label: 'Warehouse', render: r => `<strong>${esc(r.warehouse_name)}</strong>` },
        { key: 'city', label: 'Location', render: r => `${esc(r.city)}, ${esc(r.state)}` },
        { key: 'storage_units', label: 'Storage Units' },
        { key: 'stock_lots', label: 'Stock Lots' },
        { key: 'available_units', label: 'Available Units', render: r => Number(r.available_units).toLocaleString() },
        { key: 'reserved_units', label: 'Reserved Units', render: r => Number(r.reserved_units).toLocaleString() },
        { key: 'total_stock_units', label: 'Total Stock', render: r => `<strong>${Number(r.total_stock_units).toLocaleString()}</strong>` },
      ],
    },
    excursion_summary: {
      title: 'Temperature Excursion Breakdown by Severity & Status',
      columns: [
        { key: 'severity_group', label: 'Severity', render: r => getStatusBadge(r.severity_group) },
        { key: 'status_group', label: 'Alert Status', render: r => getStatusBadge(r.status_group) },
        { key: 'alert_count', label: 'Alert Count' },
        { key: 'avg_recorded_temp', label: 'Mean Recorded Temp', render: r => `${r.avg_recorded_temp}°C` },
        { key: 'max_deviation_c', label: 'Peak Deviation', render: r => `+${r.max_deviation_c}°C` },
      ],
    },
    incident_resolution: {
      title: 'Compliance Incident Resolution Metrics',
      columns: [
        { key: 'incident_type', label: 'Incident Type', render: r => `<strong>${esc(r.incident_type)}</strong>` },
        { key: 'severity', label: 'Severity', render: r => getStatusBadge(r.severity) },
        { key: 'resolution_status', label: 'Resolution Status', render: r => getStatusBadge(r.resolution_status) },
        { key: 'incident_count', label: 'Count' },
        { key: 'avg_resolution_days', label: 'Avg Resolution Days', render: r => r.avg_resolution_days !== null ? `${r.avg_resolution_days} days` : 'Open' },
      ],
    },
    shipment_summary: {
      title: 'Shipment Status & Priority Summary',
      columns: [
        { key: 'shipment_status', label: 'Shipment Status', render: r => getStatusBadge(r.shipment_status) },
        { key: 'priority_level', label: 'Priority Level', render: r => getPriorityBadge(r.priority_level) },
        { key: 'shipment_count', label: 'Shipments' },
        { key: 'avg_weight_kg', label: 'Avg Payload Weight', render: r => `${r.avg_weight_kg} kg` },
        { key: 'total_distance_km', label: 'Cumulative Corridor Distance', render: r => `${Number(r.total_distance_km).toLocaleString()} km` },
      ],
    },
  };

  const cfg = configs[key] || configs.batch_expiry;
  renderEnterpriseTable({
    containerId: 'card-active-report-table',
    tableKey: `report_${key}`,
    title: cfg.title,
    rows,
    columns: cfg.columns,
  });
}

function exportActiveReportCsv() {
  const key = document.getElementById('report-selector')?.value || 'batch_expiry';
  window.location.href = `/api/reports/export/${encodeURIComponent(key)}`;
}

/* --------------------------------------------------------------------------
   12. PAGE 9: User & Access Management (Accounts, Invitations, Matrix, Scopes, Audit)
   -------------------------------------------------------------------------- */
const CRYOTRACK_ROLES = [
  'Administrator',
  'Operations Manager',
  'Shipping & Fleet Operator',
  'Cold-Chain Monitoring Operator',
  'Inventory & Warehouse Operator',
  'Quality & Compliance Operator',
  'Delivery Operator',
  'Viewer / Auditor',
];

const CRYOTRACK_DEPARTMENTS = [
  'Administration & Governance',
  'Operations Management',
  'Shipping & Fleet',
  'Cold-Chain Monitoring',
  'Inventory & Warehousing',
  'Quality & Compliance',
  'Deliveries & Distribution',
  'Audit & Oversight',
];

function switchUsersSubView(subView) {
  currentUsersSubView = subView;
  document.querySelectorAll('.subnav-pill').forEach(b => {
    b.classList.toggle('active', b.dataset.subview === subView);
  });
  document.querySelectorAll('.users-subview-panel').forEach(p => {
    p.style.display = 'none';
  });
  const activePanel = document.getElementById(`users-subview-${subView}`);
  if (activePanel) activePanel.style.display = 'block';

  refreshCurrentUsersSubView();
}

function refreshCurrentUsersSubView() {
  if (currentUsersSubView === 'accounts') loadUsersModule();
  else if (currentUsersSubView === 'invitations') loadInvitationsSubView();
  else if (currentUsersSubView === 'matrix') loadPermissionsMatrixSubView();
  else if (currentUsersSubView === 'audit') loadAuditSubView();
}

async function loadUsersModule() {
  try {
    store.users = await apiRequest('/api/users');
    renderEnterpriseTable({
      containerId: 'card-users-table',
      tableKey: 'users',
      title: 'CryoTrack Authorized User Accounts',
      rows: store.users,
      columns: [
        {
          key: 'full_name',
          label: 'User Name',
          render: r => `<strong>${esc(r.full_name)}</strong><br><small style="color:var(--text-muted)">${esc(r.department || 'Unassigned')}</small>`,
        },
        { key: 'email', label: 'Email Address', render: r => `<code>${esc(r.email)}</code>` },
        {
          key: 'role',
          label: 'Access Role',
          render: r => `<span class="role-badge role-${esc(r.role.toLowerCase().replace(/[^a-z0-9]/g, '-'))}">${esc(r.role)}</span>`,
        },
        {
          key: 'status',
          label: 'Account Status',
          render: r => {
            if (r.status === 'Pending Approval') {
              return `<span class="badge badge-warning" style="display:inline-flex; align-items:center; gap:4px;"><span class="pulse-dot warning" style="width:6px; height:6px;"></span>Pending Approval</span>`;
            }
            return getStatusBadge(r.status);
          },
        },
        { key: 'auth_provider', label: 'Provider', render: r => `<span class="badge badge-neutral">${esc(r.auth_provider || 'Local')}</span>` },
        { key: 'created_at', label: 'Provisioned', render: r => formatDate(r.created_at) },
        {
          key: 'actions',
          label: 'Governance Actions',
          sortable: false,
          render: r => {
            const isSelf = r.email.toLowerCase() === USER_EMAIL.toLowerCase();
            if (isSelf) return '<span style="font-size:0.75rem; color:var(--text-muted)">Current Session</span>';

            let buttons = [];
            if (r.status === 'Pending Approval' && IS_ADMIN) {
              buttons.push(`<button class="btn btn-success btn-sm" onclick="approveUserAccount(${r.id || r.user_id}, '${esc(r.email)}')">Approve</button>`);
            }
            if (hasPermission('users:manage')) {
              buttons.push(`<button class="btn btn-outline btn-sm" onclick="openEditUserRoleModal('${esc(r.email)}', '${esc(r.role)}', '${esc(r.department || '')}', '${esc(r.full_name)}')">Edit</button>`);
              if (IS_ADMIN) {
                buttons.push(`<button class="btn btn-outline btn-sm" onclick="openManageUserScopesModal(${r.id || r.user_id}, '${esc(r.full_name)}')">Scopes</button>`);
              }
              const toggleLabel = r.status === 'Active' ? 'Deactivate' : 'Activate';
              const nextStatus = r.status === 'Active' ? 'Disabled' : 'Active';
              if (r.status !== 'Pending Approval') {
                buttons.push(`<button class="btn ${r.status === 'Active' ? 'btn-danger-outline' : 'btn-success'} btn-sm" onclick="confirmToggleUserStatus('${esc(r.email)}', '${nextStatus}')">${toggleLabel}</button>`);
              }
            }
            return `<div style="display:flex; gap:0.35rem; flex-wrap:wrap;">${buttons.join('')}</div>`;
          },
        },
      ],
    });
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function approveUserAccount(userId, email) {
  if (!confirm(`Approve and activate privileged access for account ${email}?`)) return;
  try {
    const res = await apiRequest(`/api/users/${userId}/approve`, { method: 'POST' });
    showToast(res.message, 'success');
    loadUsersModule();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function confirmToggleUserStatus(email, nextStatus) {
  const action = nextStatus === 'Active' ? 'activate' : 'suspend';
  if (!confirm(`Are you sure you want to ${action} account: ${email}?`)) return;
  try {
    const res = await apiRequest(`/api/users/${encodeURIComponent(email)}`, {
      method: 'PATCH',
      body: { status: nextStatus },
    });
    showToast(res.message, 'success');
    loadUsersModule();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openCreateUserModal() {
  openModal('Direct User Provisioning (Administrator)', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitCreateUser(event)">
      <div class="form-grid">
        <div class="form-field">
          <label>Full Display Name <span class="req-star">*</span></label>
          <input type="text" id="f-usr-name" class="form-control" placeholder="Dr. Elena Rostova" required>
        </div>
        <div class="form-field">
          <label>Corporate Email Address <span class="req-star">*</span></label>
          <input type="email" id="f-usr-email" class="form-control" placeholder="elena.rostova@cryotrack.io" required>
        </div>
        <div class="form-field">
          <label>Access Role <span class="req-star">*</span></label>
          <select id="f-usr-role" class="form-control" onchange="autoSelectDepartmentForRole(this.value)">
            ${CRYOTRACK_ROLES.map(r => `<option value="${r}">${r}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Department <span class="req-star">*</span></label>
          <select id="f-usr-dept" class="form-control">
            ${CRYOTRACK_DEPARTMENTS.map(d => `<option value="${d}">${d}</option>`).join('')}
          </select>
        </div>
        <div class="form-field full-span">
          <label>Temporary Password <span class="req-star">*</span></label>
          <input type="password" id="f-usr-pwd" class="form-control" placeholder="Min 8 chars, uppercase, lowercase &amp; digit" required>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Provision Account</button>
      </div>
    </form>
  `);
}

function autoSelectDepartmentForRole(role) {
  const map = {
    'Administrator': 'Administration & Governance',
    'Operations Manager': 'Operations Management',
    'Shipping & Fleet Operator': 'Shipping & Fleet',
    'Cold-Chain Monitoring Operator': 'Cold-Chain Monitoring',
    'Inventory & Warehouse Operator': 'Inventory & Warehousing',
    'Quality & Compliance Operator': 'Quality & Compliance',
    'Delivery Operator': 'Deliveries & Distribution',
    'Viewer / Auditor': 'Audit & Oversight',
  };
  const deptSelect = document.getElementById('f-usr-dept');
  if (deptSelect && map[role]) {
    deptSelect.value = map[role];
  }
}

async function submitCreateUser(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/users', {
      method: 'POST',
      body: {
        full_name: document.getElementById('f-usr-name').value,
        email: document.getElementById('f-usr-email').value,
        role: document.getElementById('f-usr-role').value,
        department: document.getElementById('f-usr-dept').value,
        password: document.getElementById('f-usr-pwd').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    loadUsersModule();
  } catch (err) {
    showFormError(err.message);
  }
}

function openEditUserRoleModal(email, currentRole, currentDept, fullName) {
  openModal(`Governance & Role — ${fullName}`, `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitEditUserRole(event, '${esc(email)}')">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Assigned Access Role for <code>${esc(email)}</code></label>
          <select id="f-eur-role" class="form-control">
            ${CRYOTRACK_ROLES.map(r => `<option value="${r}" ${r === currentRole ? 'selected' : ''}>${r}</option>`).join('')}
          </select>
        </div>
        <div class="form-field full-span">
          <label>Assigned Department</label>
          <select id="f-eur-dept" class="form-control">
            ${CRYOTRACK_DEPARTMENTS.map(d => `<option value="${d}" ${d === currentDept ? 'selected' : ''}>${d}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Update Authorization</button>
      </div>
    </form>
  `);
}

async function submitEditUserRole(e, email) {
  e.preventDefault();
  try {
    const res = await apiRequest(`/api/users/${encodeURIComponent(email)}`, {
      method: 'PATCH',
      body: {
        role: document.getElementById('f-eur-role').value,
        department: document.getElementById('f-eur-dept').value,
      },
    });
    closeModal();
    showToast(res.message, 'success');
    loadUsersModule();
  } catch (err) {
    showFormError(err.message);
  }
}

/* --------------------------------------------------------------------------
   Invitations & Onboarding Sub-View
   -------------------------------------------------------------------------- */
async function loadInvitationsSubView() {
  try {
    const invites = await apiRequest('/api/invitations');
    renderEnterpriseTable({
      containerId: 'card-invitations-table',
      tableKey: 'invitations',
      title: 'Cryptographic Invitations & Onboarding Registry',
      rows: invites,
      columns: [
        { key: 'intended_email', label: 'Intended Recipient', render: r => `<strong>${esc(r.intended_email)}</strong>` },
        {
          key: 'assigned_role',
          label: 'Pre-Assigned Role',
          render: r => `<span class="role-badge role-${esc(r.assigned_role.toLowerCase().replace(/[^a-z0-9]/g, '-'))}">${esc(r.assigned_role)}</span>`,
        },
        { key: 'department', label: 'Department', render: r => esc(r.department) },
        { key: 'status', label: 'Token Status', render: r => getStatusBadge(r.status) },
        { key: 'created_by', label: 'Issued By', render: r => `<small>${esc(r.created_by)}</small>` },
        { key: 'expires_at', label: 'Expires', render: r => formatDate(r.expires_at) },
        {
          key: 'actions',
          label: 'Action',
          sortable: false,
          render: r => {
            if (r.status === 'Active') {
              return `<button class="btn btn-danger-outline btn-sm" onclick="revokeInvitation('${esc(r.invitation_uuid)}')">Revoke</button>`;
            }
            return `<span style="font-size:0.75rem; color:var(--text-muted)">${esc(r.status)}</span>`;
          },
        },
      ],
    });
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openIssueInvitationModal() {
  openModal('Issue Cryptographic Team Invitation', `
    <div id="modal-form-error" class="form-error-banner"></div>
    <form onsubmit="submitIssueInvitation(event)">
      <div class="form-grid">
        <div class="form-field full-span">
          <label>Intended Recipient Corporate Email <span class="req-star">*</span></label>
          <input type="email" id="f-inv-email" class="form-control" placeholder="colleague@pharmaceutical.org" required>
        </div>
        <div class="form-field">
          <label>Assigned Access Role <span class="req-star">*</span></label>
          <select id="f-inv-role" class="form-control">
            ${CRYOTRACK_ROLES.map(r => `<option value="${r}">${r}</option>`).join('')}
          </select>
        </div>
        <div class="form-field">
          <label>Department <span class="req-star">*</span></label>
          <select id="f-inv-dept" class="form-control">
            ${CRYOTRACK_DEPARTMENTS.map(d => `<option value="${d}">${d}</option>`).join('')}
          </select>
        </div>
        <div class="form-field full-span">
          <label>Token Validity Window <span class="req-star">*</span></label>
          <select id="f-inv-days" class="form-control" onchange="toggleCustomDays(this.value)">
            <option value="1">1 Day</option>
            <option value="7" selected>7 Days (Standard)</option>
            <option value="30">30 Days (1 Month)</option>
            <option value="90">90 Days (Quarterly)</option>
            <option value="180">180 Days (Half Year)</option>
            <option value="365">1 Year (365 Days)</option>
            <option value="730">2 Years (730 Days)</option>
            <option value="1095">3 Years (1095 Days)</option>
            <option value="1825">5 Years (1825 Days)</option>
            <option value="custom">Custom Duration...</option>
          </select>
          <div id="f-inv-custom-wrapper" style="display:none; margin-top:0.6rem;">
            <label style="font-size:0.78rem; color:var(--text-muted); display:block; margin-bottom:0.25rem;">Custom Expiration Horizon (1 to 1825 Days):</label>
            <input type="number" id="f-inv-custom-days" class="form-control" min="1" max="1825" placeholder="Enter number of days (e.g. 14)">
          </div>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Generate Invitation Key</button>
      </div>
    </form>
  `);
}

function toggleCustomDays(val) {
  const w = document.getElementById('f-inv-custom-wrapper');
  if (w) w.style.display = val === 'custom' ? 'block' : 'none';
}

async function submitIssueInvitation(e) {
  e.preventDefault();
  try {
    let daysVal = document.getElementById('f-inv-days').value;
    if (daysVal === 'custom') {
      const customInput = document.getElementById('f-inv-custom-days');
      daysVal = customInput ? customInput.value : '';
      if (!daysVal || Number(daysVal) < 1 || Number(daysVal) > 1825) {
        showFormError('Custom expiration duration must be between 1 day and 1825 days (5 years).');
        return;
      }
    }

    const res = await apiRequest('/api/invitations', {
      method: 'POST',
      body: {
        email: document.getElementById('f-inv-email').value,
        role: document.getElementById('f-inv-role').value,
        department: document.getElementById('f-inv-dept').value,
        expires_in_days: daysVal,
      },
    });

    const invite = res.invitation;
    openModal('Invitation Successfully Generated', `
      <div style="padding:1rem 0;">
        <p style="font-size:0.9rem; margin-bottom:1rem; color:var(--text-main);">
          Share this one-time cryptographic invitation key securely with <strong>${esc(invite.intended_email)}</strong>. They must enter this key during onboarding at <code>/register</code>.
        </p>
        <div style="background:var(--bg-glass); border:1px solid var(--border-glass); border-radius:8px; padding:1rem; margin-bottom:1rem;">
          <div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-muted); margin-bottom:0.35rem;">Cryptographic Key</div>
          <div style="font-family:monospace; font-size:1.15rem; font-weight:700; color:var(--brand-primary); word-break:break-all;" id="display-inv-key">${esc(invite.invitation_key)}</div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <small style="color:var(--text-muted)">Expires on: ${formatDate(invite.expires_at)}</small>
          <button class="btn btn-primary btn-sm" onclick="copyToClipboard('${esc(invite.invitation_key)}')">Copy Key</button>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-outline" onclick="closeModal(); switchUsersSubView('invitations');">Done</button>
      </div>
    `);
  } catch (err) {
    showFormError(err.message);
  }
}

async function revokeInvitation(uuid) {
  if (!confirm('Are you sure you want to revoke this invitation key? It will be rendered permanently invalid.')) return;
  try {
    const res = await apiRequest(`/api/invitations/${uuid}/revoke`, { method: 'POST' });
    showToast(res.message, 'success');
    loadInvitationsSubView();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* --------------------------------------------------------------------------
   Role-Permission Matrix Sub-View
   -------------------------------------------------------------------------- */
async function loadPermissionsMatrixSubView() {
  try {
    const matrix = await apiRequest('/api/permissions/matrix');
    const container = document.getElementById('card-matrix-table');
    if (!container) return;

    let html = `
      <div style="padding:1.25rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
          <div>
            <h3 style="margin:0; font-size:1.1rem; font-weight:600;">8-Role × 31-Action Authorization Matrix</h3>
            <p style="margin:0.25rem 0 0; font-size:0.8rem; color:var(--text-muted);">Platform-wide server-enforced role permissions for granular access governance.</p>
          </div>
          ${IS_ADMIN ? `<span class="badge badge-success">Administrator Live Matrix</span>` : `<span class="badge badge-neutral">Auditor View</span>`}
        </div>
        <div style="overflow-x:auto;">
          <table class="enterprise-table" style="font-size:0.8rem;">
            <thead>
              <tr>
                <th style="min-width:220px;">Role / Domain</th>
                ${matrix.permissions.map(p => `<th style="text-align:center; font-size:0.7rem; white-space:nowrap;" title="${esc(p.description)}">${esc(p.name)}</th>`).join('')}
              </tr>
            </thead>
            <tbody>
    `;

    matrix.roles.forEach(role => {
      html += `<tr><td><strong>${esc(role.name)}</strong></td>`;
      matrix.permissions.forEach(p => {
        const has = role.permissions.includes(p.key);
        html += `<td style="text-align:center;">${has ? '<span style="color:var(--success); font-weight:700;">✓</span>' : '<span style="color:var(--text-muted); opacity:0.35;">—</span>'}</td>`;
      });
      html += `</tr>`;
    });

    html += `
            </tbody>
          </table>
        </div>
      </div>
    `;
    container.innerHTML = html;
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* --------------------------------------------------------------------------
   Security Audit History Sub-View
   -------------------------------------------------------------------------- */
async function loadAuditSubView() {
  try {
    const events = await apiRequest('/api/audit/events?limit=100');
    renderEnterpriseTable({
      containerId: 'card-audit-table',
      tableKey: 'audit',
      title: 'Immutable Security & Authorization Audit Trail (Latest 100 Events)',
      rows: events,
      columns: [
        { key: 'timestamp', label: 'Event Time', render: r => formatDate(r.timestamp) },
        {
          key: 'event_type',
          label: 'Event Type',
          render: r => {
            let badgeClass = 'badge-neutral';
            if (r.event_type.includes('SUCCESS') || r.event_type.includes('APPROVED')) badgeClass = 'badge-success';
            if (r.event_type.includes('FAIL') || r.event_type.includes('DENIED') || r.event_type.includes('LOCKED')) badgeClass = 'badge-danger';
            if (r.event_type.includes('INVITATION') || r.event_type.includes('PENDING')) badgeClass = 'badge-warning';
            return `<span class="badge ${badgeClass}">${esc(r.event_type)}</span>`;
          },
        },
        { key: 'actor_email', label: 'Actor', render: r => `<code>${esc(r.actor_email || 'Anonymous')}</code>` },
        { key: 'target_identifier', label: 'Target Resource', render: r => `<strong>${esc(r.target_identifier || '—')}</strong>` },
        { key: 'status', label: 'Status', render: r => getStatusBadge(r.status) },
        { key: 'details', label: 'Audit Details', render: r => `<small style="color:var(--text-muted);">${esc(r.details || '')}</small>` },
      ],
    });
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* --------------------------------------------------------------------------
   Record Authorization Scopes Modal
   -------------------------------------------------------------------------- */
async function openManageUserScopesModal(userId, fullName) {
  try {
    const data = await apiRequest(`/api/users/${userId}/scopes`);
    const scopes = data.scopes || [];
    const scopeTypes = ['ALL_RECORDS', 'WAREHOUSE', 'SHIPMENT', 'ROUTE', 'VEHICLE', 'FACILITY'];

    openModal(`Regional Record Scopes — ${fullName}`, `
      <div id="modal-form-error" class="form-error-banner"></div>
      <form onsubmit="submitManageUserScopes(event, ${userId})">
        <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1rem;">
          Assign explicit record-level visibility restrictions for this user account. When scoped, queries will strictly filter to assigned entities.
        </p>
        <div class="form-grid">
          <div class="form-field">
            <label>Scope Type <span class="req-star">*</span></label>
            <select id="f-scope-type" class="form-control">
              ${scopeTypes.map(st => `<option value="${st}">${st}</option>`).join('')}
            </select>
          </div>
          <div class="form-field">
            <label>Record / Target ID (e.g. 101, or ALL)</label>
            <input type="text" id="f-scope-val" class="form-control" placeholder="101" value="*">
          </div>
        </div>
        <div style="margin:1rem 0;">
          <h4 style="font-size:0.85rem; font-weight:600; margin-bottom:0.5rem;">Current Scopes (${scopes.length}):</h4>
          <ul style="font-size:0.8rem; color:var(--text-main); padding-left:1.25rem;">
            ${scopes.length === 0 ? '<li><em>No explicit scopes (Global platform access active)</em></li>' : scopes.map(s => `<li><code>${esc(s.scope_type)}</code>: ${esc(s.target_id || '*')}</li>`).join('')}
          </ul>
        </div>
        <div class="form-actions">
          <button type="button" class="btn btn-outline" onclick="closeModal()">Close</button>
          <button type="submit" class="btn btn-primary">Save Scope</button>
        </div>
      </form>
    `);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function submitManageUserScopes(e, userId) {
  e.preventDefault();
  const st = document.getElementById('f-scope-type').value;
  const sv = document.getElementById('f-scope-val').value.trim() || '*';
  try {
    const res = await apiRequest(`/api/users/${userId}/scopes`, {
      method: 'POST',
      body: {
        scopes: [{ scope_type: st, target_id: sv }],
      },
    });
    closeModal();
    showToast(res.message, 'success');
  } catch (err) {
    showFormError(err.message);
  }
}


/* --------------------------------------------------------------------------
   13. PAGE 10: Settings & Restrained System Health Check
   -------------------------------------------------------------------------- */
async function submitOwnProfile(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/settings/profile', {
      method: 'PATCH',
      body: { full_name: document.getElementById('set-full-name').value },
    });
    document.getElementById('header-user-name').textContent = res.user.full_name;
    document.getElementById('dropdown-user-name').textContent = res.user.full_name;
    document.getElementById('header-user-initials').textContent = res.user.initials;
    showToast(res.message, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function submitOwnPassword(e) {
  e.preventDefault();
  try {
    const res = await apiRequest('/api/settings/password', {
      method: 'POST',
      body: {
        current_password: document.getElementById('set-cur-pwd').value,
        new_password: document.getElementById('set-new-pwd').value,
        confirm_password: document.getElementById('set-cfm-pwd').value,
      },
    });
    document.getElementById('settings-pwd-form').reset();
    showToast(res.message, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function saveInterfacePreferences() {
  const val = parseInt(document.getElementById('pref-page-size').value, 10) || 15;
  defaultPageSize = val;
  localStorage.setItem('cryotrack_page_size', String(val));
  Object.keys(tableState).forEach(k => {
    tableState[k].page = 1;
    if (tableState[k]._rerender) tableState[k]._rerender();
  });
  showToast(`Default table pagination updated to ${val} rows per page.`, 'success');
}

async function checkSystemHealth(notifyToast = false) {
  const dot = document.getElementById('settings-db-dot');
  const head = document.getElementById('settings-db-headline');
  const ver = document.getElementById('settings-db-version');
  try {
    const data = await apiRequest('/api/health');
    if (data.connected) {
      dot.className = 'pulse-dot';
      head.textContent = `Oracle Connected (${data.container || data.service})`;
      ver.textContent = data.server_version || 'Oracle XE';
      if (notifyToast) showToast('Oracle Database connection verified healthy.', 'success');
    } else {
      dot.className = 'pulse-dot error';
      head.textContent = 'Oracle Connection Unavailable';
      if (notifyToast) showToast('Oracle Database unreachable.', 'error');
    }
  } catch (err) {
    dot.className = 'pulse-dot error';
    head.textContent = 'Oracle Connection Unavailable';
    if (notifyToast) showToast(err.message, 'error');
  }
}

/* --------------------------------------------------------------------------
   14. Application Initialization & Global Event Listeners
   -------------------------------------------------------------------------- */
window.addEventListener('DOMContentLoaded', () => {
  // Reflect server-enforced RBAC in UI controls
  if (!CAN_WRITE) {
    document.querySelectorAll('.write-only-control').forEach(el => {
      el.style.display = 'none';
    });
  }

  // Sync saved pagination preference
  const prefSelect = document.getElementById('pref-page-size');
  if (prefSelect) {
    prefSelect.value = String(defaultPageSize);
  }

  // Mobile drawer toggle
  const mobileBtn = document.getElementById('mobile-toggle-btn');
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (mobileBtn && sidebar && backdrop) {
    mobileBtn.addEventListener('click', () => {
      const open = sidebar.classList.toggle('mobile-open');
      backdrop.classList.toggle('active', open);
    });
    backdrop.addEventListener('click', closeMobileSidebar);
  }

  // Top-right Account Dropdown toggle
  const accBtn = document.getElementById('account-menu-btn');
  const accDd = document.getElementById('account-dropdown');
  if (accBtn && accDd) {
    accBtn.addEventListener('click', e => {
      e.stopPropagation();
      const isOpen = accDd.classList.toggle('open');
      accBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
    document.addEventListener('click', e => {
      if (!document.getElementById('account-menu-wrap')?.contains(e.target)) {
        closeAccountMenu();
      }
    });
  }

  // Keyboard Escape closes modal & account dropdown
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      closeModal();
      closeAccountMenu();
      closeMobileSidebar();
    }
  });

  // Load initial tab dynamically based on role landing tab
  if (LANDING_TAB && LANDING_TAB !== 'tab-command-center') {
    switchTab(LANDING_TAB);
  } else {
    loadCommandCenter();
  }
});
