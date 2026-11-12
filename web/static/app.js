let currentTab = "current";
let ws = null;
let lastData = null;
let selectedStrike = null;
let selectedChurnCombo = "500/200";
let lastHeaderTab = null;
let lastHeaderCombosKey = "";

// Feed mode preference: stored in localStorage so it survives page reloads
// and works on stateless serverless (Vercel) where server-side state resets each request.
let forcedSimMode = localStorage.getItem("butterfly_feed_mode") === "sim";

function changeChurnCombo(combo) {
  if (!combo) return;
  selectedChurnCombo = combo;

  syncHeaderActiveStates();

  const labelEl = document.getElementById("churn-banner-label");
  if (labelEl) {
    labelEl.innerHTML = `<strong>Live Churning Tracker (${selectedChurnCombo}):</strong>`;
  }

  if (lastData) {
    updateChurnLeaderboard(lastData);
    renderTable(lastData);
  }
}

function syncHeaderActiveStates() {
  const sel = document.getElementById("churn-combo-select");
  if (sel && sel.value !== selectedChurnCombo) {
    sel.value = selectedChurnCombo;
  }

  document.querySelectorAll(".combo-clickable-header").forEach(th => {
    const c = th.getAttribute("data-combo");
    th.classList.toggle("active-combo-header", c === selectedChurnCombo);
  });

  document.querySelectorAll(".churn-quick-pill").forEach(pill => {
    const c = pill.getAttribute("data-combo");
    pill.classList.toggle("active", c === selectedChurnCombo);
  });
}

function renderQuickPills(combos) {
  const container = document.getElementById("churn-quick-pills");
  if (!container) return;

  let pillsHtml = "";
  combos.forEach(c => {
    const isActive = (c === selectedChurnCombo);
    pillsHtml += `
      <button class="churn-quick-pill ${isActive ? 'active' : ''}" 
              data-combo="${c}" 
              onclick="changeChurnCombo('${c}')" 
              title="Switch Churning column to ${c}">
        ${c}
      </button>
    `;
  });
  container.innerHTML = pillsHtml;
}

function renderHeader(combos) {
  const thead = document.getElementById("matrix-thead");
  const combosKey = combos.join(",");

  if (lastHeaderTab === currentTab && lastHeaderCombosKey === combosKey && thead.children.length > 0 && thead.querySelector(".churn-header-col")) {
    syncHeaderActiveStates();
    return;
  }

  lastHeaderTab = currentTab;
  lastHeaderCombosKey = combosKey;

  let topHeaderHtml = `<tr><th rowspan="2" class="strike-col">Strike</th>`;
  let subHeaderHtml = `<tr>`;

  combos.forEach(combo => {
    const isActive = (combo === selectedChurnCombo);
    topHeaderHtml += `
      <th colspan="2" class="group-header combo-clickable-header ${isActive ? 'active-combo-header' : ''}" 
          data-combo="${combo}" 
          onclick="changeChurnCombo('${combo}')" 
          title="Click to switch Churning to ${combo}">
        ${combo}
      </th>
    `;
    subHeaderHtml += `<th>BCmp</th><th>SCmp</th>`;
  });

  if (currentTab === "current") {
    topHeaderHtml += `<th rowspan="2" class="straddle-header-col">Straddle</th>`;
  }

  // Churning column header is shown for BOTH Current and Next Expiries
  const optionsHtml = combos.map(c => `<option value="${c}" ${c === selectedChurnCombo ? 'selected' : ''}>${c}</option>`).join("");
  topHeaderHtml += `
    <th class="group-header churn-header-col">
      Churning
      <select id="churn-combo-select" class="churn-combo-select" onchange="changeChurnCombo(this.value)" onclick="event.stopPropagation()">
        ${optionsHtml}
      </select>
    </th>
  `;
  subHeaderHtml += `<th class="churn-sub-col">Count &bull; Range</th>`;

  topHeaderHtml += `</tr>`;
  subHeaderHtml += `</tr>`;
  thead.innerHTML = topHeaderHtml + subHeaderHtml;

  renderQuickPills(combos);
  syncHeaderActiveStates();
}

function selectStrike(strike) {
  if (selectedStrike === strike) {
    selectedStrike = null;
  } else {
    selectedStrike = strike;
  }
  if (lastData) {
    renderTable(lastData);
  }
}

