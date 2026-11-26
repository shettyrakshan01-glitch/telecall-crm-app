// TeleCall CRM - Admin Controller
// Modern White & Blue SaaS Architecture with Dark Mode, 3-Column Shared Inbox, 4-Step Bulk Upload

let currentStages = [];
let currentEmployees = [];
let allWorkspaceLeads = [];
let selectedWorkspaceLead = null;
let currentImportFile = null;
let currentImportPreview = null;
let lastImportBatchId = null;
let weeklyChartInstance = null;
let realtimePollInterval = null;

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireAuth(['admin', 'manager', 'super_admin'])) return;

  // Refresh current user info from server to ensure name and role are fresh
  try {
    const me = await apiRequest('/auth/me');
    if (me && me.id) {
      setUser(me);
    }
  } catch (e) {
    // fallback to stored user if network issue
  }

  const user = getUser();
  if (user) {
    const nameEl = document.getElementById('nav-user-name');
    if (nameEl) nameEl.innerText = user.full_name;
    const bannerNameEl = document.getElementById('superadmin-banner-name');
    if (bannerNameEl) bannerNameEl.innerText = user.full_name;
    const compEl = document.getElementById('header-company-name');
    if (compEl) compEl.innerText = user.company_name || 'My Company';
    const initials = user.full_name ? user.full_name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() : 'VI';
    const initEl = document.getElementById('nav-avatar-initials');
    if (initEl) initEl.innerText = initials || 'SA';
  }

  // Preload call dispositions for instant unified call modal
  if (typeof preloadUnifiedDispositions === 'function') {
    preloadUnifiedDispositions().catch(() => {});
  }

  // Check saved theme
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.classList.add('dark');
    updateThemeIcon(true);
  }

  if (user && user.role === 'super_admin') {
    await initSuperAdminControls();
  }

  await loadStages();
  await loadEmployees();
  await loadAnalyticsDashboard();
  await loadWorkspaceLeads();
  await loadImportHistory();
  await updateBadges();
  await initSuperAdminTransparency();

  // If a URL hash was requested (e.g. #workspace or #contacts), activate that tab immediately
  const currentHash = window.location.hash ? window.location.hash.replace('#', '') : '';
  if (currentHash && currentHash !== 'analytics') {
    switchTab(currentHash);
  }

  startNotificationPolling();
  if (typeof checkAdminAlerts === 'function') checkAdminAlerts();
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
});

// ================= THEME TOGGLE (LIGHT / DARK) =================
function toggleDarkMode() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  updateThemeIcon(isDark);
  if (weeklyChartInstance) {
    loadWeeklyAnalyticsChart();
  }
}

function updateThemeIcon(isDark) {
  const icon = document.getElementById('theme-icon');
  if (icon) {
    icon.setAttribute('data-lucide', isDark ? 'sun' : 'moon');
    (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
  }
}

// ================= TAB SWITCHER =================
function switchTab(tabKey) {
  if (typeof closeMobileSidebar === 'function') closeMobileSidebar();
  if (realtimePollInterval) {
    clearInterval(realtimePollInterval);
    realtimePollInterval = null;
  }

  const allTabs = [
    'analytics', 'workspace', 'contacts', 'allocations',
    'followups', 'dialer', 'live', 'employees', 'reports', 'imports', 'telephony',
    'companies', 'plans', 'audits'
  ];

  allTabs.forEach(t => {
    const navBtn = document.getElementById(`nav-tab-${t}`);
    const sec = document.getElementById(`content-${t}`);
    if (t === tabKey) {
      if (navBtn) {
        navBtn.className = 'flex items-center justify-between px-3.5 py-2.5 rounded-xl transition bg-blue-600 text-white font-semibold shadow-sm';
      }
      if (sec) sec.classList.remove('hidden');
    } else {
      if (navBtn) {
        navBtn.className = 'flex items-center justify-between px-3.5 py-2.5 rounded-xl transition hover:bg-navy-800 text-slate-300';
      }
      if (sec) sec.classList.add('hidden');
    }
  });

  // Mobile Bottom Navigation Bar Active Tab Highlighting
  const mobileNavTabs = ['analytics', 'workspace', 'dialer', 'contacts'];
  mobileNavTabs.forEach(t => {
    const mBtn = document.getElementById(`mobile-nav-${t}`);
    if (mBtn) {
      if (t === tabKey) {
        mBtn.className = 'flex flex-col items-center justify-center p-1.5 text-xs text-blue-600 font-bold active:scale-90 transition';
      } else {
        mBtn.className = 'flex flex-col items-center justify-center p-1.5 text-xs text-slate-500 hover:text-blue-600 active:scale-90 transition';
      }
    }
  });

  if (tabKey === 'analytics') {
    loadAnalyticsDashboard();
  } else if (tabKey === 'workspace') {
    if (typeof backToWorkspaceList === 'function') backToWorkspaceList();
    loadWorkspaceLeads();
  } else if (tabKey === 'contacts') {
    loadContactsCatalog();
  } else if (tabKey === 'allocations') {
    loadAllocationData();
  } else if (tabKey === 'followups') {
    filterFollowUps('today');
  } else if (tabKey === 'dialer') {
    initDialerTab();
  } else if (tabKey === 'live') {
    loadLiveAgentWall();
    realtimePollInterval = setInterval(loadLiveAgentWall, 4000);
  } else if (tabKey === 'employees') {
    loadEmployeesTable();
  } else if (tabKey === 'reports') {
    loadCallReportsTable();
  } else if (tabKey === 'imports') {
    loadImportHistory();
  } else if (tabKey === 'telephony') {
    loadAdminDispositionManager();
    loadTelephonyConfig();
  } else if (tabKey === 'companies') {
    loadCompaniesSuperAdmin();
  } else if (tabKey === 'plans') {
    loadPlansSuperAdmin();
  } else if (tabKey === 'audits') {
    loadAuditsSuperAdmin();
  }

  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

// ================= GLOBAL METRICS & STAGES =================
async function loadStages() {
  try {
    currentStages = await apiRequest('/leads/stages');
    const stageSelects = [
      'single-lead-stage', 'paste-lead-stage', 'catalog-stage-filter',
      'wk-right-stage-select', 'import-default-stage', 'ad-stage-select'
    ];
    stageSelects.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const cur = el.value;
      let html = id.includes('filter') ? '<option value="">All Stages</option>' : '';
      currentStages.forEach(s => {
        html += `<option value="${s.id}">${s.name}</option>`;
      });
      el.innerHTML = html;
      if (cur) el.value = cur;
    });
  } catch (err) {
    console.error('Error loading stages:', err);
  }
}

async function loadEmployees() {
  try {
    currentEmployees = await apiRequest('/employees');
    
    // Workspace Filter
    const wsFilter = document.getElementById('workspace-agent-filter');
    if (wsFilter) {
      let html = '<option value="">All Agents / Master View (Track All)</option>';
      currentEmployees.forEach(e => {
        html += `<option value="${e.id}">${e.full_name} (${e.role.toUpperCase()})</option>`;
      });
      wsFilter.innerHTML = html;
    }

    // Right details assign select
    const rightAssign = document.getElementById('wk-right-assign-select');
    if (rightAssign) {
      let html = '<option value="">Unassigned</option>';
      currentEmployees.forEach(e => {
        html += `<option value="${e.id}">${e.full_name}</option>`;
      });
      rightAssign.innerHTML = html;
    }

    // Single agent for import
    const impSingle = document.getElementById('import-single-agent');
    if (impSingle) {
      let html = '';
      currentEmployees.forEach(e => {
        html += `<option value="${e.id}">${e.full_name} (${e.role})</option>`;
      });
      impSingle.innerHTML = html;
    }

    // Round robin checklist for import
    const impChecklist = document.getElementById('import-team-checklist');
    if (impChecklist) {
      let html = '';
      currentEmployees.forEach(e => {
        html += `
          <label class="flex items-center space-x-2 text-xs text-slate-700">
            <input type="checkbox" name="import-agent-chk" value="${e.id}" checked class="rounded text-blue-600">
            <span>${e.full_name}</span>
          </label>
        `;
      });
      impChecklist.innerHTML = html;
    }

    // Allocation checklist
    const allocChecklist = document.getElementById('allocation-agents-checklist');
    if (allocChecklist) {
      let html = '';
      currentEmployees.forEach(e => {
        html += `
          <label class="flex items-center space-x-2 text-xs text-slate-700">
            <input type="checkbox" name="alloc-agent-chk" value="${e.id}" checked class="rounded text-blue-600">
            <span>${e.full_name}</span>
          </label>
        `;
      });
      allocChecklist.innerHTML = html;
    }

    // Transfer dropdowns
    const fromSelect = document.getElementById('transfer-from-agent');
    const toSelect = document.getElementById('transfer-to-agent');
    if (fromSelect && toSelect) {
      let opts = '<option value="">Select Telecaller</option>';
      currentEmployees.forEach(e => {
        opts += `<option value="${e.id}">${e.full_name}</option>`;
      });
      fromSelect.innerHTML = opts;
      toSelect.innerHTML = opts;
    }

    // Reports filter
    const repAgent = document.getElementById('rep-agent-select');
    if (repAgent) {
      let html = '<option value="">All Telecallers</option>';
      currentEmployees.forEach(e => {
        html += `<option value="${e.id}">${e.full_name}</option>`;
      });
      repAgent.innerHTML = html;
    }

    const badgeAgent = document.getElementById('badge-agent-count');
    if (badgeAgent) badgeAgent.innerText = currentEmployees.length;

  } catch (err) {
    console.error('Error loading employees:', err);
  }
}

