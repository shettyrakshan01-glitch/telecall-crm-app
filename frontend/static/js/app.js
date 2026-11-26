
// Global Safe Lucide Icon Renderer Guard
(function() {
  const originalCreateIcons = window.lucide && window.lucide.createIcons ? window.lucide.createIcons.bind(window.lucide) : null;
  window.safeCreateIcons = function() {
    if (originalCreateIcons && document.querySelector('i[data-lucide]')) {
      try {
        originalCreateIcons();
      } catch (e) {}
    }
  };
  if (window.lucide && originalCreateIcons) {
    window.lucide.createIcons = window.safeCreateIcons;
  }
})();

// Mobile Drawer & Responsive Helper
function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar-aside');
  const backdrop = document.getElementById('mobile-sidebar-backdrop');
  if (!sidebar) return;
  const isClosed = sidebar.classList.contains('-translate-x-full');
  if (isClosed) {
    sidebar.classList.remove('-translate-x-full');
    sidebar.classList.add('translate-x-0');
    if (backdrop) backdrop.classList.remove('hidden');
  } else {
    sidebar.classList.add('-translate-x-full');
    sidebar.classList.remove('translate-x-0');
    if (backdrop) backdrop.classList.add('hidden');
  }
}

function closeMobileSidebar() {
  const sidebar = document.getElementById('sidebar-aside');
  const backdrop = document.getElementById('mobile-sidebar-backdrop');
  if (sidebar && !sidebar.classList.contains('-translate-x-full')) {
    sidebar.classList.add('-translate-x-full');
    sidebar.classList.remove('translate-x-0');
  }
  if (backdrop && !backdrop.classList.contains('hidden')) {
    backdrop.classList.add('hidden');
  }
}

// Global Telecalling CRM JavaScript SDK & Helpers

const API_BASE = '/api/v1';

// Token Management (Synchronized across localStorage, sessionStorage, and Cookies for bulletproof persistence)
function getToken() {
  let token = localStorage.getItem('crm_access_token');
  if (!token) token = sessionStorage.getItem('crm_access_token');
  if (!token) {
    const match = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
    if (match) token = decodeURIComponent(match[1]);
  }
  if (token) {
    // Keep all 3 synced
    try { localStorage.setItem('crm_access_token', token); } catch(e){}
    try { sessionStorage.setItem('crm_access_token', token); } catch(e){}
  }
  return token;
}

function setToken(token) {
  if (!token) return;
  try { localStorage.setItem('crm_access_token', token); } catch(e){}
  try { sessionStorage.setItem('crm_access_token', token); } catch(e){}
  try {
    document.cookie = `access_token=${encodeURIComponent(token)}; path=/; max-age=604800; SameSite=Lax`;
  } catch(e){}
}

function removeToken() {
  try { localStorage.removeItem('crm_access_token'); } catch(e){}
  try { localStorage.removeItem('crm_user'); } catch(e){}
  try { sessionStorage.removeItem('crm_access_token'); } catch(e){}
  try { sessionStorage.removeItem('crm_user'); } catch(e){}
  try {
    document.cookie = 'access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax';
  } catch(e){}
}

function getUser() {
  let u = localStorage.getItem('crm_user');
  if (!u) u = sessionStorage.getItem('crm_user');
  let parsed = null;
  try {
    parsed = u ? JSON.parse(u) : null;
  } catch (e) {}

  // Auto-recovery: If user object was dropped but active token exists, decode JWT payload
  if (!parsed) {
    const token = getToken();
    if (token && token.includes('.')) {
      try {
        const parts = token.split('.');
        if (parts.length >= 2) {
          const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
          if (payload && payload.sub) {
            parsed = {
              id: payload.sub,
              role: payload.role || 'telecaller',
              email: payload.email || '',
              full_name: payload.full_name || payload.name || 'User',
              company_id: payload.company_id || null
            };
            setUser(parsed);
          }
        }
      } catch (err) {}
    }
  }

  if (parsed) {
    try { localStorage.setItem('crm_user', JSON.stringify(parsed)); } catch(e){}
    try { sessionStorage.setItem('crm_user', JSON.stringify(parsed)); } catch(e){}
  }
  return parsed;
}

function setUser(user) {
  if (!user) return;
  const str = JSON.stringify(user);
  try { localStorage.setItem('crm_user', str); } catch(e){}
  try { sessionStorage.setItem('crm_user', str); } catch(e){}
}

// Global API Fetch wrapper (supports both apiRequest(url, options) and apiRequest(url, 'POST', body))
async function apiRequest(endpoint, methodOrOptions = {}, bodyParam = null) {
  let options = {};
  if (typeof methodOrOptions === 'string') {
    options.method = methodOrOptions.toUpperCase();
    if (bodyParam !== null && bodyParam !== undefined) {
      if (bodyParam instanceof FormData) {
        options.body = bodyParam;
      } else if (typeof bodyParam === 'object') {
        options.body = JSON.stringify(bodyParam);
      } else {
        options.body = bodyParam;
      }
    }
  } else if (typeof methodOrOptions === 'object' && methodOrOptions !== null) {
    options = { ...methodOrOptions };
  }

  const token = getToken();
  const headers = options.headers || {};

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const selectedCompany = localStorage.getItem('crm_selected_company_id');
  if (selectedCompany && !headers['x-company-id']) {
    headers['x-company-id'] = selectedCompany;
  }

  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers
  });

  if (response.status === 401) {
    // Bulletproof protection: Never clear token or force logout on background polling or active call logs!
    if (endpoint.includes('/calls/') || endpoint.includes('/notifications/') || endpoint.includes('/presence/')) {
      console.warn(`[API Guard] 401 on background endpoint ${endpoint}; preserving active session.`);
      throw new Error(`Background request unauthorized (${endpoint})`);
    }
    removeToken();
    if (!window.location.pathname.includes('/login') && window.location.pathname !== '/') {
      window.location.href = '/login';
    }
    throw new Error('Session expired. Please log in again.');
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : data.detail.message || JSON.stringify(data.detail)) : 'Request failed';
    const err = new Error(errorMsg);
    err.data = data;
    err.status = response.status;
    throw err;
  }

  return data;
}

// Toast notification helper
function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed bottom-5 right-5 z-50 flex flex-col space-y-2 pointer-events-none';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const colors = {
    success: 'bg-emerald-600 text-white border-emerald-500',
    error: 'bg-rose-600 text-white border-rose-500',
    warning: 'bg-amber-600 text-white border-amber-500',
    info: 'bg-blue-600 text-white border-blue-500'
  };

  toast.className = `${colors[type] || colors.info} pointer-events-auto border px-4 py-3 rounded-xl shadow-2xl flex items-center space-x-3 text-sm font-medium transition-all transform translate-y-4 opacity-0`;
  toast.innerHTML = `
    <span>${message}</span>
    <button onclick="this.parentElement.remove()" class="ml-auto opacity-75 hover:opacity-100">&times;</button>
  `;

  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-4', 'opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-4');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Format duration seconds to MM:SS
