// TeleCall CRM - Telecaller / Agent Workspace Controller
// Modern White & Blue SaaS Architecture

let currentDispositions = [];
let myAssignedLeads = [];
let activeCallLogId = null;
let activeCallTimerInterval = null;
let activeCallSeconds = 0;
let agentWeeklyChartInstance = null;
let activeDialerSession = null;
let dialerCountdownInterval = null;

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireAuth(['telecaller', 'admin', 'manager', 'super_admin'])) return;

  const user = getUser();
  if (user) {
    if (document.getElementById('emp-user-name')) document.getElementById('emp-user-name').innerText = user.full_name;
    if (document.getElementById('emp-company-name')) document.getElementById('emp-company-name').innerText = user.company_name || 'Apex Realty Global';
    const initials = (user.full_name || 'AG').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    if (document.getElementById('emp-avatar-initials')) document.getElementById('emp-avatar-initials').innerText = initials || 'AG';
  }

  // Theme check
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.classList.add('dark');
    updateThemeIcon(true);
  }

  await Promise.allSettled([
    loadDispositions().catch(e => console.error('Dispositions error:', e)),
    checkCallGate().catch(e => console.error('Call gate error:', e)),
    loadAgentDashboard().catch(e => console.error('Dashboard error:', e)),
    loadMyLeads().catch(e => console.error('Leads error:', e)),
    loadMyFollowups().catch(e => console.error('Followups error:', e)),
    initSuperAdminTransparency().catch(e => console.error('Transparency error:', e))
  ]);

  startNotificationPolling();
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
});

// ================= THEME TOGGLE =================
function toggleDarkMode() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  updateThemeIcon(isDark);
}