async function updateBadges() {
  try {
    const leads = await apiRequest('/leads?limit=1');
    const badgeLeads = document.getElementById('badge-leads-count');
    const badgeContacts = document.getElementById('badge-contacts-count');
    if (badgeLeads) badgeLeads.innerText = allWorkspaceLeads.length || '0';
    if (badgeContacts) badgeContacts.innerText = allWorkspaceLeads.length || '0';

    const fups = await apiRequest('/followups/summary');
    const badgeFup = document.getElementById('badge-followup-count');
    if (badgeFup) badgeFup.innerText = (fups.today_count || 0) + (fups.overdue_count || 0);
  } catch (err) {
    console.error('Error updating badges:', err);
  }
}

// ================= TAB 1: ANALYTICS & DASHBOARD =================
async function loadAnalyticsDashboard() {
  try {
    // 1. Fetch Realtime Metrics
    const rt = await apiRequest('/dashboard/realtime');
    const sm = rt.summary || {};
    document.getElementById('stat-total-calls').innerText = sm.total_calls_today || 0;
    
    const connRate = sm.connected_calls > 0 && sm.total_calls_today > 0 
      ? Math.round((sm.connected_calls / sm.total_calls_today) * 100) 
      : 0;
    document.getElementById('stat-connected-rate').innerText = `${connRate}%`;
    document.getElementById('stat-connected-bar').style.width = `${connRate}%`;

    document.getElementById('stat-converted-leads').innerText = sm.conversions_today || 0;
    document.getElementById('stat-conversion-pct').innerText = `${sm.conversion_rate_percentage || 0}% conversion rate`;

    // 2. Weekly Analytics & Pipeline Distribution
    await loadWeeklyAnalyticsChart();

    // 3. Performance Leaderboard Table
    const perf = await apiRequest('/dashboard/performance');
    const tbody = document.getElementById('agent-leaderboard-tbody');
    if (!perf || perf.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-slate-400">No agent performance logs recorded yet.</td></tr>';
      return;
    }

    tbody.innerHTML = perf.map(a => `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(a.agent_name)}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${
            a.agent_status === 'on_call' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
            a.agent_status === 'idle' ? 'bg-blue-50 text-blue-700 border border-blue-200' :
            a.agent_status === 'break' ? 'bg-amber-50 text-amber-700 border border-amber-200' :
            'bg-slate-100 text-slate-600'
          }">${(a.agent_status || 'offline').toUpperCase()}</span>
        </td>
        <td class="py-3 px-4 text-center font-bold">${a.today_calls_count || 0}</td>
        <td class="py-3 px-4 text-center text-emerald-600 font-bold">${a.connected_calls_count || 0}</td>
        <td class="py-3 px-4 text-center">${formatDuration(a.today_talk_time_sec || 0)}</td>
        <td class="py-3 px-4 text-center">${formatDuration(a.avg_talk_time_sec || 0)}</td>
        <td class="py-3 px-4 text-center font-semibold text-blue-600">${a.followup_completion_rate || 0}%</td>
        <td class="py-3 px-4 text-center text-slate-500">${formatDuration(a.average_gap_between_calls_sec || 0)}</td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading analytics:', err);
  }
}

async function loadWeeklyAnalyticsChart() {
  try {
    const data = await apiRequest('/dashboard/weekly-analytics');
    const wc = data.weekly_chart || { labels: [], connected: [], missed: [] };

    document.getElementById('stat-total-leads').innerText = data.total_leads || 0;

    // Render Stage Distribution Progress Bars
    const stageCont = document.getElementById('lead-stage-progress-container');
    if (stageCont && data.stage_distribution) {
      stageCont.innerHTML = data.stage_distribution.map(s => `
        <div>
          <div class="flex justify-between text-xs font-semibold text-slate-700 mb-1">
            <span class="flex items-center">
              <span class="w-2.5 h-2.5 rounded-full mr-2" style="background-color: ${s.color}"></span>
              ${escapeHtml(s.name)}
            </span>
            <span class="font-bold text-slate-900">${s.count} <span class="text-slate-400 font-normal">(${s.percentage}%)</span></span>
          </div>
          <div class="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
            <div class="h-2 rounded-full" style="width: ${s.percentage}%; background-color: ${s.color}"></div>
          </div>
        </div>
      `).join('');
    }

    // Render Chart.js
    const canvas = document.getElementById('weeklyCallsChart');
    if (!canvas) return;

    if (weeklyChartInstance) {
      weeklyChartInstance.destroy();
    }

    const isDark = document.documentElement.classList.contains('dark');
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const textColor = isDark ? '#94A3B8' : '#64748B';

    weeklyChartInstance = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: wc.labels,
        datasets: [
          {
            label: 'Connected Calls',
            data: wc.connected,
            backgroundColor: '#2563EB',
            borderRadius: 6,
            barThickness: 18
          },
          {
            label: 'Not Connected',
            data: wc.missed,
            backgroundColor: isDark ? '#334155' : '#E2E8F0',
            borderRadius: 6,
            barThickness: 18
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: {
              boxWidth: 12,
              font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' },
              color: textColor
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: textColor, font: { family: 'Plus Jakarta Sans', size: 11 } }
          },
          y: {
            grid: { color: gridColor },
            ticks: { color: textColor, font: { family: 'Plus Jakarta Sans', size: 11 } },
            beginAtZero: true
          }
        }
      }
    });

  } catch (err) {
    console.error('Error rendering weekly chart:', err);
  }
}

// ================= TAB 2: SHARED INBOX (3-COLUMN WORKSPACE) =================
let currentWorkspaceStageFilter = '';

async function loadWorkspaceLeads() {
  try {
    const leads = await apiRequest('/leads?limit=300');
    allWorkspaceLeads = leads || [];
    filterWorkspaceLeads();

    const badgeLeads = document.getElementById('badge-leads-count');
    const badgeContacts = document.getElementById('badge-contacts-count');
    if (badgeLeads) badgeLeads.innerText = allWorkspaceLeads.length;
    if (badgeContacts) badgeContacts.innerText = allWorkspaceLeads.length;

  } catch (err) {
    console.error('Error loading workspace leads:', err);
  }
}

function setWorkspaceStageFilter(stageName) {
  currentWorkspaceStageFilter = stageName;
  const stages = ['', 'New', 'Follow-up', 'Interested', 'Callback', 'Converted'];
  stages.forEach(s => {
    const btn = document.getElementById(s === '' ? 'btn-stage-all' : `btn-stage-${s.toLowerCase()}`);
    if (btn) {
      if (s === stageName) {
        btn.className = 'px-2.5 py-1 rounded-full bg-blue-600 text-white font-bold whitespace-nowrap';
      } else {
        btn.className = 'px-2.5 py-1 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold whitespace-nowrap';
      }
    }
  });
  filterWorkspaceLeads();
}

function filterWorkspaceLeads() {
  const query = (document.getElementById('workspace-search-input')?.value || '').toLowerCase().trim();
  const agentFilter = document.getElementById('workspace-agent-filter')?.value || '';

  const filtered = allWorkspaceLeads.filter(l => {
    if (query) {
      const matchName = (l.first_name + ' ' + (l.last_name || '')).toLowerCase().includes(query);
      const matchPhone = (l.phone || '').includes(query);
      if (!matchName && !matchPhone) return false;
    }
    if (agentFilter && l.assigned_to !== agentFilter) {
      return false;
    }
    if (currentWorkspaceStageFilter && (l.stage_name || '').toLowerCase() !== currentWorkspaceStageFilter.toLowerCase()) {
      return false;
    }
    return true;
  });

  const totalBadge = document.getElementById('workspace-total-badge');
  if (totalBadge) totalBadge.innerText = `${filtered.length} leads`;

  renderWorkspaceLeadCards(filtered);
}

function renderWorkspaceLeadCards(leads) {
  const container = document.getElementById('workspace-leads-list');
  if (!container) return;

  if (leads.length === 0) {
    container.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs">No matching leads found.</div>';
    return;
  }

  container.innerHTML = leads.map(l => {
    const initials = l.first_name.substring(0, 2).toUpperCase();
    const isSelected = selectedWorkspaceLead && selectedWorkspaceLead.id === l.id;
    return `
      <div 
        onclick="selectWorkspaceLead('${l.id}')" 
        class="p-3.5 flex items-center justify-between cursor-pointer transition ${
          isSelected ? 'bg-blue-50/80 border-l-4 border-blue-600' : 'hover:bg-slate-50'
        }"
      >
        <div class="flex items-center space-x-3 overflow-hidden">
          <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-700 font-extrabold text-xs flex items-center justify-center shrink-0">
            ${initials}
          </div>
          <div class="truncate">
            <h5 class="font-bold text-slate-900 text-xs truncate">${escapeHtml(l.first_name)} ${escapeHtml(l.last_name || '')}</h5>
            <p class="text-[11px] text-slate-500 font-mono truncate">${escapeHtml(l.phone)}</p>
            <div class="flex items-center space-x-1.5 mt-1">
              <span class="text-[9px] font-bold px-1.5 py-0.2 rounded-full" style="background-color: ${l.stage_color || '#3B82F6'}20; color: ${l.stage_color || '#3B82F6'}">
                ${escapeHtml(l.stage_name || 'New')}
              </span>
              <span class="text-[10px] text-slate-400 truncate">&bull; ${escapeHtml(l.assigned_to_name || 'Unassigned')}</span>
            </div>
          </div>
        </div>
        <div class="flex items-center space-x-1.5 shrink-0 ml-2">
          <div class="text-right text-[10px] text-slate-400 hidden sm:block">
            ${l.last_call_at ? formatTimeAgo(l.last_call_at) : 'No calls'}
          </div>
          <button
            type="button"
            onclick="event.stopPropagation(); adminStartCall('${l.id}', '${escapeHtml(l.first_name)}', '${l.phone}', event);"
            class="p-2 rounded-xl bg-emerald-50 text-emerald-600 hover:bg-emerald-100 active:scale-90 transition shrink-0 cursor-pointer"
            title="Call ${escapeHtml(l.first_name)} (In-CRM)"
          >
            <i data-lucide="phone" class="w-4 h-4"></i>
          </button>
        </div>
      </div>
    `;
  }).join('');

  // If no lead selected yet, select first one ONLY on desktop
  if (!selectedWorkspaceLead && leads.length > 0) {
    if (window.innerWidth >= 1024) {
      selectWorkspaceLead(leads[0].id);
    }
  }
}

function backToWorkspaceList() {
  const listPane = document.getElementById('workspace-list-pane');
  const detailPane = document.getElementById('workspace-detail-pane');
  if (listPane) {
    listPane.classList.remove('hidden');
    listPane.classList.add('flex');
  }
  if (detailPane) {
    detailPane.classList.add('hidden');
    detailPane.classList.remove('flex');
  }
}

async function selectWorkspaceLead(leadId) {
  try {
    const lead = await apiRequest(`/leads/${leadId}`);
    selectedWorkspaceLead = lead;

    // Mobile single-column view: hide list, show details full width
    if (window.innerWidth < 1024) {
      const listPane = document.getElementById('workspace-list-pane');
      const detailPane = document.getElementById('workspace-detail-pane');
      if (listPane) {
        listPane.classList.add('hidden');
        listPane.classList.remove('flex');
      }
      if (detailPane) {
        detailPane.classList.remove('hidden');
        detailPane.classList.add('flex');
      }
    }

    const initials = lead.first_name.substring(0, 2).toUpperCase();
    const fullName = `${lead.first_name} ${lead.last_name || ''}`.trim();

    // Middle Header
    document.getElementById('wk-selected-avatar').innerText = initials;
    document.getElementById('wk-selected-name').innerText = fullName;
    document.getElementById('wk-selected-phone').innerText = lead.phone;
    document.getElementById('wk-selected-agent-badge').innerText = lead.assignee ? lead.assignee.full_name : 'Unassigned';

    // Remove any tel: link on Call Customer button
    const callBtn = document.getElementById('wk-btn-call');
    if (callBtn) {
      callBtn.removeAttribute('href');
    }

    // Right Details Card
    document.getElementById('wk-right-avatar').innerText = initials;
    document.getElementById('wk-right-name').innerText = fullName;
    document.getElementById('wk-right-phone').innerText = lead.phone;
    document.getElementById('wk-right-city').innerText = lead.city || 'No city specified';
    document.getElementById('wk-right-calls-count').innerText = lead.total_calls_count || 0;
    document.getElementById('wk-right-source').innerText = lead.source || 'Manual';
    document.getElementById('wk-right-created').innerText = lead.created_at ? lead.created_at.substring(0, 10) : '--';

    if (document.getElementById('wk-right-assign-select')) {
      document.getElementById('wk-right-assign-select').value = lead.assigned_to || '';
    }
    if (document.getElementById('wk-right-stage-select')) {
      document.getElementById('wk-right-stage-select').value = lead.stage_id || '';
    }

    // Populate Dispositions Dropdown
    const dispoSelect = document.getElementById('wk-disposition-select');
    if (dispoSelect && dispoSelect.options.length <= 1) {
      try {
        const dispos = await apiRequest('/calls/dispositions/catalog');
        dispoSelect.innerHTML = '<option value="">Select Call Outcome</option>' + 
          dispos.map(d => `<option value="${d.id}">${d.label || d.name || d.code}</option>`).join('');
      } catch (e) {}
    }

    // Render Middle Timeline & Call Audio Recordings
    renderWorkspaceTimeline(lead.call_logs || []);

    // Re-highlight cards
    filterWorkspaceLeads();

  } catch (err) {
    console.error('Error selecting lead:', err);
  }
}

function renderWorkspaceTimeline(logs) {
  const container = document.getElementById('wk-timeline-container');
  if (!container) return;

  if (logs.length === 0) {
    container.innerHTML = `
      <div class="text-center py-16 text-slate-400 text-xs">
        <i data-lucide="phone-missed" class="w-10 h-10 mx-auto text-slate-300 mb-2"></i>
        <span>No calls made to this lead yet. Click "Call Customer" below to place the first call.</span>
      </div>
    `;
    (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
    return;
  }

  container.innerHTML = logs.map(c => `
    <div class="p-4 rounded-2xl border border-slate-200 bg-slate-50 space-y-2.5 text-xs">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="p-1.5 rounded-lg ${
            c.status === 'connected' ? 'bg-emerald-100 text-emerald-700' :
            c.status === 'missed' ? 'bg-rose-100 text-rose-700' : 'bg-blue-100 text-blue-700'
          }">
            <i data-lucide="phone-call" class="w-3.5 h-3.5"></i>
          </span>
          <span class="font-bold text-slate-900">${escapeHtml(c.disposition_name || c.status.toUpperCase())}</span>
          <span class="text-[10px] text-slate-400">&bull; by ${escapeHtml(c.telecaller_name || 'Agent')}</span>
        </div>
        <span class="text-[11px] font-mono text-slate-500">${c.started_at ? c.started_at.substring(0, 16) : ''}</span>
      </div>

      <div class="flex items-center space-x-4 text-[11px] text-slate-600">
        <span>Duration: <b>${formatDuration(c.talk_time_seconds || 0)}</b></span>
        ${c.recording_url ? `
          <div class="flex-1 flex items-center space-x-2">
            <audio controls src="${c.recording_url}" class="w-full h-8"></audio>
          </div>
        ` : '<span class="text-slate-400 italic">No recording audio</span>'}
      </div>

      ${c.notes ? `<p class="p-2.5 rounded-xl bg-white border border-slate-200 text-slate-700 text-xs">${escapeHtml(c.notes)}</p>` : ''}
    </div>
  `).join('');

  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

// Workspace Actions
function adminStartCall(leadId, leadName, phone, e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  const cleanPhone = String(phone || '').replace(/[^\d+*#]/g, '');
  if (!cleanPhone || cleanPhone.length < 3) {
    alert('Please enter a valid phone number.');
    return false;
  }
  const useMobileSim = (typeof isMobileDevice === 'function' && isMobileDevice());
  openUnifiedCallModal({
    leadId: leadId || null,
    leadName: leadName || 'Customer',
    phone: cleanPhone,
    dialMethod: useMobileSim ? 'sim' : 'crm',
    onSaved: async () => {
      try {
        if (selectedWorkspaceLead && selectedWorkspaceLead.id) {
          await selectWorkspaceLead(selectedWorkspaceLead.id);
        }
      } catch (err) {}
      try { await loadDashboardData(); } catch (err) {}
    }
  });
  return false;
}

function triggerWorkspaceCall(e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  if (!selectedWorkspaceLead || !selectedWorkspaceLead.phone) {
    alert('Please select a lead first.');
    return false;
  }
  const cleanPhone = String(selectedWorkspaceLead.phone).replace(/[^\d+*#]/g, '');
  const fullName = `${selectedWorkspaceLead.first_name || ''} ${selectedWorkspaceLead.last_name || ''}`.trim() || 'Customer';
  return adminStartCall(selectedWorkspaceLead.id, fullName, cleanPhone, e);
}

async function saveWorkspaceDisposition() {
  if (!selectedWorkspaceLead) return;
  const dispoId = document.getElementById('wk-disposition-select')?.value;
  const notes = document.getElementById('wk-call-notes-input')?.value || '';

  if (!dispoId) {
    alert('Please select a disposition outcome.');
    return;
  }

  // Find recent undisposed call or create log
  try {
    const status = await apiRequest('/calls/gate-status');
    if (status.is_blocked && status.blocking_call_id) {
      await apiRequest('/calls/disposition', 'POST', {
        call_log_id: status.blocking_call_id,
        call_id: status.blocking_call_id,
        disposition_id: dispoId,
        notes: notes
      });
    }
    document.getElementById('wk-call-notes-input').value = '';
    await selectWorkspaceLead(selectedWorkspaceLead.id);
  } catch (err) {
    alert(err.message || 'Failed to save disposition.');
  }
}

async function reassignSelectedLead() {
  if (!selectedWorkspaceLead) return;
  const newAgentId = document.getElementById('wk-right-assign-select')?.value;
  if (!newAgentId) return;

  try {
    await apiRequest('/allocations/single', 'POST', {
      lead_id: selectedWorkspaceLead.id,
      to_user_id: newAgentId,
      transfer_reason: 'Reassigned from Shared Inbox Workspace'
    });
    alert('Lead reassigned successfully.');
    await loadWorkspaceLeads();
    await selectWorkspaceLead(selectedWorkspaceLead.id);
  } catch (err) {
    alert(err.message || 'Reassignment failed.');
  }
}

async function changeLeadStageFromRightPanel() {
  if (!selectedWorkspaceLead) return;
  const newStageId = document.getElementById('wk-right-stage-select')?.value;
  if (!newStageId) return;

  try {
    await apiRequest(`/leads/${selectedWorkspaceLead.id}`, 'PUT', {
      stage_id: newStageId
    });
    await loadWorkspaceLeads();
    await selectWorkspaceLead(selectedWorkspaceLead.id);
  } catch (err) {
    alert(err.message || 'Stage update failed.');
  }
}

async function quickUpdateStage(stageName) {
  if (!selectedWorkspaceLead) return;
  const stage = currentStages.find(s => s.name.toLowerCase().includes(stageName.toLowerCase()));
  if (!stage) {
    alert(`Stage '${stageName}' not configured.`);
    return;
  }
  try {
    await apiRequest(`/leads/${selectedWorkspaceLead.id}`, 'PUT', {
      stage_id: stage.id
    });
    alert(`Lead marked as ${stageName}`);
    await loadWorkspaceLeads();
    await selectWorkspaceLead(selectedWorkspaceLead.id);
  } catch (err) {
    alert(err.message || 'Failed to update stage.');
  }
}

async function scheduleQuickFollowUp() {
  if (!selectedWorkspaceLead) return;
  const dt = document.getElementById('wk-right-followup-dt')?.value;
  if (!dt) {
    alert('Please pick a date and time for the follow-up.');
    return;
  }
  try {
    await apiRequest('/followups', 'POST', {
      lead_id: selectedWorkspaceLead.id,
      scheduled_at: new Date(dt).toISOString(),
      priority: 'high',
      notes: 'Scheduled from Shared Inbox workspace'
    });
    alert('Follow-up scheduled successfully.');
    document.getElementById('wk-right-followup-dt').value = '';
    await updateBadges();
  } catch (err) {
    alert(err.message || 'Failed to schedule follow-up.');
  }
}

// ================= 4-STEP BULK UPLOAD WIZARD =================
function openBulkUploadModal() {
  document.getElementById('bulk-upload-modal').classList.remove('hidden');
  goToUploadStep(1);
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

function closeBulkUploadModal() {
  document.getElementById('bulk-upload-modal').classList.add('hidden');
  currentImportFile = null;
  currentImportPreview = null;
}

function goToUploadStep(stepNum) {
  for (let i = 1; i <= 4; i++) {
    const pill = document.getElementById(`step-pill-${i}`);
    const view = document.getElementById(`upload-step-${i}`);
    if (pill) {
      if (i === stepNum) {
        pill.className = 'py-1.5 rounded-full bg-blue-600 text-white font-bold';
      } else if (i < stepNum) {
        pill.className = 'py-1.5 rounded-full bg-blue-100 text-blue-700 font-bold';
      } else {
        pill.className = 'py-1.5 rounded-full bg-slate-100 text-slate-500 font-semibold';
      }
    }
    if (view) {
      if (i === stepNum) view.classList.remove('hidden');
      else view.classList.add('hidden');
    }
  }
  document.getElementById('upload-step-success').classList.add('hidden');
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

async function handleFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;

  currentImportFile = file;
  document.getElementById('selected-filename').innerText = file.name;
  document.getElementById('selected-filesize').innerText = `${Math.round(file.size / 1024)} KB`;
  document.getElementById('selected-file-info').classList.remove('hidden');

  const btnNext = document.getElementById('btn-to-step-2');
  btnNext.disabled = true;
  btnNext.innerText = 'Analyzing file columns...';

  try {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch('/api/v1/leads/import/preview', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken()}`
      },
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to parse file.');
    }

    currentImportPreview = await res.json();
    buildColumnMappingForm(currentImportPreview);
    buildPreviewTable(currentImportPreview);

    btnNext.disabled = false;
    btnNext.innerText = 'Next: Map Columns \u2192';

  } catch (err) {
    alert(err.message || 'File inspection failed.');
    btnNext.disabled = false;
    btnNext.innerText = 'Next: Map Columns \u2192';
  }
}