function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// Format Date/Time
function formatDateTime(dtStr) {
  if (!dtStr) return '-';
  const dt = new Date(dtStr);
  return dt.toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit'
  });
}

// Check auth guard on page load
function requireAuth(allowedRoles = []) {
  const user = getUser();
  const token = getToken();

  if (!token || !user) {
    window.location.href = '/login';
    return false;
  }

  if (allowedRoles.length > 0 && !allowedRoles.includes(user.role) && user.role !== 'super_admin') {
    if (user.role === 'admin' || user.role === 'manager') {
      window.location.href = '/admin';
    } else if (user.role === 'telecaller') {
      window.location.href = '/workspace';
    } else if (user.role === 'super_admin') {
      window.location.href = '/superadmin';
    }
    return false;
  }

  return true;
}

// Notifications & Web Push Engine
let notificationInterval = null;

async function fetchUnreadNotificationsCount() {
  try {
    const res = await apiRequest('/notifications/unread-count');
    const badge = document.getElementById('nav-notif-badge');
    if (badge) {
      if (res.unread_count > 0) {
        badge.innerText = res.unread_count > 99 ? '99+' : res.unread_count;
        badge.classList.remove('hidden');
      } else {
        badge.classList.add('hidden');
      }
    }
  } catch (e) {
    // Silent fail if not authenticated
  }
}

async function loadNotificationsList() {
  const container = document.getElementById('notif-dropdown-list');
  if (!container) return;
  try {
    const list = await apiRequest('/notifications?limit=15');
    container.innerHTML = '';
    if (!list || list.length === 0) {
      container.innerHTML = `<div class="p-4 text-center text-slate-500 text-xs">No notifications yet.</div>`;
      return;
    }

    list.forEach(n => {
      let iconColor = 'text-blue-400';
      if (n.type === 'missed_call') iconColor = 'text-rose-400';
      if (n.type === 'admin_alert') iconColor = 'text-amber-400';
      if (n.type === 'lead_assigned') iconColor = 'text-emerald-400';

      container.innerHTML += `
        <div class="p-3 border-b border-slate-800/80 hover:bg-slate-800/40 transition text-xs ${!n.is_read ? 'bg-slate-800/20' : ''}" onclick="markNotifRead('${n.id}')">
          <div class="flex items-center justify-between mb-1">
            <span class="font-bold text-white flex items-center space-x-1.5">
              <span class="${iconColor}">&#9679;</span>
              <span>${n.title}</span>
            </span>
            <span class="text-[10px] text-slate-500">${formatDateTime(n.created_at)}</span>
          </div>
          <p class="text-slate-300 leading-relaxed text-[11px]">${n.message}</p>
        </div>
      `;
    });
  } catch (err) {
    console.error(err);
  }
}

function toggleNotifDropdown() {
  const dropdown = document.getElementById('notif-dropdown-menu');
  if (!dropdown) return;
  dropdown.classList.toggle('hidden');
  if (!dropdown.classList.contains('hidden')) {
    loadNotificationsList();
  }
}

async function markNotifRead(id) {
  try {
    await apiRequest(`/notifications/${id}/read`, { method: 'PUT' });
    await fetchUnreadNotificationsCount();
    await loadNotificationsList();
  } catch (e) {
    console.error(e);
  }
}