let wsRetryCount = 0;
let httpPollingInterval = null;

function startHttpPolling() {
  if (httpPollingInterval) return;
  console.log("WebSocket unavailable, falling back to HTTP polling...");
  const poll = async () => {
    try {
      // Pass ?mode=sim when user has manually chosen simulator via Switch Mode
      const modeParam = forcedSimMode ? "?mode=sim" : "";
      const res = await fetch(`/api/matrix-state${modeParam}`);
      if (res.ok) {
        const data = await res.json();
        lastData = data;
        updateDashboard(data);
      }
    } catch (e) {
      console.warn("Polling error:", e);
    }
  };
  poll();
  httpPollingInterval = setInterval(poll, 1000);
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  try {
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
  } catch (e) {
    startHttpPolling();
    return;
  }

  ws.onopen = () => {
    wsRetryCount = 0;
    if (httpPollingInterval) {
      clearInterval(httpPollingInterval);
      httpPollingInterval = null;
    }
    const st = document.getElementById("ws-status");
    if (st) {
      st.textContent = "Connected (Live)";
      st.style.color = "#10b981";
    }
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    lastData = data;
    updateDashboard(data);
  };

  ws.onclose = () => {
    wsRetryCount++;
    if (wsRetryCount >= 2) {
      startHttpPolling();
    } else {
      setTimeout(connectWebSocket, 1500);
    }
  };

  ws.onerror = () => {
    ws.close();
  };
}

function switchTab(tab) {
  currentTab = tab;
  document.getElementById("tab-current").classList.toggle("active", tab === "current");
  document.getElementById("tab-next").classList.toggle("active", tab === "next");
  lastHeaderTab = null;

  if (lastData) {
    const combos = (tab === "current") ? lastData.combos_current : lastData.combos_next;
    if (combos && combos.length > 0 && !combos.includes(selectedChurnCombo)) {
      selectedChurnCombo = (tab === "current") ? "500/200" : combos[0];
      const labelEl = document.getElementById("churn-banner-label");
      if (labelEl) {
        labelEl.innerHTML = `<strong>Live Churning Tracker (${selectedChurnCombo}):</strong>`;
      }
    }
    updateChurnLeaderboard(lastData);
    renderTable(lastData);
  }
}

function updateChurnLeaderboard(data) {
  const churnContainer = document.getElementById("churn-items-container");
  if (!churnContainer) return;

  const items = (data.churn_leaderboards && data.churn_leaderboards[selectedChurnCombo])
    ? data.churn_leaderboards[selectedChurnCombo]
    : (data.churn_leaderboard || []);

  let chipsHtml = "";
  items.forEach(item => {
    if (item.churn_count > 0 || item.price_range > 0 || (item.max_price && item.max_price > 0)) {
      const dirSymbol = item.current_direction === "UP" ? "▲" : (item.current_direction === "DOWN" ? "▼" : "");
      const dirClass = item.current_direction === "UP" ? "dir-up" : "dir-down";
      chipsHtml += `
        <div class="churn-chip" onclick="openChurnModal(${item.strike}, '${selectedChurnCombo}')" title="Click to view full churn log for strike ${item.strike} (${selectedChurnCombo})">
          <strong>Strike ${item.strike}</strong>
          <span class="churn-count-badge">${item.churn_count} Churns</span>
          <span class="churn-range-text">[${item.min_price} ⇄ ${item.max_price}]</span>
          <span style="font-size: 0.75rem; color: #94a3b8;">(Δ ${item.price_range})</span>
          <span class="${dirClass}">${dirSymbol}</span>
        </div>
      `;
    }
  });

  churnContainer.innerHTML = chipsHtml || `<span class="churn-empty">Tracking live round-trip swings across strikes for ${selectedChurnCombo}...</span>`;
}