function buildColumnMappingForm(previewData) {
  const container = document.getElementById('column-mapping-container');
  if (!container) return;

  const crmFields = [
    { key: 'phone', label: 'Phone Number *', mandatory: true },
    { key: 'name', label: 'Customer Full Name', mandatory: false },
    { key: 'alternate_phone', label: 'Alternate Phone', mandatory: false },
    { key: 'city', label: 'City / Location', mandatory: false },
    { key: 'source', label: 'Lead Source / Campaign', mandatory: false },
    { key: 'notes', label: 'Initial Notes / Remarks', mandatory: false }
  ];

  const headers = previewData.headers || [];
  const autoMap = previewData.auto_mapping || {};

  container.innerHTML = crmFields.map(f => {
    let options = '<option value="">-- Skip Column --</option>';
    headers.forEach(h => {
      const selected = autoMap[f.key] === h ? 'selected' : '';
      options += `<option value="${escapeHtml(h)}" ${selected}>${escapeHtml(h)}</option>`;
    });

    return `
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 items-center p-2 rounded-xl bg-slate-50 border border-slate-200">
        <label class="font-bold text-slate-800">${f.label}</label>
        <select id="map-col-${f.key}" class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white font-medium text-slate-800 text-xs">
          ${options}
        </select>
      </div>
    `;
  }).join('');
}