async function markAllNotifsRead() {
  try {
    await apiRequest('/notifications/read-all', { method: 'POST' });
    await fetchUnreadNotificationsCount();
    await loadNotificationsList();
    showToast('All notifications marked as read', 'info');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// Browser Web Push Opt-in
async function requestBrowserPushPermission() {
  if (!('Notification' in window)) {
    showToast('Desktop push notifications not supported by this browser.', 'warning');
    return;
  }
  const perm = await Notification.requestPermission();
  if (perm === 'granted') {
    showToast('Push notifications enabled! You will receive instant desktop alerts.', 'success');
    new Notification('Telecalling CRM', {
      body: 'Desktop alerts are active for calls and lead assignments.',
      icon: '/static/icons/phone.png'
    });
  } else {
    showToast('Notification permission was not granted.', 'warning');
  }
}

function startNotificationPolling() {
  fetchUnreadNotificationsCount();
  if (notificationInterval) clearInterval(notificationInterval);
  notificationInterval = setInterval(fetchUnreadNotificationsCount, 12000); // Poll every 12 seconds
}

async function handleLogout() {
  if (notificationInterval) clearInterval(notificationInterval);
  try {
    await apiRequest('/auth/logout', { method: 'POST' });
  } catch (e) {
    console.error('Logout error', e);
  } finally {
    removeToken();
    localStorage.removeItem('crm_superadmin_master_token');
    window.location.href = '/login';
  }
}

// ============================================================================
// SUPER ADMIN MASTER ACCESS & TRANSPARENCY HELPERS
// ============================================================================

function exitSuperAdminSession() {
  const masterToken = localStorage.getItem('crm_superadmin_master_token');
  if (masterToken) {
    setToken(masterToken);
    localStorage.removeItem('crm_superadmin_master_token');
    showToast('Exited Master Session. Returning to Super Admin Console...', 'info');
    setTimeout(() => {
      window.location.href = '/superadmin';
    }, 400);
  } else {
    window.location.href = '/superadmin';
  }
}

async function initSuperAdminTransparency() {
  const user = getUser();
  if (!user) return;

  // 1. If currently in an active Super Admin Master Session (Impersonation Mode)
  if (user.is_super_admin_session || localStorage.getItem('crm_superadmin_master_token')) {
    let banner = document.getElementById('superadmin-master-session-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'superadmin-master-session-banner';
      banner.className = 'bg-gradient-to-r from-purple-700 via-indigo-700 to-blue-700 text-white px-4 py-2.5 flex items-center justify-between text-xs font-semibold shadow-xl sticky top-0 z-50 border-b border-purple-400 shrink-0';
      banner.innerHTML = `
        <div class="flex items-center space-x-2.5">
          <span class="flex h-3 w-3 relative">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
          </span>
          <span class="font-bold tracking-wide uppercase">🛡️ Super Admin Master Access Mode</span>
          <span class="hidden md:inline text-purple-200">| You have master oversight over <b>${user.full_name}</b> (${user.email} &bull; ${user.role.toUpperCase()})</span>
        </div>
        <button onclick="exitSuperAdminSession()" class="px-3.5 py-1.5 bg-white hover:bg-purple-50 text-purple-900 rounded-xl text-xs font-extrabold transition shadow flex items-center space-x-1.5 cursor-pointer">
          <i data-lucide="arrow-left" class="w-3.5 h-3.5"></i>
          <span>Exit to Super Admin Console</span>
        </button>
      `;
      document.body.prepend(banner);
      if (window.lucide) lucide.createIcons();
    }
  }

  // 2. Fetch Super Admin Oversight Transparency Status
  try {
    const data = await apiRequest('/auth/superadmin-oversight-info');
    const pillContainer = document.getElementById('superadmin-oversight-pill-container');
    if (data && data.master_oversight_active) {
      const ownerName = data.platform_owner_name || 'Vipin (Super Admin)';
      // Find or render the transparency pill in the header
      if (pillContainer) {
        pillContainer.innerHTML = `
          <button 
            onclick="showSuperAdminOversightModal()" 
            class="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-purple-50 hover:bg-purple-100 border border-purple-200 text-purple-700 text-xs font-bold transition cursor-pointer shadow-sm shrink-0 whitespace-nowrap"
            title="Super Admin has master oversight over this account. Click for details."
          >
            <i data-lucide="shield-check" class="w-3.5 h-3.5 text-purple-600"></i>
            <span>Super Admin Active</span>
          </button>
        `;
        if (window.lucide) lucide.createIcons();
      }

      // If any lingering transparency bar exists, remove it
      const existingBar = document.getElementById('superadmin-transparency-bar');
      if (existingBar) existingBar.remove();

      window.__superadminOversightData = data;
    } else {
      if (pillContainer) pillContainer.innerHTML = '';
      const existingBar = document.getElementById('superadmin-transparency-bar');
      if (existingBar) existingBar.remove();
      const existingBanner = document.getElementById('superadmin-master-session-banner');
      if (existingBanner) existingBanner.remove();
    }
  } catch (err) {
    console.warn('Oversight info error:', err);
  }
}

function showSuperAdminOversightModal() {
  const data = window.__superadminOversightData || {
    platform_owner_name: 'Vipin (Super Admin)',
    superadmin_email: 'superadmin@telecall.io',
    superadmin_role: 'Platform Super Admin & SaaS Owner',
    access_scope: 'Full Master Administrative & Telecalling Oversight across all Tenants',
    transparency_notice: 'Super Admin holds master oversight privileges across all tenant accounts for platform quality, compliance, and support monitoring.',
    recent_oversight_events: []
  };

  let modal = document.getElementById('modal-superadmin-oversight');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'modal-superadmin-oversight';
    modal.className = 'fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4';
    document.body.appendChild(modal);
  }

  const eventsHtml = (data.recent_oversight_events && data.recent_oversight_events.length > 0)
    ? data.recent_oversight_events.map(ev => `
        <div class="p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-0.5">
          <div class="flex items-center justify-between font-bold text-slate-800">
            <span>${ev.action_type === 'impersonate_agent' ? '👤 Agent Workspace Review' : '🏢 Company Admin Oversight'}</span>
            <span class="text-[10px] text-slate-400 font-normal">${ev.created_at ? new Date(ev.created_at).toLocaleString() : ''}</span>
          </div>
          <div class="text-slate-600">${ev.description}</div>
        </div>
      `).join('')
    : `<div class="text-slate-400 text-xs py-2 text-center">No recent master access actions recorded for this tenant.</div>`;

  modal.innerHTML = `
    <div class="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-200">
        <div class="flex items-center space-x-2.5">
          <div class="w-9 h-9 rounded-xl bg-purple-600 text-white flex items-center justify-center shadow-md shadow-purple-500/20">
            <i data-lucide="shield" class="w-5 h-5"></i>
          </div>
          <div>
            <h3 class="text-base font-bold text-slate-900">Platform Super Admin Oversight</h3>
            <p class="text-xs text-purple-600 font-semibold">Master Governance & System Transparency</p>
          </div>
        </div>
        <button onclick="document.getElementById('modal-superadmin-oversight').remove()" class="text-slate-400 hover:text-slate-600 text-lg font-bold">&times;</button>
      </div>

      <div class="space-y-3 text-xs">
        <div class="p-3.5 bg-purple-50/70 border border-purple-200 rounded-xl text-purple-900 space-y-1">
          <div class="font-bold flex items-center space-x-1.5">
            <i data-lucide="info" class="w-4 h-4 text-purple-600"></i>
            <span>Platform Owner Master Access Notice</span>
          </div>
          <p class="text-purple-800 leading-relaxed">${data.transparency_notice}</p>
        </div>

        <div class="grid grid-cols-2 gap-2.5">
          <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
            <span class="text-slate-400 font-medium block">Super Admin Identity</span>
            <span class="font-bold text-slate-900 block mt-0.5">${data.platform_owner_name}</span>
            <span class="text-[11px] text-purple-600 font-mono">${data.superadmin_email}</span>
          </div>
          <div class="p-3 bg-slate-50 rounded-xl border border-slate-200">
            <span class="text-slate-400 font-medium block">Access Authority</span>
            <span class="font-bold text-emerald-600 block mt-0.5">&#10003; Full Master Oversight</span>
            <span class="text-[11px] text-slate-500">Admins & Agents Monitored</span>
          </div>
        </div>

        <div>
          <span class="font-bold text-slate-800 block mb-1.5">Recent Super Admin Master Events:</span>
          <div class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            ${eventsHtml}
          </div>
        </div>
      </div>

      <div class="pt-3 border-t border-slate-200 flex justify-end">
        <button onclick="document.getElementById('modal-superadmin-oversight').remove()" class="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl font-semibold text-xs shadow">
          Understood & Acknowledged
        </button>
      </div>
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('hidden');
    if (window.lucide) lucide.createIcons();
  }
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('hidden');
  }
}

function isMobileDevice() {
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent || '')
    || (navigator.maxTouchPoints > 1 && window.innerWidth <= 1024);
}

function triggerPhoneDialer(phone) {
  const clean = String(phone || '').replace(/[^\d+*#]/g, '');
  if (!clean) return false;
  if (isMobileDevice()) {
    try {
      window.location.href = 'tel:' + clean;
    } catch (e) {
      try {
        const a = document.createElement('a');
        a.href = 'tel:' + clean;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { try { a.remove(); } catch (err) {} }, 300);
      } catch (err2) {}
    }
    return true;
  }
  console.log('[Desktop Call] In-CRM call active for:', clean);
  return false;
}

// Web Audio Ringtone & Disconnect Tone Generator (AudioContext)
let crmAudioCtx = null;
let crmRingInterval = null;

function playCrmRingtone() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    if (!crmAudioCtx || crmAudioCtx.state === 'closed') {
      crmAudioCtx = new AudioContextClass();
    }
    if (crmAudioCtx.state === 'suspended') {
      crmAudioCtx.resume();
    }

    function ringBurst() {
      if (!crmAudioCtx || crmAudioCtx.state === 'closed') return;
      const now = crmAudioCtx.currentTime;
      const osc1 = crmAudioCtx.createOscillator();
      const osc2 = crmAudioCtx.createOscillator();
      const gain = crmAudioCtx.createGain();

      osc1.type = 'sine';
      osc2.type = 'sine';
      osc1.frequency.setValueAtTime(440, now);
      osc2.frequency.setValueAtTime(480, now);

      gain.gain.setValueAtTime(0.06, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 1.8);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(crmAudioCtx.destination);

      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 1.8);
      osc2.stop(now + 1.8);
    }

    ringBurst();
    crmRingInterval = setInterval(ringBurst, 3200);
  } catch (e) {
    console.log('[Audio] Web Audio ringtone unavailable:', e);
  }
}

function stopCrmRingtone() {
  if (crmRingInterval) {
    clearInterval(crmRingInterval);
    crmRingInterval = null;
  }
  if (crmAudioCtx && crmAudioCtx.state !== 'closed') {
    try { crmAudioCtx.close(); } catch (e) {}
    crmAudioCtx = null;
  }
}

function playCrmDisconnectTone() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(480, now);
    gain.gain.setValueAtTime(0.1, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.35);
    setTimeout(() => { try { ctx.close(); } catch(e){} }, 500);
  } catch (e) {}
}

// ================= UNIFIED CALL + DISPOSITION + VOICE RECORDING MODAL (AGENT & ADMIN) =================
function isAdminUser() {
  const u = getUser();
  return !!(u && u.role === 'admin');
}

window.__unifiedCallState = {
  callLogId: null,
  initiatePromise: null,
  timerInterval: null,
  seconds: 0,
  ended: false,
  selectedDispoId: null,
  selectedDispoCode: '',
  selectedDispoLabel: '',
  dispoEditMode: false,
  mediaRecorder: null,
  audioChunks: [],
  recordingBlob: null,
  recordingFile: null,
  recInterval: null,
  recSeconds: 0,
  onSaved: null
};

async function preloadUnifiedDispositions(force = false) {
  if (!force && Array.isArray(window.__cachedDispositions) && window.__cachedDispositions.length > 0) {
    return window.__cachedDispositions;
  }
  try {
    const dispos = await apiRequest('/calls/dispositions');
    if (Array.isArray(dispos)) {
      window.__cachedDispositions = dispos;
      return dispos;
    }
  } catch (e) {
    console.error('Failed loading dispositions:', e);
  }
  return [];
}

function formatCallTimer(sec) {
  const s = Math.max(0, sec || 0);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m < 10 ? '0' : ''}${m}:${r < 10 ? '0' : ''}${r}`;
}

function renderUnifiedDispositionGrid(dispositions) {
  const grid = document.getElementById('ucm-dispo-grid');
  if (!grid) return;

  if (!Array.isArray(dispositions) || dispositions.length === 0) {
    grid.innerHTML = '<div class="col-span-2 text-center py-3 text-xs text-slate-400">No outcomes found.</div>';
    return;
  }

  const st = window.__unifiedCallState;
  const stillExists = dispositions.some(d => d.id === st.selectedDispoId);
  if ((!st.selectedDispoId || !stillExists) && dispositions.length > 0) {
    st.selectedDispoId = dispositions[0].id;
    st.selectedDispoCode = dispositions[0].code || '';
    st.selectedDispoLabel = dispositions[0].label || dispositions[0].name || dispositions[0].code;
  }

  const showEditControls = isAdminUser() && st.dispoEditMode;

  grid.innerHTML = dispositions.map(d => {
    const label = d.label || d.name || d.code;
    const code = d.code || '';
    const safeLabel = String(label).replace(/'/g, "\\'").replace(/"/g, '&quot;');
    const safeCode = String(code).replace(/'/g, "\\'").replace(/"/g, '&quot;');
    const isSelected = st.selectedDispoId === d.id;

    if (showEditControls) {
      return `
        <div class="col-span-2 flex items-center justify-between px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 gap-2">
          <span class="text-xs font-semibold text-slate-800 truncate flex-1">${label}</span>
          <button type="button" onclick="adminEditDispositionInline('${d.id}', '${safeLabel}')" class="px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-bold transition cursor-pointer">
            Edit
          </button>
          <button type="button" onclick="adminDeleteDispositionFromModal('${d.id}', '${safeLabel}')" class="px-2 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-600 text-[11px] font-bold transition cursor-pointer">
            Remove
          </button>
        </div>
      `;
    }

    const cls = isSelected
      ? 'bg-indigo-700 text-white border-indigo-700 font-bold shadow-sm'
      : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200 font-medium';
    return `
      <button
        type="button"
        onclick="selectUnifiedDisposition('${d.id}', '${safeLabel}', '${safeCode}')"
        data-dispo-id="${d.id}"
        class="ucm-dispo-btn text-left px-3.5 py-2.5 rounded-xl border text-xs transition cursor-pointer ${cls}"
      >
        ${label}
      </button>
    `;
  }).join('');

  toggleUnifiedOtherBox();
}

function toggleUnifiedDispoEditMode() {
  if (!isAdminUser()) return;
  const st = window.__unifiedCallState;
  st.dispoEditMode = !st.dispoEditMode;
  const addBar = document.getElementById('ucm-admin-add-dispo-bar');
  const toggleBtn = document.getElementById('ucm-btn-toggle-edit-dispo');
  if (addBar) addBar.classList.toggle('hidden', !st.dispoEditMode);
  if (toggleBtn) {
    toggleBtn.innerText = st.dispoEditMode ? 'Done Editing' : '+ Add / Edit';
  }
  renderUnifiedDispositionGrid(window.__cachedDispositions || []);
}

async function adminAddDispositionFromModal() {
  if (!isAdminUser()) return;
  const input = document.getElementById('ucm-admin-new-dispo-input');
  const label = (input?.value || '').trim();
  if (!label) {
    showToast('Please enter a disposition option name.', 'error');
    return;
  }
  try {
    await apiRequest('/calls/dispositions', 'POST', { label });
    if (input) input.value = '';
    const updated = await preloadUnifiedDispositions(true);
    renderUnifiedDispositionGrid(updated);
    if (typeof loadAdminDispositionManager === 'function') loadAdminDispositionManager();
    showToast(`Added "${label}"`, 'success');
  } catch (err) {
    showToast(err.message || 'Could not add disposition.', 'error');
  }
}

async function adminEditDispositionInline(dispoId, currentLabel) {
  if (!isAdminUser()) return;
  const newLabel = prompt('Edit Disposition Option Name:', currentLabel);
  if (newLabel === null) return;
  const trimmed = newLabel.trim();
  if (!trimmed || trimmed === currentLabel) return;
  try {
    await apiRequest(`/calls/dispositions/${dispoId}`, 'PUT', { label: trimmed });
    const updated = await preloadUnifiedDispositions(true);
    renderUnifiedDispositionGrid(updated);
    if (typeof loadAdminDispositionManager === 'function') loadAdminDispositionManager();
    showToast(`Updated to "${trimmed}"`, 'success');
  } catch (err) {
    showToast(err.message || 'Could not update disposition.', 'error');
  }
}

async function adminDeleteDispositionFromModal(dispoId, label) {
  if (!isAdminUser()) return;
  if (!confirm(`Remove "${label}" from Call Outcome options?`)) return;
  try {
    await apiRequest(`/calls/dispositions/${dispoId}`, 'DELETE');
    const updated = await preloadUnifiedDispositions(true);
    renderUnifiedDispositionGrid(updated);
    if (typeof loadAdminDispositionManager === 'function') loadAdminDispositionManager();
    showToast(`Removed "${label}"`, 'success');
  } catch (err) {
    showToast(err.message || 'Could not remove disposition.', 'error');
  }
}

function toggleUnifiedOtherBox() {
  const st = window.__unifiedCallState;
  const wrap = document.getElementById('ucm-other-input-wrap');
  const input = document.getElementById('ucm-other-text');
  if (!wrap) return;
  const isOther = (st.selectedDispoCode || '').toUpperCase() === 'OTHER' || (st.selectedDispoLabel || '').trim().toLowerCase() === 'other';
  if (isOther) {
    wrap.classList.remove('hidden');
    if (input) setTimeout(() => input.focus(), 50);
  } else {
    wrap.classList.add('hidden');
  }
}

function selectUnifiedDisposition(dispoId, dispoLabel, dispoCode = '') {
  window.__unifiedCallState.selectedDispoId = dispoId;
  window.__unifiedCallState.selectedDispoCode = dispoCode;
  window.__unifiedCallState.selectedDispoLabel = dispoLabel;
  document.querySelectorAll('.ucm-dispo-btn').forEach(btn => {
    const active = btn.getAttribute('data-dispo-id') === dispoId;
    btn.className = active
      ? 'ucm-dispo-btn text-left px-3.5 py-2.5 rounded-xl border text-xs transition cursor-pointer bg-indigo-700 text-white border-indigo-700 font-bold shadow-sm'
      : 'ucm-dispo-btn text-left px-3.5 py-2.5 rounded-xl border text-xs transition cursor-pointer bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200 font-medium';
  });
  toggleUnifiedOtherBox();
}

function stopUnifiedCallTimersAndMic() {
  stopCrmRingtone();
  if (window.__crmConnectTimeout) {
    clearTimeout(window.__crmConnectTimeout);
    window.__crmConnectTimeout = null;
  }
  if (typeof window.__crmSimReturnCleanup === 'function') {
    try { window.__crmSimReturnCleanup(); } catch (e) {}
    window.__crmSimReturnCleanup = null;
  }
  const st = window.__unifiedCallState;
  if (st.timerInterval) {
    clearInterval(st.timerInterval);
    st.timerInterval = null;
  }
  if (st.recInterval) {
    clearInterval(st.recInterval);
    st.recInterval = null;
  }
  if (st.mediaRecorder && st.mediaRecorder.state !== 'inactive') {
    try {
      st.mediaRecorder.stop();
      st.mediaRecorder.stream?.getTracks().forEach(t => t.stop());
    } catch (e) {}
  }
}

function openUnifiedCallModal({ leadId = null, leadName = 'Customer', phone = '', dialMethod = 'crm', onSaved = null } = {}) {
  stopUnifiedCallTimersAndMic();

  const cleanPhone = String(phone || '').replace(/[^\d+*#]/g, '');
  const useSimDialer = isMobileDevice() && dialMethod !== 'cloud';
  const safeName = String(leadName || 'Customer')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  // Hide legacy small overlays if present
  const oldActive = document.getElementById('active-call-modal');
  if (oldActive) oldActive.classList.add('hidden');
  const oldMand = document.getElementById('mandatory-disposition-modal');
  if (oldMand) oldMand.classList.add('hidden');

  const existing = document.getElementById('unified-call-modal');
  if (existing) existing.remove();

  // Reset state
  const st = window.__unifiedCallState;
  st.callLogId = null;
  st.initiatePromise = null;
  st.seconds = 0;
  st.ended = false;
  st.useSimDialer = useSimDialer;
  st.simBackgroundedAt = null;
  st.callConnectedAt = null;
  st.selectedDispoId = null;
  st.selectedDispoCode = '';
  st.selectedDispoLabel = '';
  st.dispoEditMode = false;
  st.mediaRecorder = null;
  st.audioChunks = [];
  st.recordingBlob = null;
  st.recordingFile = null;
  st.recSeconds = 0;
  st.onSaved = onSaved;

  const isGenericLeadName = !leadName || /^(manual call|customer|unknown|contact(\s+\d+)?)$/i.test(String(leadName).trim());
  const prefillCustomerName = isGenericLeadName ? '' : safeName;

  const modal = document.createElement('div');
  modal.id = 'unified-call-modal';
  modal.className = 'fixed inset-0 z-[70] bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4';

  modal.innerHTML = `
    <div class="bg-white rounded-3xl shadow-2xl border border-slate-200 w-full max-w-md overflow-hidden max-h-[94vh] flex flex-col">
      <!-- Dark Navy Call Header -->
      <div class="bg-slate-950 text-white p-4 sm:p-5 space-y-3 shrink-0">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span id="ucm-status-dot" class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping"></span>
            <span id="ucm-status-text" class="text-[11px] font-extrabold uppercase tracking-wider text-amber-300">${useSimDialer ? 'Dialing via Phone SIM...' : 'Calling &amp; Ringing In-CRM...'}</span>
          </div>
          <div class="flex items-center space-x-2">
            <span id="ucm-timer" class="font-mono font-bold text-xs sm:text-sm bg-slate-800 px-2.5 py-0.5 rounded-lg text-white">00:00</span>
            <button type="button" onclick="closeUnifiedCallModal()" class="p-1 rounded-full text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer" title="Close">
              <i data-lucide="x" class="w-4 h-4"></i>
            </button>
          </div>
        </div>

        <div>
          <h3 id="ucm-header-name" class="font-extrabold text-base sm:text-lg text-white leading-tight">${safeName}</h3>
          <div class="flex items-center flex-wrap gap-2 mt-1">
            <span class="text-xs text-blue-300 font-mono font-bold">${cleanPhone || phone}</span>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold ${useSimDialer ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30' : 'bg-blue-500/20 text-blue-300 border border-blue-400/30'}">${useSimDialer ? '● Phone SIM + CRM' : '● In-CRM Web Call'}</span>
            ${useSimDialer && cleanPhone ? `<a href="tel:${cleanPhone}" onclick="if(window.__unifiedCallState){window.__unifiedCallState.simBackgroundedAt=Date.now();}" class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-white/10 hover:bg-white/20 text-white border border-white/20">Redial SIM</a>` : ''}
          </div>
        </div>

        <div class="flex items-center space-x-2">
          ${useSimDialer && cleanPhone ? `
            <a
              id="ucm-btn-call-sim"
              href="tel:${cleanPhone}"
              onclick="if(window.__unifiedCallState){window.__unifiedCallState.simBackgroundedAt=Date.now();}"
              class="flex-1 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 active:scale-95 text-slate-950 font-extrabold text-xs flex items-center justify-center space-x-1.5 shadow-lg shadow-emerald-500/30 transition cursor-pointer"
            >
              <i data-lucide="phone-call" class="w-4 h-4"></i>
              <span>Call via SIM</span>
            </a>
          ` : ''}
          <button
            type="button"
            id="ucm-btn-end-call"
            onclick="endUnifiedCall()"
            class="${useSimDialer ? 'flex-1' : 'w-full'} py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 active:scale-95 text-white font-bold text-xs flex items-center justify-center space-x-2 shadow-lg shadow-rose-600/30 transition cursor-pointer"
          >
            <i data-lucide="phone-off" class="w-4 h-4"></i>
            <span>End Call</span>
          </button>
        </div>
      </div>

      <!-- Scrollable Body: Customer Name + Disposition Grid + Callback + Voice Recording -->
      <div class="p-4 sm:p-5 space-y-4 overflow-y-auto flex-1">
        <!-- Customer / Lead Name Input -->
        <div>
          <label class="block text-xs font-bold text-slate-800 mb-1">Customer Name <span class="text-slate-400 font-normal">(Add / Edit)</span></label>
          <input
            type="text"
            id="ucm-customer-name"
            value="${prefillCustomerName}"
            oninput="const h=document.getElementById('ucm-header-name'); if(h){h.innerText=this.value.trim()||'${safeName}';}"
            placeholder="Enter customer name (e.g. Rahul Sharma)"
            class="w-full px-3 py-2 text-xs font-semibold rounded-xl border border-slate-200 bg-slate-50 text-slate-900 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:bg-white transition"
          >
        </div>
        <!-- Call Outcome / Disposition Grid -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <label class="block text-xs font-bold text-slate-800">Call Outcome / Disposition <span class="text-rose-500">*</span></label>
            ${isAdminUser() ? `
              <button
                type="button"
                id="ucm-btn-toggle-edit-dispo"
                onclick="toggleUnifiedDispoEditMode()"
                class="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 hover:underline cursor-pointer"
              >
                + Add / Edit
              </button>
            ` : ''}
          </div>

          ${isAdminUser() ? `
            <div id="ucm-admin-add-dispo-bar" class="hidden mb-2.5 flex items-center space-x-2">
              <input
                type="text"
                id="ucm-admin-new-dispo-input"
                placeholder="New option name (e.g. Interested)"
                class="flex-1 px-3 py-1.5 text-xs rounded-xl border border-indigo-300 bg-indigo-50/40 text-slate-900 focus:outline-none focus:border-indigo-600 focus:bg-white"
              >
              <button
                type="button"
                onclick="adminAddDispositionFromModal()"
                class="px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold cursor-pointer"
              >
                Add
              </button>
            </div>
          ` : ''}

          <div id="ucm-dispo-grid" class="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-0.5">
            <div class="col-span-2 text-center py-3 text-xs text-slate-400">Loading outcomes...</div>
          </div>

          <!-- Custom Text Box (Appears automatically when "Other" is selected) -->
          <div id="ucm-other-input-wrap" class="hidden mt-3">
            <label class="block text-[11px] font-bold text-indigo-700 mb-1">Write Custom Outcome / Remark</label>
            <textarea
              id="ucm-other-text"
              rows="2"
              placeholder="Write here what happened on the call..."
              class="w-full px-3 py-2 text-xs rounded-xl border-2 border-indigo-300 bg-indigo-50/40 text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-600 focus:bg-white transition"
            ></textarea>
          </div>
        </div>

        <!-- Optional Follow-up Callback -->
        <div>
          <label class="block text-xs font-bold text-slate-800 mb-1.5">Schedule Follow-up Callback <span class="text-slate-400 font-normal">(Optional)</span></label>
          <input type="datetime-local" id="ucm-followup-dt" class="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 bg-slate-50 text-slate-800 focus:outline-none focus:border-blue-500">
        </div>

        <!-- Call Voice Recording Box -->
        <div class="p-3.5 rounded-2xl border border-slate-200 bg-slate-50/80 space-y-2.5">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2 text-slate-800">
              <i data-lucide="mic" class="w-4 h-4 text-indigo-600"></i>
              <span class="text-xs font-bold">Call Audio Recording</span>
            </div>
            <span id="ucm-rec-badge" class="hidden text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">REC 00:00</span>
          </div>

          <div class="flex items-center space-x-2">
            <button
              type="button"
              id="ucm-btn-record"
              onclick="toggleUnifiedVoiceRecording()"
              class="px-3 py-1.5 rounded-xl bg-rose-700 hover:bg-rose-800 text-white text-xs font-bold flex items-center space-x-1.5 transition cursor-pointer shadow-sm"
            >
              <i data-lucide="mic" class="w-3.5 h-3.5"></i>
              <span>Record Voice</span>
            </button>

            <label
              for="ucm-audio-upload-input"
              class="px-3 py-1.5 rounded-xl bg-white hover:bg-slate-100 border border-slate-300 text-slate-800 text-xs font-bold flex items-center space-x-1.5 transition cursor-pointer"
            >
              <i data-lucide="upload" class="w-3.5 h-3.5"></i>
              <span>Attach File</span>
            </label>
            <input type="file" id="ucm-audio-upload-input" accept=".mp3,.m4a,.wav,.ogg,.webm,audio/*" onchange="handleUnifiedAudioFile(event)" class="hidden">
          </div>

          <div id="ucm-audio-preview-wrap" class="hidden pt-1 space-y-1">
            <div id="ucm-audio-filename" class="text-[11px] font-semibold text-emerald-700 truncate"></div>
            <audio id="ucm-audio-preview" controls class="w-full h-8"></audio>
          </div>

          <p class="text-[10px] text-slate-500 leading-relaxed">
            Record via microphone or attach <span class="font-mono text-slate-700">.mp3 / .m4a / .wav</span> phone recordings.
          </p>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-4 py-3 border-t border-slate-100 bg-white flex items-center space-x-3 shrink-0">
        <button
          type="button"
          onclick="closeUnifiedCallModal()"
          class="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-bold text-xs transition cursor-pointer"
        >
          Later
        </button>
        <button
          type="button"
          id="ucm-btn-save"
          onclick="saveUnifiedCallDisposition()"
          class="flex-1 btn-primary-glow py-2.5 font-bold text-xs cursor-pointer"
        >
          Save Disposition
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  if (window.lucide) lucide.createIcons();

  // Option 1: Trigger real Android SIM dialer on mobile, or Web Audio ringtone on desktop
  if (useSimDialer) {
    st.simBackgroundedAt = Date.now();
    triggerPhoneDialer(cleanPhone);

    // Auto-stop call timer when agent cuts Phone SIM call and returns to CRM
    const onLeaveToDialer = () => {
      if (document.hidden && !st.ended) {
        st.simBackgroundedAt = st.simBackgroundedAt || Date.now();
      }
    };
    const onReturnFromDialer = () => {
      if (document.hidden || st.ended || !st.simBackgroundedAt) return;
      const awayMs = Date.now() - st.simBackgroundedAt;
      if (awayMs >= 1500) {
        if (st.callConnectedAt) {
          st.seconds = Math.max(st.seconds, Math.floor((Date.now() - st.callConnectedAt) / 1000));
        } else {
          st.seconds = Math.max(st.seconds, Math.floor(awayMs / 1000));
        }
        const tEl = document.getElementById('ucm-timer');
        if (tEl) tEl.innerText = formatCallTimer(st.seconds);
        endUnifiedCall();
      }
    };
    document.addEventListener('visibilitychange', onLeaveToDialer);
    document.addEventListener('visibilitychange', onReturnFromDialer);
    window.addEventListener('blur', onLeaveToDialer);
    window.addEventListener('focus', onReturnFromDialer);
    window.__crmSimReturnCleanup = () => {
      document.removeEventListener('visibilitychange', onLeaveToDialer);
      document.removeEventListener('visibilitychange', onReturnFromDialer);
      window.removeEventListener('blur', onLeaveToDialer);
      window.removeEventListener('focus', onReturnFromDialer);
    };
  } else {
    playCrmRingtone();
  }

  // Transition from "Ringing" to "Connected" after 3.2s
  window.__crmConnectTimeout = setTimeout(() => {
    stopCrmRingtone();
    if (st.ended) return;
    st.callConnectedAt = Date.now();
    const dot = document.getElementById('ucm-status-dot');
    const txt = document.getElementById('ucm-status-text');
    if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
    if (txt) {
      txt.innerText = useSimDialer ? '● SIM Call In Progress (Log After Call)' : '● Connected (Live In-CRM Call)';
      txt.className = 'text-[11px] font-extrabold uppercase tracking-wider text-emerald-400';
    }

    // Start live call duration timer using real wall-clock elapsed time
    st.timerInterval = setInterval(() => {
      if (st.ended) return;
      st.seconds = Math.max(st.seconds + 1, Math.floor((Date.now() - st.callConnectedAt) / 1000));
      const tEl = document.getElementById('ucm-timer');
      if (tEl) tEl.innerText = formatCallTimer(st.seconds);
    }, 1000);
  }, 3200);

  // Load & render dispositions immediately, then refresh fresh from server
  if (Array.isArray(window.__cachedDispositions) && window.__cachedDispositions.length > 0) {
    renderUnifiedDispositionGrid(window.__cachedDispositions);
  }
  preloadUnifiedDispositions(true).then(dispos => renderUnifiedDispositionGrid(dispos));

  // Initiate backend call log asynchronously
  st.initiatePromise = (async () => {
    try {
      const res = await apiRequest('/calls/initiate', 'POST', {
        lead_id: leadId || null,
        phone: phone || cleanPhone,
        dial_method: useSimDialer ? 'sim' : 'crm'
      });
      st.callLogId = res.call_log_id || null;
      return st.callLogId;
    } catch (err) {
      console.error('Unified call log initiation error:', err);
      return null;
    }
  })();
}

async function endUnifiedCall() {
  stopCrmRingtone();
  if (window.__crmConnectTimeout) {
    clearTimeout(window.__crmConnectTimeout);
    window.__crmConnectTimeout = null;
  }
  playCrmDisconnectTone();

  const st = window.__unifiedCallState;
  if (st.ended) return;
  st.ended = true;
  if (st.timerInterval) {
    clearInterval(st.timerInterval);
    st.timerInterval = null;
  }
  if (typeof window.__crmSimReturnCleanup === 'function') {
    try { window.__crmSimReturnCleanup(); } catch (e) {}
    window.__crmSimReturnCleanup = null;
  }

  const dot = document.getElementById('ucm-status-dot');
  const txt = document.getElementById('ucm-status-text');
  const btn = document.getElementById('ucm-btn-end-call');
  const simBtn = document.getElementById('ucm-btn-call-sim');
  if (simBtn) simBtn.classList.add('hidden');
  if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-amber-400';
  if (txt) {
    txt.innerText = `Call Ended (${formatCallTimer(st.seconds)}) — Select Outcome`;
    txt.className = 'text-[11px] font-extrabold uppercase tracking-wider text-amber-400';
  }
  if (btn) {
    btn.disabled = true;
    btn.className = 'w-full py-2.5 rounded-xl bg-slate-800 text-slate-400 font-bold text-xs flex items-center justify-center space-x-2 cursor-not-allowed';
    btn.innerHTML = '<span>Call Ended &bull; Select Outcome Below</span>';
  }

  try {
    const logId = st.callLogId || (st.initiatePromise ? await st.initiatePromise : null);
    if (logId) {
      await apiRequest('/calls/end', 'POST', {
        call_log_id: logId,
        call_id: logId,
        duration_seconds: st.seconds,
        talk_time_seconds: st.seconds
      });
    }
  } catch (e) {}
}

async function toggleUnifiedVoiceRecording() {
  const st = window.__unifiedCallState;
  const btn = document.getElementById('ucm-btn-record');
  const badge = document.getElementById('ucm-rec-badge');

  // If already recording -> stop
  if (st.mediaRecorder && st.mediaRecorder.state === 'recording') {
    st.mediaRecorder.stop();
    st.mediaRecorder.stream?.getTracks().forEach(t => t.stop());
    if (st.recInterval) {
      clearInterval(st.recInterval);
      st.recInterval = null;
    }
    if (btn) {
      btn.className = 'px-3.5 py-2 rounded-xl bg-rose-700 hover:bg-rose-800 text-white text-xs font-bold flex items-center space-x-1.5 transition cursor-pointer shadow-sm';
      btn.innerHTML = '<i data-lucide="mic" class="w-3.5 h-3.5"></i><span>Record Voice</span>';
      if (window.lucide) lucide.createIcons();
    }
    if (badge) {
      badge.innerText = 'Recorded';
      badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700';
    }
    return;
  }

  // Start recording
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showToast('Microphone recording requires HTTPS or localhost.', 'error');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    st.audioChunks = [];
    st.recordingBlob = null;
    st.recordingFile = null;
    st.recSeconds = 0;

    const recorder = new MediaRecorder(stream);
    st.mediaRecorder = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) st.audioChunks.push(e.data);
    };

    recorder.onstop = () => {
      const blob = new Blob(st.audioChunks, { type: recorder.mimeType || 'audio/webm' });
      st.recordingBlob = blob;
      const url = URL.createObjectURL(blob);
      const wrap = document.getElementById('ucm-audio-preview-wrap');
      const audioEl = document.getElementById('ucm-audio-preview');
      const nameEl = document.getElementById('ucm-audio-filename');
      if (audioEl) audioEl.src = url;
      if (nameEl) nameEl.innerText = `Voice Recording (${formatCallTimer(st.recSeconds)}) ready to save`;
      if (wrap) wrap.classList.remove('hidden');
    };

    recorder.start();

    if (btn) {
      btn.className = 'px-3.5 py-2 rounded-xl bg-rose-600 text-white text-xs font-bold flex items-center space-x-1.5 transition cursor-pointer animate-pulse shadow';
      btn.innerHTML = '<i data-lucide="square" class="w-3.5 h-3.5"></i><span>Stop Recording</span>';
      if (window.lucide) lucide.createIcons();
    }
    if (badge) {
      badge.classList.remove('hidden');
      badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 animate-pulse';
      badge.innerText = 'REC 00:00';
    }

    st.recInterval = setInterval(() => {
      st.recSeconds++;
      if (badge) badge.innerText = `REC ${formatCallTimer(st.recSeconds)}`;
    }, 1000);
  } catch (err) {
    showToast('Microphone access denied or unavailable.', 'error');
  }
}