function updateDashboard(data) {
  // Update Spot
  if (data.spot) {
    const spotEl = document.getElementById("spot-price");
    const formattedSpot = data.spot.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (spotEl.textContent !== formattedSpot) {
      spotEl.textContent = formattedSpot;
      spotEl.classList.remove("flash-spot");
      void spotEl.offsetWidth;
      spotEl.classList.add("flash-spot");
    }
  }

  // Update Feed Badge and Status
  const badge = document.getElementById("feed-badge");
  const wsStatus = document.getElementById("ws-status");
  const mktBanner = document.getElementById("market-closed-banner");

  if (data.feed_mode && badge) {
    badge.textContent = data.feed_mode;
    if (data.feed_mode.includes("Upstox Live")) {
      badge.className = "badge badge-live";

      // Check IST market hours (Mon-Fri 09:15 - 15:30 IST)
      const now = new Date();
      const istTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (5.5 * 3600 * 1000));
      const hours = istTime.getHours();
      const mins = istTime.getMinutes();
      const isWeekday = istTime.getDay() >= 1 && istTime.getDay() <= 5;
      const isMarketOpen = isWeekday && ((hours > 9 || (hours === 9 && mins >= 15)) && (hours < 15 || (hours === 15 && mins <= 30)));

      if (!isMarketOpen) {
        if (wsStatus) {
          wsStatus.textContent = "Market Closed (No Live Ticks)";
          wsStatus.style.color = "#f59e0b";
        }
        if (mktBanner) mktBanner.style.display = "flex";
      } else {
        if (wsStatus) {
          wsStatus.textContent = "Upstox Live (Active)";
          wsStatus.style.color = "#10b981";
        }
        if (mktBanner) mktBanner.style.display = "none";
      }
    } else {
      badge.className = "badge badge-sim";
      if (wsStatus) {
        wsStatus.textContent = "Simulator (Active)";
        wsStatus.style.color = "#38bdf8";
      }
      if (mktBanner) mktBanner.style.display = "none";
    }
  }

  // Update Auth / Fallback Banner
  const authBanner = document.getElementById("auth-alert-banner");
  if (authBanner) {
    if (data.auth_error) {
      authBanner.style.display = "flex";
      const msgEl = document.getElementById("auth-alert-msg");
      if (msgEl) msgEl.textContent = data.auth_error;
    } else {
      authBanner.style.display = "none";
    }
  }

  // Update ATM Strike
  if (data.atm_strike) {
    const atmEl = document.getElementById("atm-strike");
    const formattedAtm = data.atm_strike.toLocaleString();
    if (atmEl.textContent !== formattedAtm) {
      atmEl.textContent = formattedAtm;
      atmEl.classList.remove("flash-spot");
      void atmEl.offsetWidth;
      atmEl.classList.add("flash-spot");
    }
  }

  // Update Live Churn Leaderboard
  updateChurnLeaderboard(data);

  renderTable(data);
}