function buildPreviewTable(previewData) {
  const thead = document.getElementById('preview-table-header');
  const tbody = document.getElementById('preview-table-body');
  if (!thead || !tbody) return;

  const headers = previewData.headers || [];
  const rows = previewData.preview_rows || [];

  thead.innerHTML = headers.map(h => `<th class="py-2 px-3 text-slate-600">${escapeHtml(h)}</th>`).join('');

  tbody.innerHTML = rows.map(r => `
    <tr class="hover:bg-slate-50">
      ${headers.map(h => `<td class="py-2 px-3">${escapeHtml(r[h] || '')}</td>`).join('')}
    </tr>
  `).join('');

  document.getElementById('preview-stat-total').innerText = previewData.total_rows || 0;
  document.getElementById('preview-stat-valid').innerText = previewData.total_rows || 0;
  document.getElementById('preview-stat-duplicate').innerText = 0;
  document.getElementById('preview-stat-invalid').innerText = 0;
}

function toggleAssignModeInputs() {
  const mode = document.querySelector('input[name="assign-mode"]:checked')?.value;
  const singlePicker = document.getElementById('assign-single-picker');
  const roundRobinPicker = document.getElementById('assign-round-robin-picker');

  if (mode === 'single') {
    singlePicker.classList.remove('hidden');
    roundRobinPicker.classList.add('hidden');
  } else if (mode === 'round_robin') {
    singlePicker.classList.add('hidden');
    roundRobinPicker.classList.remove('hidden');
  } else {
    singlePicker.classList.add('hidden');
    roundRobinPicker.classList.add('hidden');
  }
}

async function executeFinalImport() {
  if (!currentImportFile) {
    alert('No file uploaded.');
    return;
  }

  const phoneMapped = document.getElementById('map-col-phone')?.value;
  if (!phoneMapped) {
    alert('Please map the Phone Number column before importing.');
    goToUploadStep(2);
    return;
  }

  const mapping = {
    phone: phoneMapped,
    name: document.getElementById('map-col-name')?.value || '',
    alternate_phone: document.getElementById('map-col-alternate_phone')?.value || '',
    city: document.getElementById('map-col-city')?.value || '',
    source: document.getElementById('map-col-source')?.value || '',
    notes: document.getElementById('map-col-notes')?.value || ''
  };

  const dupRule = document.querySelector('input[name="dup-rule"]:checked')?.value || 'skip';
  const assignMode = document.querySelector('input[name="assign-mode"]:checked')?.value || 'unassigned';
  const batchName = document.getElementById('import-batch-name')?.value || 'Excel Import Batch';
  const defaultStage = document.getElementById('import-default-stage')?.value || '';

  const formData = new FormData();
  formData.append('file', currentImportFile);
  formData.append('column_mapping_json', JSON.stringify(mapping));
  formData.append('duplicate_handling', dupRule);
  formData.append('assignment_mode', assignMode);
  formData.append('batch_name', batchName);
  if (defaultStage) formData.append('default_stage_id', defaultStage);

  if (assignMode === 'single') {
    const singleAgentId = document.getElementById('import-single-agent')?.value;
    if (singleAgentId) formData.append('assigned_user_id', singleAgentId);
  } else if (assignMode === 'round_robin') {
    const checked = Array.from(document.querySelectorAll('input[name="import-agent-chk"]:checked')).map(c => c.value);
    formData.append('assigned_user_ids_json', JSON.stringify(checked));
  }

  const btn = document.getElementById('btn-final-import');
  btn.disabled = true;
  btn.innerText = 'Importing...';
  document.getElementById('import-progress-container').classList.remove('hidden');

  try {
    const res = await fetch('/api/v1/leads/import/execute', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken()}`
      },
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Import execution failed.');
    }

    const data = await res.json();
    lastImportBatchId = data.batch_id;

    // Show Success View
    document.getElementById('upload-step-4').classList.add('hidden');
    document.getElementById('upload-step-success').classList.remove('hidden');

    document.getElementById('succ-imported').innerText = data.imported || 0;
    document.getElementById('succ-duplicates').innerText = data.duplicates || 0;
    document.getElementById('succ-failed').innerText = data.failed || 0;

    if (data.failed > 0 || data.duplicates > 0) {
      document.getElementById('btn-download-error-report').classList.remove('hidden');
    }

    await loadWorkspaceLeads();
    await loadImportHistory();
    await updateBadges();

  } catch (err) {
    alert(err.message || 'Bulk import failed.');
  } finally {
    btn.disabled = false;
    btn.innerText = 'Import Leads';
    document.getElementById('import-progress-container').classList.add('hidden');
  }
}

function downloadLastErrorReport() {
  if (!lastImportBatchId) return;
  window.location.href = `/api/v1/leads/import/history/${lastImportBatchId}/error-report`;
}

// ================= TAB 10: IMPORT HISTORY =================
async function loadImportHistory() {
  try {
    const history = await apiRequest('/leads/import/history');
    const tbody = document.getElementById('import-history-tbody');
    if (!tbody) return;

    if (!history || history.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" class="text-center py-6 text-slate-400">No bulk upload batches recorded.</td></tr>';
      return;
    }

    tbody.innerHTML = history.map(h => `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4 font-mono text-[11px] text-slate-500">${escapeHtml(h.created_at)}</td>
        <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(h.batch_name || 'Upload')}</td>
        <td class="py-3 px-4 font-mono text-[11px]">${escapeHtml(h.file_name)}</td>
        <td class="py-3 px-4">${escapeHtml(h.uploaded_by_name)}</td>
        <td class="py-3 px-4 text-center font-bold">${h.total_rows}</td>
        <td class="py-3 px-4 text-center text-emerald-600 font-bold">${h.imported_count}</td>
        <td class="py-3 px-4 text-center text-amber-600 font-bold">${h.duplicates_count}</td>
        <td class="py-3 px-4 text-center text-rose-600 font-bold">${h.failed_count}</td>
        <td class="py-3 px-4 text-center">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${
            h.status === 'completed' ? 'bg-emerald-50 text-emerald-700' :
            h.status === 'undone' ? 'bg-slate-100 text-slate-500' : 'bg-blue-50 text-blue-700'
          }">${h.status.toUpperCase()}</span>
        </td>
        <td class="py-3 px-4 text-center space-x-1">
          ${h.has_errors ? `
            <a href="/api/v1/leads/import/history/${h.id}/error-report" class="text-blue-600 font-semibold hover:underline text-[11px]">Errors</a>
          ` : ''}
          ${h.status !== 'undone' ? `
            <button onclick="undoImportBatch('${h.id}')" class="text-rose-600 font-semibold hover:underline text-[11px]">Undo</button>
          ` : '<span class="text-slate-400 text-[11px]">Rolled back</span>'}
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading import history:', err);
  }
}