function handleUnifiedAudioFile(e) {
  const file = e.target?.files?.[0];
  if (!file) return;
  const st = window.__unifiedCallState;
  st.recordingFile = file;
  st.recordingBlob = null;

  const url = URL.createObjectURL(file);
  const wrap = document.getElementById('ucm-audio-preview-wrap');
  const audioEl = document.getElementById('ucm-audio-preview');
  const nameEl = document.getElementById('ucm-audio-filename');
  const badge = document.getElementById('ucm-rec-badge');
  if (audioEl) audioEl.src = url;
  if (nameEl) nameEl.innerText = `Attached: ${file.name}`;
  if (wrap) wrap.classList.remove('hidden');
  if (badge) {
    badge.classList.remove('hidden');
    badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700';
    badge.innerText = 'Audio Attached';
  }
}

async function saveUnifiedCallDisposition() {
  const st = window.__unifiedCallState;
  if (!st.selectedDispoId) {
    showToast('Please select a call outcome.', 'error');
    return;
  }

  const saveBtn = document.getElementById('ucm-btn-save');
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerText = 'Saving...';
  }

  // Stop live recording gracefully if still recording
  if (st.mediaRecorder && st.mediaRecorder.state === 'recording') {
    await new Promise(resolve => {
      const prevOnStop = st.mediaRecorder.onstop;
      st.mediaRecorder.onstop = () => {
        if (prevOnStop) prevOnStop();
        resolve();
      };
      st.mediaRecorder.stop();
      st.mediaRecorder.stream?.getTracks().forEach(t => t.stop());
    });
  }

  if (st.timerInterval) {
    clearInterval(st.timerInterval);
    st.timerInterval = null;
  }

  try {
    const logId = st.callLogId || (st.initiatePromise ? await st.initiatePromise : null);
    if (!logId) {
      closeUnifiedCallModal();
      return;
    }

    if (!st.ended) {
      await apiRequest('/calls/end', 'POST', {
        call_log_id: logId,
        call_id: logId,
        duration_seconds: st.seconds,
        talk_time_seconds: st.seconds
      }).catch(() => {});
    }

    // Upload voice recording if recorded or attached
    const audioToUpload = st.recordingFile || (st.recordingBlob ? new File([st.recordingBlob], `call_${logId}.webm`, { type: st.recordingBlob.type || 'audio/webm' }) : null);
    if (audioToUpload) {
      const fd = new FormData();
      fd.append('file', audioToUpload);
      await apiRequest(`/calls/${logId}/recording`, {
        method: 'POST',
        body: fd
      }).catch(err => console.error('Recording upload error:', err));
    }

    const isOther = (st.selectedDispoCode || '').toUpperCase() === 'OTHER' || (st.selectedDispoLabel || '').trim().toLowerCase() === 'other';
    const customOtherText = document.getElementById('ucm-other-text')?.value?.trim() || '';
    const finalNotes = isOther && customOtherText ? customOtherText : (st.selectedDispoLabel || '');

    const followupDt = document.getElementById('ucm-followup-dt')?.value;
    const customerNameVal = document.getElementById('ucm-customer-name')?.value?.trim() || '';
    const dispoPayload = {
      call_log_id: logId,
      call_id: logId,
      disposition_id: st.selectedDispoId,
      notes: finalNotes
    };
    if (customerNameVal) {
      dispoPayload.customer_name = customerNameVal;
    }
    if (followupDt) {
      dispoPayload.next_followup_at = new Date(followupDt).toISOString();
      dispoPayload.followup_notes = `Callback: ${finalNotes}`;
      dispoPayload.followup_priority = 'high';
    }

    await apiRequest('/calls/disposition', 'POST', dispoPayload);

    const cb = st.onSaved;
    closeUnifiedCallModal();
    if (typeof cb === 'function') {
      cb();
    }
  } catch (err) {
    console.error('Save disposition error:', err);
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerText = 'Save Disposition';
    }
    showToast(err.message || 'Failed to save disposition.', 'error');
  }
}

function closeUnifiedCallModal() {
  stopUnifiedCallTimersAndMic();
  const modal = document.getElementById('unified-call-modal');
  if (modal) modal.remove();
}