function renderTable(data) {
  const combos = currentTab === "current" ? data.combos_current : data.combos_next;
  const rows = currentTab === "current" ? data.current : data.next;

  renderHeader(combos);

  const tbody = document.getElementById("matrix-tbody");
  let bodyHtml = "";
  rows.forEach(row => {
    const strike = row["Strike"];
    const isAtm = !!row["is_atm"];
    const isSelected = (selectedStrike !== null && Number(strike) === Number(selectedStrike));
    const offset = row["offset_from_atm"];
    const offsetBadge = isAtm ? '<span class="atm-badge">ATM</span>' : (offset !== undefined ? `<span class="offset-badge">${offset > 0 ? '+' : ''}${offset}</span>` : '');

    let rowClass = "";
    if (isAtm && isSelected) {
      rowClass = "atm-row selected-row";
    } else if (isAtm) {
      rowClass = "atm-row";
    } else if (isSelected) {
      rowClass = "selected-row";
    }

    bodyHtml += `<tr class="${rowClass}">
      <td class="strike-col ${isAtm ? 'atm-strike-col' : ''} ${isSelected ? 'selected-strike-col' : ''}" onclick="selectStrike(${strike})" title="Click to highlight strike ${strike}">
        ${strike} ${offsetBadge}
      </td>`;

    combos.forEach(combo => {
      const bcmp = row[`${combo}_BCmp`];
      const scmp = row[`${combo}_SCmp`];
      const isPeak = !!row[`${combo}_SCmp_Peak`];
      const scmpMax = row[`${combo}_SCmp_Max`];
      const scmpMin = row[`${combo}_SCmp_Min`];

      const bcmpStr = (typeof bcmp === "number") ? bcmp.toFixed(2) : (bcmp || "-");
      const scmpStr = (typeof scmp === "number") ? scmp.toFixed(2) : (scmp || "-");

      const [gap, wing] = combo.split(" ")[0].split("/").map(Number);
      const peakClass = isPeak ? "scmp-cell scmp-peak-alert" : "scmp-cell";
      const scmpTitle = isPeak
        ? `SCMP AT HIGH LEVEL / SELL SIGNAL: CMP (${scmpStr}) is at peak resistance [Range: ${scmpMin} - ${scmpMax}]! Optimal Sell / Credit zone.`
        : `Click to inspect 6-leg strategy (SCmp: ${scmpStr})`;

      bodyHtml += `
        <td class="bcmp-cell" onclick="openStrategyModal(${strike}, ${gap}, ${wing})">${bcmpStr}</td>
        <td class="${peakClass}" onclick="openStrategyModal(${strike}, ${gap}, ${wing})" title="${scmpTitle}">${scmpStr}</td>
      `;
    });

    if (currentTab === "current") {
      const strd = row["Straddle"];
      const strdStr = (typeof strd === "number") ? strd.toFixed(2) : (strd || "-");

      bodyHtml += `
        <td class="straddle-cell">${strdStr}</td>
      `;
    }

    // Churn column cell for selectedChurnCombo (shown for BOTH current and next expiries)
    const cCount = row[`${selectedChurnCombo}_churn_count`] ?? row["churn_count"] ?? 0;
    const cRange = row[`${selectedChurnCombo}_churn_range`] ?? row["churn_range"] ?? 0;
    const cMin = typeof row[`${selectedChurnCombo}_churn_min`] === "number" ? row[`${selectedChurnCombo}_churn_min`] : (typeof row["churn_min"] === "number" ? row["churn_min"] : 0);
    const cMax = typeof row[`${selectedChurnCombo}_churn_max`] === "number" ? row[`${selectedChurnCombo}_churn_max`] : (typeof row["churn_max"] === "number" ? row["churn_max"] : 0);
    const cPhase = row[`${selectedChurnCombo}_churn_phase`] || row["churn_phase"] || "INITIALIZING";

    let phaseBadge = '<span class="churn-phase-pill phase-idle">-</span>';
    if (cPhase === "AT_HIGH") {
      phaseBadge = '<span class="churn-phase-pill phase-high">▲AT HIGH</span>';
    } else if (cPhase === "DROPPING_TO_LOW") {
      phaseBadge = '<span class="churn-phase-pill phase-dropping">▼TO LOW</span>';
    } else if (cPhase === "AT_LOW") {
      phaseBadge = '<span class="churn-phase-pill phase-low">●HIT LOW</span>';
    }

    let churnCellContent = '<span style="color: #475569; font-size: 0.75rem;">-</span>';
    if (cCount > 0 || cRange > 0 || cMax > 0) {
      const minStr = cMin.toFixed(2);
      const maxStr = cMax.toFixed(2);
      churnCellContent = `
        <div class="churn-cell-layout">
          <span class="churn-count-badge" title="${cCount} Completed Churns (Highest to Lowest Level)">${cCount}x</span>
          <span class="churn-range-text">${minStr} ⇄ ${maxStr}</span>
          ${phaseBadge}
        </div>
      `;
    }

    bodyHtml += `
      <td class="churn-table-col" onclick="openChurnModal(${strike}, '${selectedChurnCombo}')" title="Click to view completed churn log for strike ${strike} (${selectedChurnCombo})">
        ${churnCellContent}
      </td>
    `;

    bodyHtml += `</tr>`;
  });

  tbody.innerHTML = bodyHtml;
}