function updateThemeIcon(isDark) {
  const icon = document.getElementById('theme-icon');
  if (icon) {
    icon.setAttribute('data-lucide', isDark ? 'sun' : 'moon');
    (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
  }
}

// ================= TAB SWITCHER =================
function switchAgentTab(tabKey) {
  if (typeof closeMobileSidebar === 'function') closeMobileSidebar();
  const tabs = ['dashboard', 'leads', 'followups', 'dialer', 'history'];
  tabs.forEach(t => {
    const btn = document.getElementById(`agent-tab-dashboard`);
    const link = document.getElementById(`agent-tab-${t}`);
    const sec = document.getElementById(`agent-sec-${t}`);
    if (t === tabKey) {
      if (link) link.className = 'flex items-center justify-between px-3.5 py-2.5 rounded-xl transition bg-blue-600 text-white font-semibold shadow-sm';
      if (sec) sec.classList.remove('hidden');
    } else {
      if (link) link.className = 'flex items-center justify-between px-3.5 py-2.5 rounded-xl transition hover:bg-navy-800 text-slate-300';
      if (sec) sec.classList.add('hidden');
    }
  });

  // Mobile Bottom Navigation Bar Active Tab Highlighting
  const empNavTabs = ['dashboard', 'leads', 'dialer', 'followups', 'history'];
  empNavTabs.forEach(t => {
    const mBtn = document.getElementById(`agent-bottom-${t}`);
    if (mBtn) {
      if (t === 'dialer') {
        const circle = mBtn.querySelector('div');
        if (circle) {
          if (tabKey === 'dialer') {
            circle.className = 'w-12 h-12 rounded-full bg-gradient-to-tr from-emerald-500 to-teal-500 text-white flex items-center justify-center shadow-xl shadow-emerald-500/50 border-4 border-navy-900';
          } else {
            circle.className = 'w-12 h-12 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-xl shadow-blue-500/50 border-4 border-navy-900';
          }
        }
      } else {
        if (t === tabKey) {
          mBtn.className = 'flex flex-col items-center space-y-1 text-blue-400 font-bold active:scale-90 transition';
        } else {
          mBtn.className = 'flex flex-col items-center space-y-1 text-slate-400 hover:text-white active:scale-90 transition';
        }
      }
    }
  });

  if (tabKey === 'dashboard') loadAgentDashboard();
  if (tabKey === 'leads') loadMyLeads();
  if (tabKey === 'followups') loadMyFollowups();
  if (tabKey === 'history') loadMyCallHistory();

  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

// ================= PRESENCE STATUS =================
async function changePresenceStatus(status) {
  let breakReason = null;
  if (status === 'break') {
    breakReason = prompt('Enter reason for break (e.g. Lunch, Tea Break, Training):', 'Lunch');
    if (!breakReason) {
      document.getElementById('agent-presence-select').value = 'idle';
      return;
    }
  }

  try {
    await apiRequest('/employees/status', 'POST', {
      status: status,
      break_reason: breakReason
    });
  } catch (err) {
    alert(err.message || 'Status update failed.');
  }
}

// ================= DISPOSITIONS & CALL GATE =================
async function loadDispositions() {
  try {
    currentDispositions = await apiRequest('/calls/dispositions');
    if (Array.isArray(currentDispositions)) {
      window.__cachedDispositions = currentDispositions;
    }
    const mandSelect = document.getElementById('mand-dispo-select');
    if (mandSelect && Array.isArray(currentDispositions)) {
      mandSelect.innerHTML = currentDispositions.map(d => `<option value="${d.id}">${d.label || d.name || d.code}</option>`).join('');
    }
  } catch (err) {
    console.error('Error loading dispositions:', err);
  }
}

async function checkCallGate(openModal = false) {
  try {
    const gate = await apiRequest('/calls/gate-status');
    if (gate.is_blocked && gate.blocking_call_id) {
      activeCallLogId = gate.blocking_call_id;
      if (openModal) {
        document.getElementById('mandatory-disposition-modal').classList.remove('hidden');
        (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
      }
    }
  } catch (err) {}
}

async function submitMandatoryDisposition() {
  const dispoSelect = document.getElementById('mand-dispo-select');
  const dispoId = dispoSelect?.value;
  const dispoLabel = dispoSelect?.options[dispoSelect.selectedIndex]?.text || 'Completed';
  const notes = document.getElementById('mand-notes-textarea')?.value?.trim() || dispoLabel;
  const followupDt = document.getElementById('mand-followup-dt')?.value;

  if (!dispoId) {
    alert('Please select a disposition outcome.');
    return;
  }

  try {
    const dispoPayload = {
      call_log_id: activeCallLogId,
      call_id: activeCallLogId,
      disposition_id: dispoId,
      notes: notes
    };

    if (followupDt) {
      dispoPayload.next_followup_at = new Date(followupDt).toISOString();
      dispoPayload.followup_notes = `Callback: ${dispoLabel}`;
      dispoPayload.followup_priority = 'high';
    }

    await apiRequest('/calls/disposition', 'POST', dispoPayload);

    document.getElementById('mandatory-disposition-modal').classList.add('hidden');
    const notesInput = document.getElementById('mand-notes-textarea');
    if (notesInput) notesInput.value = '';
    const fupInput = document.getElementById('mand-followup-dt');
    if (fupInput) fupInput.value = '';
    activeCallLogId = null;

    await loadAgentDashboard();
    await loadMyFollowups();

    // If auto-dialer active, advance queue
    if (activeDialerSession) {
      skipAgentAutoDialerLead();
    }

  } catch (err) {
    alert(err.message || 'Failed to submit disposition.');
  }
}

// ================= AGENT DASHBOARD =================
async function loadAgentDashboard() {
  // Always initialize the chart immediately so it is never blank
  renderAgentChart();

  let calls = [];
  try {
    calls = await apiRequest('/reports/calls?limit=50');
  } catch (err) {
    console.warn('Could not load call reports:', err);
  }

  const totalCalls = Array.isArray(calls) ? calls.length : 0;
  const connected = Array.isArray(calls) ? calls.filter(c => c.disposition_name === 'Connected' || c.status === 'connected').length : 0;
  const missed = Array.isArray(calls) ? calls.filter(c => c.status === 'missed' || c.status === 'no_answer' || c.status === 'busy').length : 0;
  const talkSec = Array.isArray(calls) ? calls.reduce((acc, c) => acc + (c.duration_seconds || 0), 0) : 0;

  if (document.getElementById('agent-stat-total')) document.getElementById('agent-stat-total').innerText = totalCalls;
  if (document.getElementById('agent-stat-conn')) document.getElementById('agent-stat-conn').innerText = connected;
  if (document.getElementById('agent-stat-miss')) document.getElementById('agent-stat-miss').innerText = missed;
  if (document.getElementById('agent-stat-talk')) document.getElementById('agent-stat-talk').innerText = formatDuration(talkSec);
  if (document.getElementById('shift-calls-count')) document.getElementById('shift-calls-count').innerText = totalCalls;
  if (document.getElementById('shift-talk-time')) document.getElementById('shift-talk-time').innerText = formatDuration(talkSec);

  // Target vs Achieved (Target: 50 calls)
  const target = 50;
  const pct = Math.min(100, Math.round((totalCalls / target) * 100));
  if (document.getElementById('target-progress-text')) {
    document.getElementById('target-progress-text').innerText = `${totalCalls} / ${target} Calls Achieved (${pct}%)`;
  }
  if (document.getElementById('target-progress-bar')) {
    document.getElementById('target-progress-bar').style.width = `${pct}%`;
  }

  // Render Recent Calls Table
  const tbody = document.getElementById('agent-recent-calls-tbody');
  if (tbody) {
    if (!Array.isArray(calls) || calls.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-400">No calls made today. Click "Call Now" on any lead to start!</td></tr>';
    } else {
      tbody.innerHTML = calls.slice(0, 10).map(c => `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-2.5 px-3 font-mono text-[11px] text-slate-500">${c.call_date ? c.call_date.substring(11, 16) : ''}</td>
          <td class="py-2.5 px-3 font-bold text-slate-900">${escapeHtml(c.lead_name || 'Customer')}</td>
          <td class="py-2.5 px-3 font-mono">${escapeHtml(c.lead_phone || '')}</td>
          <td class="py-2.5 px-3 font-mono">${formatDuration(c.duration_seconds || 0)}</td>
          <td class="py-2.5 px-3">
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${
              (c.disposition_name === 'Connected' || c.status === 'connected') ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-700'
            }">${escapeHtml(c.disposition_name || c.disposition_label || 'Completed')}</span>
          </td>
          <td class="py-2.5 px-3">
            ${c.recording_url ? `
              <audio controls src="${c.recording_url}" class="h-7 max-w-[160px]"></audio>
            ` : '<span class="text-slate-400 text-[10px] italic">No audio</span>'}
          </td>
        </tr>
      `).join('');
    }
  }

  // Follow-ups due
  try {
    const fups = await apiRequest('/followups?timeframe=today');
    const fupList = Array.isArray(fups) ? fups : [];
    if (document.getElementById('agent-stat-fup')) document.getElementById('agent-stat-fup').innerText = fupList.length;
    if (document.getElementById('agent-fup-count')) document.getElementById('agent-fup-count').innerText = fupList.length;
    renderTodayFollowups(fupList);
  } catch (err) {
    console.warn('Could not load follow-ups:', err);
    renderTodayFollowups([]);
  }

  // Live Weekly Chart Analytics
  try {
    const analytics = await apiRequest('/dashboard/weekly-analytics');
    if (analytics && analytics.days_labels && analytics.days_labels.length > 0) {
      renderAgentChart(analytics.days_labels, analytics.connected_series, analytics.missed_series);
    }
  } catch (err) {
    console.warn('Weekly analytics live fetch fallback');
  }
}

function renderTodayFollowups(fups) {
  const container = document.getElementById('agent-today-fup-container');
  if (!container) return;

  if (!Array.isArray(fups) || fups.length === 0) {
    container.innerHTML = '<div class="text-center py-8 text-slate-400 text-xs">No pending callbacks scheduled for today.</div>';
    return;
  }

  container.innerHTML = fups.map(f => {
    const cleanPhone = String(f.lead_phone || '').replace(/[^\d+*#]/g, '');
    return `
    <div class="p-3 rounded-xl border border-slate-200 bg-slate-50 flex items-center justify-between text-xs">
      <div>
        <h5 class="font-bold text-slate-900">${escapeHtml(f.lead_name || 'Customer')}</h5>
        <p class="text-slate-500 font-mono text-[11px]">${escapeHtml(f.lead_phone || '')}</p>
        <p class="text-[10px] text-slate-400 mt-0.5">${escapeHtml(f.notes || 'No notes')}</p>
      </div>
      <button type="button" onclick="agentInitiateCall('${f.lead_id}', '${escapeHtml(f.lead_name)}', '${f.lead_phone}')" class="btn-primary-glow px-3 py-1.5 text-xs font-bold flex items-center space-x-1 cursor-pointer">
        <i data-lucide="phone" class="w-3.5 h-3.5"></i>
        <span>Call</span>
      </button>
    </div>
  `;
  }).join('');

  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

function renderAgentChart(labels, connectedData, missedData, retryCount = 0) {
  const canvas = document.getElementById('agentWeeklyChart');
  if (!canvas) return;

  if (typeof Chart === 'undefined') {
    if (retryCount < 10) {
      setTimeout(() => renderAgentChart(labels, connectedData, missedData, retryCount + 1), 350);
    }
    return;
  }

  if (agentWeeklyChartInstance) {
    agentWeeklyChartInstance.destroy();
  }

  const isDark = document.documentElement.classList.contains('dark');
  const textColor = isDark ? '#94A3B8' : '#64748B';

  const chartLabels = labels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Today'];
  const dataConn = connectedData || [12, 19, 15, 25, 22, 18, 14];
  const dataMiss = missedData || [3, 4, 2, 5, 3, 2, 1];

  agentWeeklyChartInstance = new Chart(canvas, {
    type: 'line',
    data: {
      labels: chartLabels,
      datasets: [
        {
          label: 'Connected Calls',
          data: dataConn,
          borderColor: '#2563EB',
          backgroundColor: 'rgba(37, 99, 235, 0.1)',
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointBackgroundColor: '#2563EB'
        },
        {
          label: 'Missed / Busy',
          data: dataMiss,
          borderColor: '#94A3B8',
          backgroundColor: 'rgba(148, 163, 184, 0.05)',
          fill: true,
          tension: 0.35,
          pointRadius: 3,
          borderDash: [4, 4]
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: {
            boxWidth: 10,
            font: { size: 10, weight: 'bold' },
            color: textColor
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } },
        y: { beginAtZero: true, ticks: { color: textColor, precision: 0 } }
      }
    }
  });
}

// ================= TAB 2: MY LEADS =================
async function loadMyLeads() {
  try {
    myAssignedLeads = await apiRequest('/leads?limit=200');
    const badge = document.getElementById('agent-leads-count');
    if (badge) badge.innerText = myAssignedLeads.length;
    renderAgentLeadsTable(myAssignedLeads);
    updateHeroLeadCard();
  } catch (err) {
    console.error('Error loading my leads:', err);
  }
}

function filterAgentLeads() {
  const q = (document.getElementById('agent-lead-search')?.value || '').toLowerCase().trim();
  const filtered = myAssignedLeads.filter(l => 
    (l.first_name + ' ' + (l.last_name || '')).toLowerCase().includes(q) ||
    (l.phone || '').includes(q) ||
    (l.city || '').toLowerCase().includes(q)
  );
  renderAgentLeadsTable(filtered);
}

function renderAgentLeadsTable(leads) {
  const tbody = document.getElementById('agent-leads-tbody');
  const mList = document.getElementById('agent-leads-mobile-list');

  if (tbody) {
    if (leads.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-400">No leads found.</td></tr>';
    } else {
      tbody.innerHTML = leads.map(l => {
        const cleanPhone = String(l.phone || '').replace(/[^\d+*#]/g, '');
        return `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(l.first_name)} ${escapeHtml(l.last_name || '')}</td>
          <td class="py-3 px-4 font-mono">${escapeHtml(l.phone)}</td>
          <td class="py-3 px-4 text-slate-500">${escapeHtml(l.city || '--')}</td>
          <td class="py-3 px-4">
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold" style="background-color: ${l.stage_color || '#3B82F6'}20; color: ${l.stage_color || '#3B82F6'}">
              ${escapeHtml(l.stage_name || 'New')}
            </span>
          </td>
          <td class="py-3 px-4 font-mono font-bold">${l.total_calls_count || 0}</td>
          <td class="py-3 px-4 text-center">
            <button type="button" onclick="agentInitiateCall('${l.id}', '${escapeHtml(l.first_name)}', '${l.phone}')" class="btn-primary-glow px-3 py-1 text-xs font-bold inline-flex items-center justify-center cursor-pointer">
              Call
            </button>
          </td>
        </tr>
      `;
      }).join('');
    }
  }

  if (mList) {
    if (leads.length === 0) {
      mList.innerHTML = '<div class="text-center py-8 text-slate-400 text-xs">No leads found.</div>';
    } else {
      mList.innerHTML = leads.map(l => {
        const cleanPhone = String(l.phone || '').replace(/[^\d+*#]/g, '');
        const initials = ((l.first_name ? l.first_name[0] : '') + (l.last_name ? l.last_name[0] : '')).toUpperCase() || 'L';
        const name = `${escapeHtml(l.first_name)} ${escapeHtml(l.last_name || '')}`.trim();
        return `
        <div class="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-sm flex items-center justify-between gap-3 active:bg-slate-50 transition">
          <div class="flex items-center space-x-3 min-w-0">
            <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-700 font-extrabold flex items-center justify-center shrink-0 text-sm">
              ${initials}
            </div>
            <div class="min-w-0">
              <div class="flex items-center space-x-1.5">
                <h5 class="font-extrabold text-sm text-slate-900 truncate">${name}</h5>
                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0" style="background-color: ${l.stage_color || '#3B82F6'}20; color: ${l.stage_color || '#3B82F6'}">
                  ${escapeHtml(l.stage_name || 'New')}
                </span>
              </div>
              <p class="text-xs font-mono text-slate-500 truncate mt-0.5">${escapeHtml(l.phone)} &bull; ${escapeHtml(l.city || 'India')}</p>
            </div>
          </div>
          <button type="button" onclick="agentInitiateCall('${l.id}', '${escapeHtml(l.first_name)}', '${l.phone}')" class="w-11 h-11 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white flex items-center justify-center shadow-lg shadow-emerald-500/30 shrink-0 active:scale-95 transition" title="Call Customer (In-CRM)">
            <i data-lucide="phone-call" class="w-5 h-5"></i>
          </button>
        </div>
        `;
      }).join('');
    }
  }
  if (window.lucide) (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

// ================= TAB 3: FOLLOW-UPS =================
async function loadMyFollowups() {
  try {
    const list = await apiRequest('/followups?timeframe=today');
    const tbody = document.getElementById('agent-full-fup-tbody');
    const mList = document.getElementById('agent-followups-mobile-list');

    if (tbody) {
      if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-6 text-slate-400">No pending follow-ups.</td></tr>';
      } else {
        tbody.innerHTML = list.map(f => {
          const cleanPhone = String(f.lead_phone || '').replace(/[^\d+*#]/g, '');
          return `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-mono text-[11px] text-slate-600">${f.scheduled_at ? f.scheduled_at.substring(0, 16) : ''}</td>
            <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(f.lead_name || 'Customer')}</td>
            <td class="py-3 px-4 font-mono">${escapeHtml(f.lead_phone || '')}</td>
            <td class="py-3 px-4 text-slate-600">${escapeHtml(f.notes || '--')}</td>
            <td class="py-3 px-4 text-center">
              <button type="button" onclick="agentInitiateCall('${f.lead_id}', '${escapeHtml(f.lead_name)}', '${f.lead_phone}')" class="btn-primary-glow px-3 py-1 text-xs font-bold inline-flex items-center justify-center cursor-pointer">
                Call Now
              </button>
            </td>
          </tr>
        `;
        }).join('');
      }
    }

    if (mList) {
      if (list.length === 0) {
        mList.innerHTML = '<div class="text-center py-8 text-slate-400 text-xs">No pending follow-ups.</div>';
      } else {
        mList.innerHTML = list.map(f => {
          const cleanPhone = String(f.lead_phone || '').replace(/[^\d+*#]/g, '');
          const timeStr = f.scheduled_at ? f.scheduled_at.substring(0, 16) : 'Today';
          return `
          <div class="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-sm space-y-2">
            <div class="flex items-center justify-between">
              <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 border border-amber-200 text-amber-700">
                ⏰ ${timeStr}
              </span>
              <span class="text-[10px] font-bold text-slate-400">Callback</span>
            </div>
            <div class="flex items-center justify-between">
              <div class="min-w-0 pr-2">
                <h5 class="font-extrabold text-sm text-slate-900 truncate">${escapeHtml(f.lead_name || 'Customer')}</h5>
                <p class="text-xs font-mono text-slate-500 mt-0.5">${escapeHtml(f.lead_phone || '')}</p>
                ${f.notes ? `<p class="text-xs text-slate-600 mt-1 italic truncate">"${escapeHtml(f.notes)}"</p>` : ''}
              </div>
              <button type="button" onclick="agentInitiateCall('${f.lead_id}', '${escapeHtml(f.lead_name)}', '${f.lead_phone}')" class="w-11 h-11 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white flex items-center justify-center shadow-lg shadow-emerald-500/30 shrink-0 active:scale-95 transition" title="Call Callback (In-CRM)">
                <i data-lucide="phone-call" class="w-5 h-5"></i>
              </button>
            </div>
          </div>
          `;
        }).join('');
      }
    }
    if (window.lucide) (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));

  } catch (err) {
    console.error('Error loading follow-ups:', err);
  }
}

// ================= TAB 5: CALL HISTORY =================
async function loadMyCallHistory() {
  try {
    const calls = await apiRequest('/reports/calls?limit=100');
    const tbody = document.getElementById('agent-full-history-tbody');
    const mList = document.getElementById('agent-history-mobile-list');

    if (tbody) {
      if (calls.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-400">No call records found.</td></tr>';
      } else {
        tbody.innerHTML = calls.map(c => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-mono text-[11px] text-slate-600">${c.call_date || ''}</td>
            <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(c.lead_name || 'Customer')}</td>
            <td class="py-3 px-4 font-mono">${escapeHtml(c.lead_phone || '')}</td>
            <td class="py-3 px-4 font-mono">${formatDuration(c.duration_seconds || 0)}</td>
            <td class="py-3 px-4 font-bold text-slate-700">${escapeHtml(c.disposition_name || 'Completed')}</td>
            <td class="py-3 px-4">
              ${c.recording_url ? `
                <audio controls src="${c.recording_url}" class="h-8 max-w-[180px]"></audio>
              ` : '<span class="text-slate-400 text-[11px] italic">No audio</span>'}
            </td>
          </tr>
        `).join('');
      }
    }

    if (mList) {
      if (calls.length === 0) {
        mList.innerHTML = '<div class="text-center py-8 text-slate-400 text-xs">No call records found.</div>';
      } else {
        mList.innerHTML = calls.map(c => {
          return `
          <div class="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-sm space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-[10px] font-mono text-slate-400">${c.call_date || ''}</span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                ${escapeHtml(c.disposition_name || 'Completed')}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <div>
                <h5 class="font-extrabold text-sm text-slate-900">${escapeHtml(c.lead_name || 'Customer')}</h5>
                <p class="text-xs font-mono text-slate-500 mt-0.5">${escapeHtml(c.lead_phone || '')} &bull; ${formatDuration(c.duration_seconds || 0)}</p>
              </div>
              ${c.recording_url ? `
                <audio controls src="${c.recording_url}" class="h-8 max-w-[140px]"></audio>
              ` : ''}
            </div>
          </div>
          `;
        }).join('');
      }
    }
    if (window.lucide) (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));

  } catch (err) {
    console.error('Error loading history:', err);
  }
}

// ================= CALL ACTIONS & UNIFIED CALL MODAL =================
function agentInitiateCall(leadId, leadName, phone, fromNativeAnchor = false, evt = null) {
  if (evt && typeof evt.preventDefault === 'function') {
    evt.preventDefault();
  }
  const cleanPhone = phone ? String(phone).replace(/[^\d+*#]/g, '') : '';
  if (!cleanPhone) {
    if (typeof showToast === 'function') showToast('No valid phone number to call', 'warning');
    return false;
  }

  // Open Unified Call Modal (on mobile, triggers real Phone SIM dialer + CRM tracking)
  const useMobileSim = (typeof isMobileDevice === 'function' && isMobileDevice());
  openUnifiedCallModal({
    leadId: leadId || null,
    leadName: leadName || 'Customer',
    phone: cleanPhone,
    dialMethod: useMobileSim ? 'sim' : 'crm',
    onSaved: async () => {
      try { await loadAgentDashboard(); } catch (e) {}
      try { await loadMyFollowups(); } catch (e) {}
      try { await loadMyCallHistory(); } catch (e) {}
      if (activeDialerSession) {
        skipAgentAutoDialerLead();
      }
    }
  });

  return false;
}

function toggleCallMute() {
  const btn = document.getElementById('btn-call-mute');
  const isMuted = btn.innerText === 'Unmute';
  btn.innerText = isMuted ? 'Mute' : 'Unmute';
  btn.className = isMuted 
    ? 'py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-xs font-bold text-slate-700'
    : 'py-2.5 rounded-xl border border-amber-300 bg-amber-50 text-xs font-bold text-amber-700';
}

function toggleCallHold() {
  const btn = document.getElementById('btn-call-hold');
  const isHold = btn.innerText === 'Unhold';
  btn.innerText = isHold ? 'Hold' : 'Unhold';
  btn.className = isHold 
    ? 'py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-xs font-bold text-slate-700'
    : 'py-2.5 rounded-xl border border-blue-300 bg-blue-50 text-xs font-bold text-blue-700';
}

async function endActiveCall() {
  if (activeCallTimerInterval) {
    clearInterval(activeCallTimerInterval);
    activeCallTimerInterval = null;
  }

  document.getElementById('active-call-modal').classList.add('hidden');

  try {
    if (activeCallLogId) {
      await apiRequest('/calls/end', 'POST', {
        call_log_id: activeCallLogId,
        call_id: activeCallLogId,
        duration_seconds: activeCallSeconds,
        talk_time_seconds: activeCallSeconds,
        call_notes: document.getElementById('active-call-live-notes')?.value || ''
      });
    }
  } catch (err) {}

  document.getElementById('active-call-live-notes').value = '';

  // Trigger Mandatory Call Gate Disposition Popup
  document.getElementById('mandatory-disposition-modal').classList.remove('hidden');
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

// ================= KEYPAD & FLOATING DIALER =================
function syncKeypadDialHref() {
  // Pure In-CRM Calling: No tel: href assignment
}

function agentPressKey(d) {
  const el = document.getElementById('agent-keypad-phone');
  if (el) {
    el.value += d;
  }
}

function agentBackspaceKey() {
  const el = document.getElementById('agent-keypad-phone');
  if (el) {
    el.value = el.value.slice(0, -1);
  }
}

function agentKeypadDial(e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  const phone = document.getElementById('agent-keypad-phone')?.value.trim();
  const cleanPhone = String(phone || '').replace(/[^\d+*#]/g, '');
  if (!cleanPhone || cleanPhone.length < 3) {
    alert('Please enter a valid phone number.');
    return false;
  }
  return agentInitiateCall(null, 'Manual Call', cleanPhone, false, e);
}

function openAgentFloatingDialer() {
  switchAgentTab('dialer');
}

function closeAgentFloatingDialer() {
  document.getElementById('agent-floating-dialer')?.classList.add('hidden');
}

function syncFloatDialHref() {
  // Pure In-CRM Calling: No tel: href assignment
}

function agentFloatKey(d) {
  const el = document.getElementById('agent-float-phone');
  if (el) {
    el.value += d;
  }
}

function handleAgentFloatCall(e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  const phone = document.getElementById('agent-float-phone')?.value.trim();
  const cleanPhone = String(phone || '').replace(/[^\d+*#]/g, '');
  if (!cleanPhone || cleanPhone.length < 3) {
    alert('Please enter a valid phone number.');
    return false;
  }
  closeAgentFloatingDialer();
  return agentInitiateCall(null, 'Quick Dial', cleanPhone, false, e);
}

// ================= AUTO-DIALER CAMPAIGN RUNNER =================
async function startAgentAutoDialer() {
  const mode = document.getElementById('agent-ad-mode')?.value || 'preview';
  const delay = parseInt(document.getElementById('agent-ad-delay')?.value) || 8;

  try {
    const res = await apiRequest('/autodialer/start', 'POST', {
      mode: mode,
      countdown_seconds: delay
    });

    activeDialerSession = res;
    document.getElementById('agent-ad-pill').innerText = 'Active Running';
    document.getElementById('agent-ad-pill').className = 'text-xs font-bold px-3 py-1 rounded-full bg-emerald-100 text-emerald-800';

    document.getElementById('agent-btn-ad-start').classList.add('hidden');
    document.getElementById('agent-btn-ad-pause').classList.remove('hidden');
    document.getElementById('agent-btn-ad-skip').classList.remove('hidden');
    document.getElementById('agent-btn-ad-stop').classList.remove('hidden');

    updateAutoDialerQueueView(res);

  } catch (err) {
    alert(err.message || 'Auto-dialer session could not start.');
  }
}

function updateAutoDialerQueueView(session) {
  if (!session) return;
  const lead = session.current_lead;
  document.getElementById('agent-ad-progress-text').innerText = `${session.current_index || 0} / ${session.total_leads || 0} Leads`;
  document.getElementById('agent-ad-progress-bar').style.width = `${session.progress_percentage || 0}%`;

  if (lead) {
    const cleanPhone = String(lead.phone || '').replace(/[^\d+*#]/g, '');
    document.getElementById('agent-ad-current-lead-text').innerHTML = `
      <b>Next Up:</b> ${escapeHtml(lead.first_name)} (${lead.phone}) &bull; City: ${lead.city || 'N/A'}
      <button type="button" onclick="agentInitiateCall('${lead.id}', '${escapeHtml(lead.first_name)}', '${lead.phone}')" class="ml-2 btn-primary-glow px-2.5 py-0.5 text-[11px] font-bold inline-flex items-center cursor-pointer">
        Dial Customer
      </button>
    `;
  } else {
    document.getElementById('agent-ad-current-lead-text').innerText = 'Campaign finished or no leads left in queue.';
  }
}

async function pauseAgentAutoDialer() {
  if (!activeDialerSession) return;
  try {
    await apiRequest(`/autodialer/session/${activeDialerSession.session_id}/pause`, 'POST');
    document.getElementById('agent-ad-pill').innerText = 'Paused';
    document.getElementById('agent-ad-pill').className = 'text-xs font-bold px-3 py-1 rounded-full bg-amber-100 text-amber-800';
  } catch (err) {}
}

async function skipAgentAutoDialerLead() {
  if (!activeDialerSession) return;
  try {
    const res = await apiRequest(`/autodialer/session/${activeDialerSession.session_id}/skip`, 'POST');
    activeDialerSession = res;
    updateAutoDialerQueueView(res);
  } catch (err) {}
}

async function stopAgentAutoDialer() {
  if (!activeDialerSession) return;
  try {
    await apiRequest(`/autodialer/session/${activeDialerSession.session_id}/stop`, 'POST');
    activeDialerSession = null;
    document.getElementById('agent-ad-pill').innerText = 'Inactive';
    document.getElementById('agent-ad-pill').className = 'text-xs font-bold px-3 py-1 rounded-full bg-slate-100 text-slate-600';

    document.getElementById('agent-btn-ad-start').classList.remove('hidden');
    document.getElementById('agent-btn-ad-pause').classList.add('hidden');
    document.getElementById('agent-btn-ad-skip').classList.add('hidden');
    document.getElementById('agent-btn-ad-stop').classList.add('hidden');

    document.getElementById('agent-ad-current-lead-text').innerText = 'Campaign stopped.';
  } catch (err) {}
}

// ================= UTILITIES =================
function formatDuration(sec) {
  if (!sec || sec < 0) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}


// ================= NATIVE DIALER SUBVIEW TOGGLE =================
function toggleDialerSubView(view) {
  const keypadView = document.getElementById('dialer-view-keypad');
  const autoView = document.getElementById('dialer-view-autodialer');
  const btnKeypad = document.getElementById('subview-btn-keypad');
  const btnAuto = document.getElementById('subview-btn-autodialer');

  if (view === 'keypad') {
    if (keypadView) keypadView.classList.remove('hidden');
    if (autoView) autoView.classList.add('hidden');
    if (btnKeypad) {
      btnKeypad.className = 'flex-1 py-2 text-xs font-bold rounded-xl bg-white text-slate-900 shadow-sm transition';
    }
    if (btnAuto) {
      btnAuto.className = 'flex-1 py-2 text-xs font-bold rounded-xl text-slate-600 hover:text-slate-900 transition';
    }
  } else {
    if (keypadView) keypadView.classList.add('hidden');
    if (autoView) autoView.classList.remove('hidden');
    if (btnAuto) {
      btnAuto.className = 'flex-1 py-2 text-xs font-bold rounded-xl bg-white text-slate-900 shadow-sm transition';
    }
    if (btnKeypad) {
      btnKeypad.className = 'flex-1 py-2 text-xs font-bold rounded-xl text-slate-600 hover:text-slate-900 transition';
    }
  }
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

// Contact Auto-Lookup while typing on keypad
function lookupKeypadContact() {
  const phone = (document.getElementById('agent-keypad-phone')?.value || '').trim().replace(/[^\d]/g, '');
  const matchEl = document.getElementById('dialer-matched-contact');
  if (!matchEl) return;

  if (phone.length < 3) {
    matchEl.innerText = '';
    return;
  }

  const found = myAssignedLeads.find(l => {
    const lPhone = String(l.phone || '').replace(/[^\d]/g, '');
    return lPhone.includes(phone) || phone.includes(lPhone);
  });

  if (found) {
    matchEl.innerHTML = `<span class="inline-flex items-center space-x-1"><i data-lucide="user-check" class="w-3.5 h-3.5 inline mr-1"></i> ${escapeHtml(found.first_name)} ${escapeHtml(found.last_name || '')} (${escapeHtml(found.stage_name || 'Lead')})</span>`;
    (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
  } else {
    matchEl.innerText = '';
  }
}

// ================= HERO LEAD QUEUE CARD =================
let currentHeroLeadIndex = 0;

function updateHeroLeadCard() {
  const card = document.getElementById('hero-next-lead-card');
  if (!card) return;

  if (!myAssignedLeads || myAssignedLeads.length === 0) {
    card.classList.add('hidden');
    return;
  }

  card.classList.remove('hidden');
  const lead = myAssignedLeads[currentHeroLeadIndex % myAssignedLeads.length];
  if (!lead) return;

  const cleanPhone = String(lead.phone || '').replace(/[^\d+*#]/g, '');
  const nameEl = document.getElementById('hero-next-name');
  const phoneEl = document.getElementById('hero-next-phone');
  const stageEl = document.getElementById('hero-next-stage');
  const callBtn = document.getElementById('hero-next-call-btn');

  if (nameEl) nameEl.innerText = `${lead.first_name} ${lead.last_name || ''}`.trim();
  if (phoneEl) phoneEl.innerText = `${lead.phone} • ${lead.city || 'India'}`;
  if (stageEl) stageEl.innerText = lead.stage_name || 'New Lead';
  if (callBtn) {
    callBtn.removeAttribute('href');
  }
}

function skipHeroLead() {
  if (!myAssignedLeads || myAssignedLeads.length === 0) return;
  currentHeroLeadIndex = (currentHeroLeadIndex + 1) % myAssignedLeads.length;
  updateHeroLeadCard();
}

function triggerHeroCall(e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  const lead = myAssignedLeads[currentHeroLeadIndex % myAssignedLeads.length];
  if (!lead) return false;
  const cleanPhone = String(lead.phone || '').replace(/[^\d+*#]/g, '');
  return agentInitiateCall(lead.id, `${lead.first_name} ${lead.last_name || ''}`, cleanPhone, false, e);
}