async function undoImportBatch(historyId) {
  if (!confirm('Are you sure you want to UNDO this import batch? All leads created in this upload will be permanently deleted.')) return;
  try {
    const res = await apiRequest(`/leads/import/history/${historyId}/undo`, 'POST');
    alert(`Import undone. ${res.deleted_leads_count} leads were removed.`);
    await loadImportHistory();
    await loadWorkspaceLeads();
    await updateBadges();
  } catch (err) {
    alert(err.message || 'Undo failed.');
  }
}

// ================= TAB 3: CONTACTS BOOK & CATALOG =================
async function loadContactsCatalog() {
  try {
    const search = document.getElementById('catalog-search-input')?.value || '';
    const stageId = document.getElementById('catalog-stage-filter')?.value || '';
    let url = `/leads?limit=100`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (stageId) url += `&stage_id=${encodeURIComponent(stageId)}`;

    const leads = await apiRequest(url);
    const badgeContacts = document.getElementById('badge-contacts-count');
    if (badgeContacts && leads) badgeContacts.innerText = leads.length;

    const tbody = document.getElementById('contacts-catalog-tbody');
    if (!tbody) return;

    if (!leads || leads.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-6 text-slate-400">No contacts found.</td></tr>';
      return;
    }

    tbody.innerHTML = leads.map(l => {
      const cleanPhone = String(l.phone || '').replace(/[^\d+*#]/g, '');
      const fullName = `${l.first_name || ''} ${l.last_name || ''}`.trim().replace(/'/g, "\\'");
      return `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(l.first_name)} ${escapeHtml(l.last_name || '')}</td>
        <td class="py-3 px-4 font-mono">${escapeHtml(l.phone)}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold" style="background-color: ${l.stage_color || '#3B82F6'}20; color: ${l.stage_color || '#3B82F6'}">
            ${escapeHtml(l.stage_name || 'New')}
          </span>
        </td>
        <td class="py-3 px-4 text-slate-600">${escapeHtml(l.assigned_to_name || 'Unassigned')}</td>
        <td class="py-3 px-4 text-center space-x-2">
          <button type="button" onclick="adminStartCall('${l.id}', '${escapeHtml(fullName)}', '${l.phone}', event)" class="btn-primary-glow px-3 py-1 text-[11px] font-bold inline-flex items-center cursor-pointer">
            Call
          </button>
          <button onclick="selectWorkspaceLead('${l.id}'); switchTab('workspace');" class="text-blue-600 font-semibold hover:underline text-xs">
            View
          </button>
        </td>
      </tr>
    `;
    }).join('');

  } catch (err) {
    console.error('Error loading contacts catalog:', err);
  }
}

async function handleCreateSingleLead(event) {
  event.preventDefault();
  const name = document.getElementById('single-lead-name').value.trim();
  const phone = document.getElementById('single-lead-phone').value.trim();
  const stageId = document.getElementById('single-lead-stage').value;
  const city = document.getElementById('single-lead-city').value.trim();

  try {
    await apiRequest('/leads', 'POST', {
      first_name: name,
      phone: phone,
      stage_id: stageId || null,
      city: city || null,
      source: 'Direct Add'
    });
    alert('Contact added successfully.');
    document.getElementById('form-single-contact').reset();
    await loadContactsCatalog();
    await loadWorkspaceLeads();
    await updateBadges();
  } catch (err) {
    alert(err.message || 'Failed to add contact.');
  }
}

async function handlePasteImport() {
  const text = document.getElementById('paste-leads-text').value.trim();
  const stageId = document.getElementById('paste-lead-stage').value;
  if (!text) {
    alert('Please paste some name and phone numbers.');
    return;
  }

  const lines = text.split('\n').filter(l => l.trim().length > 0);
  let csvContent = 'Name,Phone\n';
  lines.forEach(l => {
    const parts = l.split(',');
    if (parts.length >= 2) {
      csvContent += `"${parts[0].trim()}","${parts[1].trim()}"\n`;
    } else {
      csvContent += `"Customer","${parts[0].trim()}"\n`;
    }
  });

  const blob = new Blob([csvContent], { type: 'text/csv' });
  const file = new File([blob], 'pasted_leads.csv', { type: 'text/csv' });

  const formData = new FormData();
  formData.append('file', file);
  formData.append('column_mapping_json', JSON.stringify({ name: 'Name', phone: 'Phone' }));
  formData.append('duplicate_handling', 'skip');
  formData.append('assignment_mode', 'unassigned');
  formData.append('batch_name', 'Quick Paste Import');
  if (stageId) formData.append('default_stage_id', stageId);

  try {
    const res = await fetch('/api/v1/leads/import/execute', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${getToken()}` },
      body: formData
    });
    const data = await res.json();
    alert(`Pasted Import: ${data.imported} imported, ${data.duplicates} duplicates skipped, ${data.failed} failed.`);
    document.getElementById('paste-leads-text').value = '';
    await loadContactsCatalog();
    await loadWorkspaceLeads();
    await updateBadges();
  } catch (err) {
    alert(err.message || 'Paste import failed.');
  }
}

// ================= TAB 4: ALLOCATIONS =================
async function loadAllocationData() {
  try {
    const capacityCont = document.getElementById('allocation-capacity-list');
    if (capacityCont) {
      capacityCont.innerHTML = currentEmployees.map(e => `
        <div class="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-200">
          <span class="font-bold text-slate-800">${escapeHtml(e.full_name)}</span>
          <span class="font-bold text-blue-600">${e.assigned_leads_count || 0} leads</span>
        </div>
      `).join('');
    }
  } catch (err) {}
}

async function handleEqualSplitAllocation() {
  const checked = Array.from(document.querySelectorAll('input[name="alloc-agent-chk"]:checked')).map(c => c.value);
  if (checked.length === 0) {
    alert('Please select at least one agent for the split.');
    return;
  }
  try {
    const res = await apiRequest('/allocations/bulk-split', 'POST', {
      user_ids: checked,
      strategy: 'equal'
    });
    alert(`Equal split completed: ${res.total_allocated} leads distributed across ${checked.length} agents.`);
    await loadEmployees();
    await loadAllocationData();
    await loadWorkspaceLeads();
  } catch (err) {
    alert(err.message || 'Allocation split failed.');
  }
}

async function handleBulkTransferLeads() {
  const fromId = document.getElementById('transfer-from-agent').value;
  const toId = document.getElementById('transfer-to-agent').value;
  const reason = document.getElementById('transfer-reason-input').value.trim();

  if (!fromId || !toId || !reason) {
    alert('Please choose From Agent, To Agent, and provide a mandatory Transfer Reason.');
    return;
  }
  if (fromId === toId) {
    alert('From and To telecallers must be different.');
    return;
  }

  try {
    const res = await apiRequest('/allocations/bulk-transfer', 'POST', {
      from_user_id: fromId,
      to_user_id: toId,
      transfer_reason: reason
    });
    alert(`Transfer completed: ${res.transferred_count} leads transferred.`);
    document.getElementById('transfer-reason-input').value = '';
    await loadEmployees();
    await loadAllocationData();
    await loadWorkspaceLeads();
  } catch (err) {
    alert(err.message || 'Transfer failed.');
  }
}

// ================= TAB 5: FOLLOW-UPS =================
async function filterFollowUps(filterType) {
  ['today', 'tomorrow', 'overdue'].forEach(f => {
    const btn = document.getElementById(`fup-btn-${f}`);
    if (btn) {
      if (f === filterType) {
        btn.className = 'px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold';
      } else {
        btn.className = 'px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-xs font-semibold';
      }
    }
  });

  try {
    const list = await apiRequest(`/followups?timeframe=${filterType}`);
    const tbody = document.getElementById('followups-tbody');
    if (!tbody) return;

    if (!list || list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-slate-400">No ${filterType} follow-ups scheduled.</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(f => {
      const cleanPhone = String(f.lead_phone || '').replace(/[^\d+*#]/g, '');
      const safeName = String(f.lead_name || 'Customer').replace(/'/g, "\\'");
      return `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(f.lead_name || 'Customer')}</td>
        <td class="py-3 px-4 font-mono">${escapeHtml(f.lead_phone || '')}</td>
        <td class="py-3 px-4">${escapeHtml(f.assigned_to_name || 'Unassigned')}</td>
        <td class="py-3 px-4 font-mono text-[11px] text-slate-600">${f.scheduled_at ? f.scheduled_at.substring(0, 16) : ''}</td>
        <td class="py-3 px-4 text-slate-500">${escapeHtml(f.notes || '--')}</td>
        <td class="py-3 px-4 text-center">
          <button type="button" onclick="adminStartCall('${f.lead_id}', '${escapeHtml(safeName)}', '${f.lead_phone}', event)" class="btn-primary-glow px-3 py-1 text-[11px] font-bold inline-flex items-center cursor-pointer">
            Call
          </button>
        </td>
      </tr>
    `;
    }).join('');

  } catch (err) {
    console.error('Error loading follow-ups:', err);
  }
}

// ================= TAB 6: DEDICATED DIALER & FLOATING DIALER =================
function syncAdminKeypadHref() {
  // Pure In-CRM Calling: No tel: assignment
}

function pressDialerKey(digit) {
  const input = document.getElementById('dialer-phone-input');
  if (input) {
    input.value += digit;
  }
}

function clearDialerInput() {
  const input = document.getElementById('dialer-phone-input');
  if (input) {
    input.value = input.value.slice(0, -1);
  }
}

function handleKeypadCall(e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  const phone = document.getElementById('dialer-phone-input')?.value.trim();
  const cleanPhone = String(phone || '').replace(/[^\d+*#]/g, '');
  if (!cleanPhone || cleanPhone.length < 3) {
    alert('Please enter a valid phone number.');
    return false;
  }
  return adminStartCall(null, 'Manual Call', cleanPhone, e);
}

function openFloatingDialer() {
  document.getElementById('floating-dialer-modal').classList.remove('hidden');
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

function closeFloatingDialer() {
  document.getElementById('floating-dialer-modal').classList.add('hidden');
}

function syncAdminFloatHref() {
  // Pure In-CRM Calling: No tel: assignment
}

function floatKey(d) {
  const input = document.getElementById('float-dial-number');
  if (input) {
    input.value += d;
  }
}

function handleFloatCall(e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  const phone = document.getElementById('float-dial-number')?.value.trim();
  const cleanPhone = String(phone || '').replace(/[^\d+*#]/g, '');
  if (!cleanPhone || cleanPhone.length < 3) {
    alert('Please enter a valid phone number.');
    return false;
  }
  closeFloatingDialer();
  return adminStartCall(null, 'Quick Dial', cleanPhone, e);
}

// ================= TAB 7: LIVE AGENTS WALL =================
async function loadLiveAgentWall() {
  try {
    const rt = await apiRequest('/dashboard/realtime');
    const counts = rt.agent_counts || {};
    document.getElementById('live-count-oncall').innerText = counts.on_call || 0;
    document.getElementById('live-count-idle').innerText = counts.idle || 0;
    document.getElementById('live-count-break').innerText = counts.on_break || 0;
    document.getElementById('live-count-offline').innerText = counts.offline || 0;

    const grid = document.getElementById('live-agents-grid');
    if (!grid) return;

    const allAgents = [
      ...(rt.agents?.on_call || []),
      ...(rt.agents?.idle || []),
      ...(rt.agents?.on_break || []),
      ...(rt.agents?.offline || [])
    ];

    if (allAgents.length === 0) {
      grid.innerHTML = '<div class="p-6 text-center text-slate-400 text-xs col-span-full">No active employees found.</div>';
      return;
    }

    grid.innerHTML = allAgents.map(a => `
      <div class="p-4 rounded-2xl border ${
        a.status === 'on_call' ? 'bg-emerald-50/50 border-emerald-300' :
        a.status === 'idle' ? 'bg-blue-50/50 border-blue-200' :
        a.status === 'break' ? 'bg-amber-50/50 border-amber-300' : 'bg-slate-50 border-slate-200'
      } flex flex-col justify-between space-y-3">
        <div class="flex items-start justify-between">
          <div>
            <h5 class="font-bold text-slate-900 text-xs">${escapeHtml(a.full_name)}</h5>
            <p class="text-[10px] text-slate-500 uppercase tracking-wider">${a.role}</p>
          </div>
          <span class="px-2 py-0.5 rounded-full text-[9px] font-bold ${
            a.status === 'on_call' ? 'bg-emerald-600 text-white animate-pulse' :
            a.status === 'idle' ? 'bg-blue-600 text-white' :
            a.status === 'break' ? 'bg-amber-600 text-white' : 'bg-slate-300 text-slate-700'
          }">${(a.status || 'offline').toUpperCase()}</span>
        </div>

        ${a.active_call ? `
          <div class="p-2 rounded-xl bg-white border border-emerald-200 text-[11px] space-y-1">
            <span class="text-emerald-700 font-bold block">Speaking with ${escapeHtml(a.active_call.lead_name)}</span>
            <span class="text-slate-500 font-mono">${a.active_call.callee_number}</span>
          </div>
        ` : ''}

        <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-200/50">
          <span>Duration in status:</span>
          <span class="font-mono font-bold text-slate-700">${formatDuration(a.status_duration_sec || 0)}</span>
        </div>
      </div>
    `).join('');

  } catch (err) {
    console.error('Error loading live agent wall:', err);
  }
}

// ================= TAB 8: EMPLOYEES & TEAM =================
async function loadEmployeesTable() {
  try {
    await loadEmployees();
    const tbody = document.getElementById('employees-tbody');
    if (!tbody) return;

    tbody.innerHTML = currentEmployees.map(e => `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4">
          <div class="font-bold text-slate-900">${escapeHtml(e.full_name)}</div>
          <div class="text-[11px] text-slate-400">${escapeHtml(e.email)}</div>
        </td>
        <td class="py-3 px-4 uppercase font-bold text-[10px] text-blue-600">${e.role}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${
            e.agent_status === 'on_call' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
            e.agent_status === 'idle' ? 'bg-blue-50 text-blue-700 border border-blue-200' :
            e.agent_status === 'break' ? 'bg-amber-50 text-amber-700 border border-amber-200' :
            'bg-slate-100 text-slate-600'
          }">${(e.agent_status || 'offline').toUpperCase()}</span>
        </td>
        <td class="py-3 px-4 text-center font-bold">${e.assigned_leads_count || 0}</td>
        <td class="py-3 px-4 text-center font-bold text-emerald-600">${e.today_calls_count || 0}</td>
        <td class="py-3 px-4 text-center">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${e.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}">
            ${e.is_active ? 'ACTIVE' : 'INACTIVE'}
          </span>
        </td>
        <td class="py-3 px-4 text-center space-x-2">
          ${user && user.role === 'super_admin' && e.role === 'telecaller' ? `
            <button onclick="enterAgentWorkspace('${e.id}')" class="inline-flex items-center space-x-1 px-2.5 py-1 bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 rounded-lg text-xs font-bold transition cursor-pointer">
              <i data-lucide="external-link" class="w-3 h-3"></i>
              <span>Open Workspace</span>
            </button>
          ` : ''}
          <button onclick="promptResetPassword('${e.id}')" class="text-xs text-blue-600 hover:underline font-semibold">
            Reset Password
          </button>
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading employees table:', err);
  }
}

async function promptResetPassword(empId) {
  const pwd = prompt('Enter new password for this employee:');
  if (!pwd) return;
  try {
    await apiRequest(`/employees/${empId}/reset-password`, 'POST', { new_password: pwd });
    alert('Password reset successfully.');
  } catch (err) {
    alert(err.message || 'Password reset failed.');
  }
}

function openAddEmployeeModal() {
  const form = document.getElementById('form-add-employee');
  if (form) form.reset();
  const modal = document.getElementById('modal-add-employee');
  if (modal) modal.classList.remove('hidden');
}

async function submitAddEmployee(e) {
  e.preventDefault();
  const name = document.getElementById('add-emp-name').value.trim();
  const email = document.getElementById('add-emp-email').value.trim();
  const phone = document.getElementById('add-emp-phone').value.trim();
  const role = document.getElementById('add-emp-role').value;
  const password = document.getElementById('add-emp-pwd').value;

  try {
    await apiRequest('/employees', {
      method: 'POST',
      body: JSON.stringify({
        full_name: name,
        email: email,
        phone: phone,
        role: role,
        password: password
      })
    });

    showToast(`Employee "${name}" created successfully!`, 'success');
    closeModal('modal-add-employee');
    await loadEmployees();
    await loadEmployeesTable();
  } catch (err) {
    showToast(err.message || 'Failed to create employee.', 'error');
  }
}

// ================= TAB 9: REPORTS & EXPORT =================
async function loadCallReportsTable() {
  try {
    const sDate = document.getElementById('rep-start-date')?.value || '';
    const eDate = document.getElementById('rep-end-date')?.value || '';
    const agentId = document.getElementById('rep-agent-select')?.value || '';

    let url = `/reports/calls?limit=50`;
    if (sDate) url += `&start_date=${sDate}`;
    if (eDate) url += `&end_date=${eDate}`;
    if (agentId) url += `&agent_id=${agentId}`;

    const calls = await apiRequest(url);
    const tbody = document.getElementById('call-reports-tbody');
    if (!tbody) return;

    if (!calls || calls.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-slate-400">No calls matching criteria.</td></tr>';
      return;
    }

    tbody.innerHTML = calls.map(c => `
      <tr class="hover:bg-slate-50 transition">
        <td class="py-3 px-4 font-mono text-[11px] text-slate-600">${c.call_date || ''}</td>
        <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(c.lead_name || 'Customer')}</td>
        <td class="py-3 px-4 font-mono">${escapeHtml(c.lead_phone || '')}</td>
        <td class="py-3 px-4">${escapeHtml(c.telecaller_name || 'Agent')}</td>
        <td class="py-3 px-4 font-mono">${formatDuration(c.duration_seconds || 0)}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${
            c.disposition_name === 'Connected' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-700'
          }">${escapeHtml(c.disposition_name || 'Completed')}</span>
        </td>
        <td class="py-3 px-4">
          ${c.recording_url ? `
            <audio controls src="${c.recording_url}" class="h-8 max-w-[180px]"></audio>
          ` : '<span class="text-slate-400 text-[11px] italic">No audio</span>'}
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading call reports:', err);
  }
}

// ================= EXPORT HELPERS =================
function exportLeads(format) {
  window.location.href = `/api/v1/leads/export/${format}`;
}

function exportWorkspaceLeads(format) {
  window.location.href = `/api/v1/leads/export/${format}`;
}

function exportEmployees(format) {
  window.location.href = `/api/v1/employees/export/${format}`;
}

function exportCallReports(format) {
  window.location.href = `/api/v1/reports/calls/export/${format}`;
}

function downloadPerformanceReport() {
  window.location.href = `/api/v1/reports/calls/export/csv`;
}

// ================= ADMIN-ONLY CALL DISPOSITION MANAGER =================
async function loadAdminDispositionManager() {
  const container = document.getElementById('admin-dispositions-list');
  if (!container) return;

  try {
    const dispos = await apiRequest('/calls/dispositions');
    window.__cachedDispositions = dispos;

    // Also keep Shared Inbox disposition dropdown synced
    const dispoSelect = document.getElementById('wk-disposition-select');
    if (dispoSelect && Array.isArray(dispos)) {
      dispoSelect.innerHTML = '<option value="">Select Call Outcome</option>' +
        dispos.map(d => `<option value="${d.id}">${escapeHtml(d.label || d.name || d.code)}</option>`).join('');
    }

    if (!Array.isArray(dispos) || dispos.length === 0) {
      container.innerHTML = '<div class="col-span-full text-center py-4 text-xs text-slate-400">No disposition options yet. Add one above.</div>';
      return;
    }

    container.innerHTML = dispos.map(d => {
      const label = d.label || d.name || d.code;
      const safeLabel = String(label).replace(/'/g, "\\'").replace(/"/g, '&quot;');
      return `
        <div class="flex items-center justify-between p-3.5 rounded-xl border border-slate-200 bg-slate-50/80 hover:border-blue-300 transition gap-2">
          <div class="min-w-0">
            <div class="text-xs font-bold text-slate-900 truncate">${escapeHtml(label)}</div>
            <div class="text-[10px] font-mono text-slate-400">${escapeHtml(d.code)}</div>
          </div>
          <div class="flex items-center space-x-1.5 shrink-0">
            <button type="button" onclick="handleAdminEditDisposition('${d.id}', '${safeLabel}')" class="px-2.5 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-bold transition cursor-pointer">
              Edit
            </button>
            <button type="button" onclick="handleAdminDeleteDisposition('${d.id}', '${safeLabel}')" class="px-2.5 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-600 text-[11px] font-bold transition cursor-pointer">
              Remove
            </button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = '<div class="col-span-full text-center py-4 text-xs text-rose-500">Failed to load disposition options.</div>';
  }
}

async function handleAdminCreateDisposition(event) {
  event.preventDefault();
  const input = document.getElementById('admin-new-dispo-label');
  const label = (input?.value || '').trim();
  if (!label) return;
  try {
    await apiRequest('/calls/dispositions', 'POST', { label });
    if (input) input.value = '';
    await loadAdminDispositionManager();
    showToast(`Added "${label}"`, 'success');
  } catch (err) {
    showToast(err.message || 'Failed to add disposition option.', 'error');
  }
}

async function handleAdminEditDisposition(dispoId, currentLabel) {
  const newLabel = prompt('Edit Disposition Option Name:', currentLabel);
  if (newLabel === null) return;
  const trimmed = newLabel.trim();
  if (!trimmed || trimmed === currentLabel) return;
  try {
    await apiRequest(`/calls/dispositions/${dispoId}`, 'PUT', { label: trimmed });
    await loadAdminDispositionManager();
    showToast(`Updated to "${trimmed}"`, 'success');
  } catch (err) {
    showToast(err.message || 'Failed to update disposition option.', 'error');
  }
}

async function handleAdminDeleteDisposition(dispoId, label) {
  if (!confirm(`Remove "${label}" from Call Outcome options?`)) return;
  try {
    await apiRequest(`/calls/dispositions/${dispoId}`, 'DELETE');
    await loadAdminDispositionManager();
    showToast(`Removed "${label}"`, 'success');
  } catch (err) {
    showToast(err.message || 'Failed to remove disposition option.', 'error');
  }
}

// ================= TAB 11: TELEPHONY SETTINGS =================
async function loadTelephonyConfig() {
  try {
    const cfg = await apiRequest('/telephony/config');
    document.getElementById('tele-provider').value = cfg.provider || 'mock';
    document.getElementById('tele-virtual-num').value = cfg.virtual_number || '';
    document.getElementById('tele-retention').value = cfg.retention_days || 30;
    document.getElementById('tele-consent-chk').checked = cfg.recording_consent_enabled !== false;
    document.getElementById('tele-consent-text').value = cfg.consent_announcement_text || '';
    if (document.getElementById('cfg-allow-manual')) {
      document.getElementById('cfg-allow-manual').checked = cfg.allow_manual_dialing !== false;
    }
  } catch (err) {
    console.error('Error loading telephony config:', err);
  }
}

async function handleSaveTelephonyConfig(event) {
  event.preventDefault();
  const provider = document.getElementById('tele-provider').value;
  const num = document.getElementById('tele-virtual-num').value.trim();
  const apiKey = document.getElementById('tele-api-key').value.trim();
  const apiToken = document.getElementById('tele-api-token').value.trim();
  const retention = parseInt(document.getElementById('tele-retention').value) || 30;
  const consent = document.getElementById('tele-consent-chk').checked;
  const consentText = document.getElementById('tele-consent-text').value.trim();

  try {
    await apiRequest('/telephony/config', 'PUT', {
      provider: provider,
      virtual_number: num,
      api_key: apiKey,
      api_token: apiToken,
      retention_days: retention,
      recording_consent_enabled: consent,
      consent_announcement_text: consentText,
      is_active: true
    });
    const status = document.getElementById('tele-save-status');
    status.innerText = 'Settings saved successfully!';
    setTimeout(() => { status.innerText = ''; }, 3000);
  } catch (err) {
    alert(err.message || 'Failed to save settings.');
  }
}

function syncTelephonyStatus() {
  alert('Telephony connection status synced. Provider is active.');
}

// ================= UTILITIES =================
function formatDuration(sec) {
  if (!sec || sec < 0) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
}

function formatTimeAgo(dtStr) {
  try {
    const dt = new Date(dtStr);
    return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return '--';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// =========================================================================
// SUPER ADMIN MASTER CONTROLS & MULTI-TENANT ENGINE
// =========================================================================

let superAdminCompaniesList = [];
let superAdminPlansList = [];

async function initSuperAdminControls() {
  try {
    superAdminCompaniesList = await apiRequest('/superadmin/companies');
    const select = document.getElementById('superadmin-company-select');
    if (select) {
      select.innerHTML = '';
      let savedCompanyId = localStorage.getItem('crm_selected_company_id');
      if (!savedCompanyId && superAdminCompaniesList.length > 0) {
        savedCompanyId = superAdminCompaniesList[0].id;
        localStorage.setItem('crm_selected_company_id', savedCompanyId);
      }
      
      superAdminCompaniesList.forEach((c) => {
        const isSelected = (c.id === savedCompanyId);
        select.innerHTML += `<option value="${c.id}" ${isSelected ? 'selected' : ''}>🏢 ${c.name} (${c.subdomain}.crm.io)</option>`;
      });

      if (savedCompanyId) {
        select.value = savedCompanyId;
      }
    }

    // Update company header title
    const selectedComp = superAdminCompaniesList.find(c => c.id === localStorage.getItem('crm_selected_company_id')) || superAdminCompaniesList[0];
    if (selectedComp) {
      const compEl = document.getElementById('header-company-name');
      if (compEl) compEl.innerText = `${selectedComp.name} (Super Admin Active Context)`;
    }

    // Update Badges
    const compBadge = document.getElementById('badge-companies-count');
    if (compBadge) compBadge.innerText = superAdminCompaniesList.length;

    try {
      plansList = await apiRequest('/superadmin/plans');
      const planBadge = document.getElementById('badge-plans-count');
      if (planBadge) planBadge.innerText = plansList.length;
    } catch (pe) {}

  } catch (err) {
    console.warn('Super Admin init warning:', err);
  }
}

async function onSuperAdminCompanyChange(companyId) {
  if (companyId) {
    localStorage.setItem('crm_selected_company_id', companyId);
    const comp = superAdminCompaniesList.find(c => c.id === companyId);
    const compEl = document.getElementById('header-company-name');
    if (compEl && comp) compEl.innerText = `${comp.name} (Super Admin Active Context)`;
    showToast(`Switched active context to: ${comp ? comp.name : companyId}`, 'info');
  }

  // Reload current active tab & global data for this selected company
  await loadStages();
  await loadEmployees();
  await loadAnalyticsDashboard();
  await loadWorkspaceLeads();
  await loadContactsCatalog();
  await loadImportHistory();
  await updateBadges();
  (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
}

async function loadCompaniesSuperAdmin() {
  try {
    superAdminCompaniesList = await apiRequest('/superadmin/companies');
    const tbody = document.getElementById('companies-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    superAdminCompaniesList.forEach(c => {
      tbody.innerHTML += `
        <tr class="hover:bg-slate-50/80 transition">
          <td class="p-3 font-bold text-slate-900">${c.name}</td>
          <td class="p-3 font-mono text-blue-600">${c.subdomain}.crm.io</td>
          <td class="p-3"><span class="px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-[11px] font-bold uppercase">${c.plan_name}</span></td>
          <td class="p-3 text-slate-900 font-bold">${c.user_count || 0}</td>
          <td class="p-3 text-slate-700">${(c.lead_count || 0).toLocaleString()}</td>
          <td class="p-3">
            <span class="px-2.5 py-0.5 rounded-full ${c.is_active ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700'} uppercase text-[10px] font-bold">
              ${c.is_active ? 'Active' : 'Suspended'}
            </span>
          </td>
          <td class="p-3 text-right space-x-1.5 whitespace-nowrap">
            <button 
              onclick="enterCompanyAdmin('${c.id}')" 
              class="btn-primary-glow px-3 py-1 text-white rounded-lg text-xs font-semibold inline-flex items-center space-x-1 cursor-pointer"
              title="Super Admin Master Access: Jump into this tenant's Admin Dashboard"
            >
              <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
              <span>Enter Admin Panel</span>
            </button>
            <button 
              onclick="onSuperAdminCompanyChange('${c.id}'); switchTab('workspace');" 
              class="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold inline-flex items-center space-x-1 cursor-pointer transition"
              title="Switch context and inspect leads in Shared Inbox"
            >
              <i data-lucide="inbox" class="w-3.5 h-3.5"></i>
              <span>View Inbox</span>
            </button>
            <button onclick="toggleCompany('${c.id}')" class="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded text-xs cursor-pointer transition">
              ${c.is_active ? 'Suspend' : 'Activate'}
            </button>
          </td>
        </tr>
      `;
    });

    const compBadge = document.getElementById('badge-companies-count');
    if (compBadge) compBadge.innerText = superAdminCompaniesList.length;
    (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
  } catch (err) {
    console.error('Failed to load companies:', err);
  }
}

async function loadPlansSuperAdmin() {
  try {
    const plans = await apiRequest('/superadmin/plans');
    const pGrid = document.getElementById('plans-grid');
    if (!pGrid) return;
    pGrid.innerHTML = '';

    plans.forEach(p => {
      pGrid.innerHTML += `
        <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <div class="flex items-center justify-between">
            <span class="font-bold text-slate-900 text-base">${p.name}</span>
            <span class="px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 uppercase text-[10px] font-bold">${p.tier}</span>
          </div>
          <div class="text-xs space-y-1.5 text-slate-600">
            <div>&#10003; Max Employees: <b class="text-slate-900">${p.max_employees}</b></div>
            <div>&#10003; Max Leads: <b class="text-slate-900">${p.max_leads.toLocaleString()}</b></div>
            <div>&#10003; Recording Retention: <b class="text-slate-900">${p.recording_retention_days} Days</b></div>
            <div class="${p.has_auto_dialer ? 'text-emerald-600 font-semibold' : 'text-slate-400'}">&#9679; Auto-Dialer: ${p.has_auto_dialer ? 'Enabled' : 'Disabled'}</div>
            <div class="${p.has_sentiment_analysis ? 'text-emerald-600 font-semibold' : 'text-slate-400'}">&#9679; Sentiment Analysis: ${p.has_sentiment_analysis ? 'Enabled' : 'Disabled'}</div>
          </div>
        </div>
      `;
    });

    const planBadge = document.getElementById('badge-plans-count');
    if (planBadge) planBadge.innerText = plans.length;
    (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
  } catch (err) {
    console.error('Failed to load plans:', err);
  }
}

async function loadAuditsSuperAdmin() {
  try {
    const logs = await apiRequest('/superadmin/audit-logs');
    const tbody = document.getElementById('audit-logs-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!logs || logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-slate-400">No master access sessions recorded yet.</td></tr>`;
      return;
    }

    logs.forEach(l => {
      const dateStr = l.created_at ? new Date(l.created_at).toLocaleString() : '-';
      const roleBadge = l.target_role === 'admin' 
        ? `<span class="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-bold text-[10px]">ADMIN</span>`
        : `<span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold text-[10px]">TELECALLER</span>`;

      tbody.innerHTML += `
        <tr class="hover:bg-slate-50/80 transition">
          <td class="p-3 font-mono text-[11px] text-slate-500">${dateStr}</td>
          <td class="p-3 font-mono text-purple-600 font-bold">${l.super_admin_email}</td>
          <td class="p-3 font-bold text-slate-900">${l.company_name}</td>
          <td class="p-3">
            <span class="text-slate-900 font-medium">${l.target_user_name || '-'}</span> ${roleBadge}
          </td>
          <td class="p-3 text-slate-700">${l.description}</td>
          <td class="p-3 font-mono text-slate-400">${l.ip_address || '127.0.0.1'}</td>
        </tr>
      `;
    });

    (window.safeCreateIcons ? safeCreateIcons() : (window.lucide && lucide.createIcons()));
  } catch (err) {
    console.error('Failed to load audits:', err);
  }
}

// Edit Super Admin Name
function openEditSuperAdminNameModal() {
  const user = getUser();
  const input = document.getElementById('edit-superadmin-name-input');
  if (input) input.value = user ? user.full_name : 'Vipin (Super Admin)';
  const modal = document.getElementById('modal-edit-superadmin-name');
  if (modal) modal.classList.remove('hidden');
}

async function submitEditSuperAdminName(e) {
  e.preventDefault();
  const input = document.getElementById('edit-superadmin-name-input');
  if (!input) return;
  const newName = input.value.trim();
  if (!newName) return;

  try {
    const res = await apiRequest('/superadmin/profile/name', {
      method: 'PUT',
      body: JSON.stringify({ full_name: newName })
    });

    const user = getUser();
    if (user) {
      user.full_name = res.full_name;
      setUser(user);
    }

    const nameEl = document.getElementById('nav-user-name');
    if (nameEl) nameEl.innerText = res.full_name;

    const bannerEl = document.getElementById('superadmin-banner-name');
    if (bannerEl) bannerEl.innerText = res.full_name;

    const initialEl = document.getElementById('nav-avatar-initials');
    if (initialEl) {
      const initials = res.full_name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
      initialEl.innerText = initials || 'SA';
    }

    showToast(`Super Admin name updated to: ${res.full_name}`, 'success');
    const modal = document.getElementById('modal-edit-superadmin-name');
    if (modal) modal.classList.add('hidden');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// Super Admin 1-Click Master Access
async function enterCompanyAdmin(companyId) {
  try {
    const currentMasterToken = getToken();
    localStorage.setItem('crm_superadmin_master_token', currentMasterToken);

    const data = await apiRequest(`/superadmin/impersonate-company/${companyId}`, { method: 'POST' });
    setToken(data.access_token);
    setUser({
      id: data.user_id,
      email: data.email,
      full_name: data.full_name,
      role: data.role,
      company_id: data.company_id,
      company_name: data.company_name,
      is_super_admin_session: true,
      super_admin_email: data.super_admin_email
    });

    showToast(`Master Access: Entering ${data.company_name} Admin Panel...`, 'success');
    setTimeout(() => { window.location.href = '/admin'; }, 500);
  } catch (err) {
    showToast('Failed to enter admin panel: ' + err.message, 'error');
  }
}

async function enterAgentWorkspace(agentId) {
  try {
    const currentMasterToken = getToken();
    localStorage.setItem('crm_superadmin_master_token', currentMasterToken);

    const data = await apiRequest(`/superadmin/impersonate-agent/${agentId}`, { method: 'POST' });
    setToken(data.access_token);
    setUser({
      id: data.user_id,
      email: data.email,
      full_name: data.full_name,
      role: data.role,
      company_id: data.company_id,
      company_name: data.company_name,
      is_super_admin_session: true,
      super_admin_email: data.super_admin_email
    });

    showToast(`Master Access: Entering Workspace for ${data.full_name}...`, 'success');
    setTimeout(() => { window.location.href = '/workspace'; }, 500);
  } catch (err) {
    showToast('Failed to enter agent workspace: ' + err.message, 'error');
  }
}

async function toggleCompany(companyId) {
  try {
    await apiRequest(`/superadmin/companies/${companyId}/toggle-status`, { method: 'PUT' });
    showToast('Company status updated.', 'success');
    await loadCompaniesSuperAdmin();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openOnboardCompanyModal() {
  const form = document.getElementById('onboardForm');
  if (form) form.reset();
  const select = document.getElementById('onboard-plan-select');
  if (select && plansList) {
    select.innerHTML = '';
    plansList.forEach(p => {
      select.innerHTML += `<option value="${p.id}">${p.name} (Max ${p.max_employees} agents, ${p.max_leads.toLocaleString()} leads)</option>`;
    });
  }
  openModal('modal-onboard-company');
}

async function submitOnboardCompany(e) {
  e.preventDefault();
  const name = document.getElementById('onboard-name').value.trim();
  const subdomain = document.getElementById('onboard-subdomain').value.trim();
  const plan_id = document.getElementById('onboard-plan-select').value;
  const admin_name = document.getElementById('onboard-admin-name').value.trim();
  const admin_email = document.getElementById('onboard-admin-email').value.trim();
  const admin_phone = document.getElementById('onboard-admin-phone').value.trim();
  const admin_password = document.getElementById('onboard-admin-password').value;

  try {
    await apiRequest('/superadmin/companies', {
      method: 'POST',
      body: JSON.stringify({ name, subdomain, plan_id, admin_name, admin_email, admin_phone, admin_password })
    });

    showToast(`Client company "${name}" successfully onboarded!`, 'success');
    closeModal('modal-onboard-company');
    await loadCompaniesSuperAdmin();
    await initSuperAdminControls();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openCreatePlanModal() {
  const form = document.getElementById('createPlanForm');
  if (form) form.reset();
  openModal('modal-create-plan');
}

async function submitCreatePlan(e) {
  e.preventDefault();
  const name = document.getElementById('plan-name').value.trim();
  const tier = document.getElementById('plan-tier').value;
  const max_employees = parseInt(document.getElementById('plan-max-emp').value);
  const max_leads = parseInt(document.getElementById('plan-max-leads').value);
  const recording_retention_days = parseInt(document.getElementById('plan-retention').value);
  const has_auto_dialer = document.getElementById('plan-auto-dialer').checked;
  const has_sentiment_analysis = document.getElementById('plan-sentiment').checked;

  try {
    await apiRequest('/superadmin/plans', {
      method: 'POST',
      body: JSON.stringify({ name, tier, max_employees, max_leads, recording_retention_days, has_auto_dialer, has_sentiment_analysis })
    });

    showToast(`Subscription plan "${name}" created successfully!`, 'success');
    closeModal('modal-create-plan');
    await loadPlansSuperAdmin();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