async function openStrategyModal(center, gap, wing) {
  selectedStrike = center;
  if (lastData) {
    renderTable(lastData);
  }
  document.getElementById("modal-center").value = center;
  document.getElementById("modal-gap").value = gap;
  document.getElementById("modal-wing").value = wing;

  try {
    const res = await fetch(`/api/strategy-details?center=${center}&gap=${gap}&wing=${wing}&expiry=${currentTab}`);
    const data = await res.json();

    document.getElementById("modal-bcmp").textContent = (data.bcmp !== null) ? data.bcmp.toFixed(2) : "-";
    document.getElementById("modal-scmp").textContent = (data.scmp !== null) ? data.scmp.toFixed(2) : "-";
    document.getElementById("modal-spread").textContent = (data.spread !== null) ? data.spread.toFixed(2) : "-";

    const legsTbody = document.getElementById("modal-legs-tbody");
    let legsHtml = "";

    data.legs.forEach(leg => {
      const actionBadge = leg.action === "BUY" ? '<span class="badge-buy">BUY</span>' : '<span class="badge-sell">SELL</span>';
      const bidCheckbox = leg.is_bidding ? '<input type="checkbox" checked disabled>' : '<input type="checkbox" disabled>';

      legsHtml += `
        <tr>
          <td>${leg.leg_number}</td>
          <td>${leg.option_type}</td>
          <td>${leg.expiry}</td>
          <td style="font-weight: 700;">${leg.strike}</td>
          <td>${actionBadge}</td>
          <td>${leg.ratio}</td>
          <td style="color: #f43f5e; font-weight: 600;">${leg.bid.toFixed(2)}</td>
          <td style="color: #10b981; font-weight: 600;">${leg.ask.toFixed(2)}</td>
          <td>${leg.ltp.toFixed(2)}</td>
          <td style="text-align: center;">${bidCheckbox}</td>
        </tr>
      `;
    });

    legsTbody.innerHTML = legsHtml;

    // Detailed formula explanation
    if (data.legs.length === 6) {
      const l = data.legs;
      document.getElementById("formula-bcmp").textContent = 
        `BCmp = -(Ask(${l[0].option_type} ${l[0].strike}) - 2*Bid(${l[1].option_type} ${l[1].strike}) + Ask(${l[2].option_type} ${l[2].strike}) + Ask(${l[3].option_type} ${l[3].strike}) - 2*Bid(${l[4].option_type} ${l[4].strike}) + Ask(${l[5].option_type} ${l[5].strike}))\n` +
        `     = -(${l[0].ask.toFixed(2)} - 2*${l[1].bid.toFixed(2)} + ${l[2].ask.toFixed(2)} + ${l[3].ask.toFixed(2)} - 2*${l[4].bid.toFixed(2)} + ${l[5].ask.toFixed(2)}) = ${data.bcmp ? data.bcmp.toFixed(2) : '-'}`;

      document.getElementById("formula-scmp").textContent = 
        `SCmp = +(Bid(${l[0].option_type} ${l[0].strike}) - 2*Ask(${l[1].option_type} ${l[1].strike}) + Bid(${l[2].option_type} ${l[2].strike}) + Bid(${l[3].option_type} ${l[3].strike}) - 2*Ask(${l[4].option_type} ${l[4].strike}) + Bid(${l[5].option_type} ${l[5].strike}))\n` +
        `     = +(${l[0].bid.toFixed(2)} - 2*${l[1].ask.toFixed(2)} + ${l[2].bid.toFixed(2)} + ${l[3].bid.toFixed(2)} - 2*${l[4].ask.toFixed(2)} + ${l[5].bid.toFixed(2)}) = ${data.scmp ? data.scmp.toFixed(2) : '-'}`;
    }

    document.getElementById("strategy-modal").style.display = "flex";
  } catch (err) {
    console.error("Failed to load strategy details:", err);
  }
}

async function openChurnModal(strike, combo = selectedChurnCombo) {
  selectedStrike = strike;
  if (lastData) renderTable(lastData);

  document.getElementById("churn-modal-subtitle").textContent = `(Strike: ${strike} | Combo: ${combo})`;
  try {
    const res = await fetch(`/api/strike-swings?strike=${strike}&combo=${combo}`);
    const data = await res.json();

    document.getElementById("cm-cycles").textContent = `${data.churn_count || 0} Churns`;
    document.getElementById("cm-high").textContent = `${(data.max_price || 0).toFixed(2)}`;
    document.getElementById("cm-low").textContent = `${(data.min_price || 0).toFixed(2)}`;
    document.getElementById("cm-range").textContent = `${(data.price_range || 0).toFixed(2)} pts`;

    const tbody = document.getElementById("churn-modal-tbody");
    let html = "";
    if (data.completed_churns && data.completed_churns.length > 0) {
      data.completed_churns.slice().reverse().forEach(c => {
        html += `
          <tr>
            <td style="font-weight: 700; color: #fbbf24;">Churn #${c.churn_id}</td>
            <td style="color: #94a3b8; font-family: monospace;">${c.time}</td>
            <td style="font-weight: 700; font-family: monospace; color: #10b981;">${c.from_level.toFixed(2)}</td>
            <td style="font-weight: 700; font-family: monospace; color: #f43f5e;">${c.to_level.toFixed(2)}</td>
            <td style="color: #38bdf8; font-weight: 700; font-family: monospace;">${c.points.toFixed(2)} pts</td>
            <td><span class="badge" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-size: 0.72rem; padding: 2px 6px; border-radius: 3px; font-weight: 700;">ONE CHURN COMPLETE</span></td>
          </tr>
        `;
      });
    } else {
      const curPhase = data.current_phase || "BUILDING_RANGE";
      html = `<tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 24px; line-height: 1.6;">
        <div style="font-size: 0.95rem; margin-bottom: 6px;">Live Channel: <strong style="color: #10b981;">Highest: ${(data.max_price || 0).toFixed(2)}</strong> &bull; <strong style="color: #f43f5e;">Lowest: ${(data.min_price || 0).toFixed(2)}</strong></div>
        Current Phase: <strong style="color: #fbbf24;">${curPhase}</strong><br>
        <span style="font-size: 0.8rem; color: #64748b;">A churn completes when price rises to the Highest Level CMP and then drops down to hit the Lowest Level CMP.</span>
      </td></tr>`;
    }
    tbody.innerHTML = html;
    document.getElementById("churn-modal").style.display = "flex";
  } catch (err) {
    console.error("Failed to load churn swings:", err);
  }
}

function closeModal() {
  const modal = document.getElementById("strategy-modal");
  if (modal) modal.style.display = "none";
}

function closeChurnModal() {
  const modal = document.getElementById("churn-modal");
  if (modal) modal.style.display = "none";
}

// Close modals on Escape key press
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal();
    closeChurnModal();
  }
});

async function toggleFeedMode() {
  // On Vercel (serverless), each request is a fresh Lambda — there's no persistent global state.
  // So we store the mode preference in localStorage and pass it as a query param on each poll.
  forcedSimMode = !forcedSimMode;
  localStorage.setItem("butterfly_feed_mode", forcedSimMode ? "sim" : "live");

  // Update the button text immediately so the user sees feedback
  const btn = document.getElementById("btn-toggle-feed");
  if (btn) {
    btn.textContent = forcedSimMode ? "Switch to Live" : "Switch Mode";
    btn.style.background = forcedSimMode ? "#2563eb" : "";
  }

  // Also try to inform the server (works on localhost; no-op on Vercel stateless)
  const targetMode = forcedSimMode ? "sim" : "upstox";
  try {
    const res = await fetch(`/api/switch-feed?mode=${targetMode}`, { method: "POST" });
    const result = await res.json();
    if (result.auth_error && targetMode === "upstox") {
      alert(result.auth_error);
      // Revert if upstox failed
      forcedSimMode = true;
      localStorage.setItem("butterfly_feed_mode", "sim");
      if (btn) { btn.textContent = "Switch to Live"; btn.style.background = "#2563eb"; }
    }
  } catch (err) {
    // On Vercel, POST may also work per-request — that's fine
    console.log("Feed switch (stateless ok):", err.message);
  }

  // Restart polling immediately with new mode
  if (httpPollingInterval) {
    clearInterval(httpPollingInterval);
    httpPollingInterval = null;
  }
  startHttpPolling();
}

// Close modals on backdrop click
window.addEventListener("DOMContentLoaded", () => {
  // Restore Switch Mode button label from localStorage on page load
  const btn = document.getElementById("btn-toggle-feed");
  if (btn && forcedSimMode) {
    btn.textContent = "Switch to Live";
    btn.style.background = "#2563eb";
  }

  connectWebSocket();
  
  const stratModal = document.getElementById("strategy-modal");
  if (stratModal) {
    stratModal.addEventListener("click", (e) => {
      if (e.target === stratModal) closeModal();
    });
  }

  const churnModal = document.getElementById("churn-modal");
  if (churnModal) {
    churnModal.addEventListener("click", (e) => {
      if (e.target === churnModal) closeChurnModal();
    });
  }
});
