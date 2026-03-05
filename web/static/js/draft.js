async function runAutoSimDraft() {
    const teamName = document.getElementById("team-name").value || "My Team";
    const draftPos = document.getElementById("draft-position").value;
    const btn = document.getElementById("run-draft-btn");
    const resultsDiv = document.getElementById("draft-results");

    btn.disabled = true;
    btn.textContent = "Drafting...";

    try {
        const data = await postJSON("/api/draft/auto-sim", {
            team_name: teamName,
            draft_position: parseInt(draftPos),
        });
        renderDraftBoard(data.picks);
        renderTeamResults(data.teams, teamName);
        resultsDiv.classList.remove("hidden");
    } catch (err) {
        alert("Draft failed: " + err.message);
    }

    btn.disabled = false;
    btn.textContent = "Run Draft";
}

function renderDraftBoard(picks) {
    const board = document.getElementById("draft-board");
    // Build a 15-round x 12-team grid
    // Get team order from round 1 picks
    const round1 = picks.filter(p => p.round === 1);
    const teamOrder = round1.map(p => p.team);

    let html = '<h2>Draft Board</h2><div class="table-wrapper"><table class="data-table draft-board-table"><thead><tr><th>Rd</th>';
    teamOrder.forEach(t => { html += `<th>${t}</th>`; });
    html += '</tr></thead><tbody>';

    for (let round = 1; round <= 15; round++) {
        html += `<tr><td><strong>${round}</strong></td>`;
        const roundPicks = picks.filter(p => p.round === round);
        // In snake draft, even rounds are reversed
        const ordered = round % 2 === 0 ? [...roundPicks].reverse() : roundPicks;
        ordered.forEach(pick => {
            html += `<td class="draft-cell"><span class="pos-badge pos-${pick.position.toLowerCase()}">${pick.position}</span> ${pick.player}</td>`;
        });
        html += '</tr>';
    }
    html += '</tbody></table></div>';
    board.innerHTML = html;
}

function renderTeamResults(teams, userTeamName, containerId) {
    const container = document.getElementById(containerId || "team-results");
    let html = '<h2>Team Results</h2><div class="card-grid">';

    teams.forEach((team, i) => {
        const isUser = team.name === userTeamName;
        html += `<div class="card team-card ${isUser ? 'user-team' : ''}">`;
        html += `<h3>${isUser ? '⭐ ' : ''}#${i + 1} ${team.name} (Pick ${team.draft_position})</h3>`;
        html += `<p class="big-number">${team.total_points} pts</p>`;
        html += '<table class="data-table compact"><thead><tr><th>Pos</th><th>Player</th><th>Slot</th><th>Pts</th></tr></thead><tbody>';
        team.roster.forEach(e => {
            html += `<tr><td><span class="pos-badge pos-${e.position.toLowerCase()}">${e.position}</span></td>`;
            html += `<td>${e.player}</td><td>${e.slot}</td><td>${e.points}</td></tr>`;
        });
        html += '</tbody></table></div>';
    });

    html += '</div>';
    container.innerHTML = html;
}

/* ==========================================
   Interactive Draft — WebSocket Logic
   ========================================== */

let socket = null;
let draftLog = [];

function startInteractiveDraft() {
    const teamName = document.getElementById("int-team-name").value || "My Team";
    const draftPos = document.getElementById("int-draft-position").value;

    // Connect to SocketIO
    socket = io();

    socket.on("ai_pick", (data) => {
        draftLog.push(data);
        updateDraftLog();
        updateStatus(`Round ${data.round} - AI picking...`);
    });

    socket.on("your_turn", (data) => {
        updateStatus(`Round ${data.round}, Pick ${data.pick} - YOUR TURN!`);
        showAvailablePlayers(data.available);
        showRecommendations(data.recommendations);
        showMyRoster(data.roster);
        document.getElementById("pick-controls").classList.remove("hidden");
    });

    socket.on("pick_confirmed", (data) => {
        draftLog.push({...data, team: teamName});
        updateDraftLog();
        document.getElementById("pick-controls").classList.add("hidden");
        updateStatus("Waiting for other teams...");
    });

    socket.on("draft_complete", (data) => {
        renderTeamResults(data.teams, teamName, "int-team-results");
        document.getElementById("interactive-results").classList.remove("hidden");
        document.getElementById("pick-controls").classList.add("hidden");
        updateStatus("Draft Complete!");
        socket.disconnect();
    });

    socket.on("error", (data) => {
        alert(data.message);
    });

    // Hide setup, show draft UI
    document.getElementById("int-setup").classList.add("hidden");
    document.getElementById("int-draft-ui").classList.remove("hidden");

    socket.emit("start_draft", {
        team_name: teamName, draft_position: parseInt(draftPos)
    });
}

function pickPlayer(playerName) {
    socket.emit("user_pick", {player_name: playerName});
}

function updateStatus(text) {
    const el = document.getElementById("draft-status");
    el.textContent = text;
    if (text.includes("YOUR TURN")) {
        el.classList.add("your-turn");
    } else {
        el.classList.remove("your-turn");
    }
}

function showAvailablePlayers(players) {
    const container = document.getElementById("available-players");
    let html = '<input type="text" placeholder="Search players..." onkeyup="filterTable(\'avail-table\', this.value)" class="search-input">';
    html += '<div class="position-filter-mini">';
    ["ALL","QB","RB","WR","TE","K","DEF"].forEach(pos => {
        html += `<button onclick="filterAvailableByPos('${pos}')" class="btn-small">${pos}</button>`;
    });
    html += '</div>';
    html += '<div class="table-wrapper"><table class="data-table compact" id="avail-table"><thead><tr>';
    html += '<th>Pos</th><th>Name</th><th data-sort="pts" data-type="number">Pts</th>';
    html += '<th data-sort="vbd" data-type="number">VBD</th><th>Action</th></tr></thead><tbody>';
    players.forEach(p => {
        html += `<tr data-position="${p.position}">`;
        html += `<td><span class="pos-badge pos-${p.position.toLowerCase()}">${p.position}</span></td>`;
        html += `<td data-col="name">${p.name}</td>`;
        html += `<td data-col="pts">${p.points}</td>`;
        html += `<td data-col="vbd">${p.vbd}</td>`;
        html += `<td><button class="btn-primary btn-small" onclick="pickPlayer('${p.name.replace(/'/g, "\\'")}')">Pick</button></td>`;
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    container.innerHTML = html;
    makeSortable("avail-table");
}

function filterAvailableByPos(pos) {
    const rows = document.querySelectorAll("#avail-table tbody tr");
    rows.forEach(row => {
        row.style.display = (pos === "ALL" || row.dataset.position === pos) ? "" : "none";
    });
}

function showRecommendations(recs) {
    const container = document.getElementById("recommendations");
    let html = '<h3>Recommended Picks</h3>';
    recs.slice(0, 5).forEach((p, i) => {
        html += `<div class="rec-item" onclick="pickPlayer('${p.name.replace(/'/g, "\\'")}')">`;
        html += `<span class="rec-rank">#${i + 1}</span>`;
        html += `<span class="pos-badge pos-${p.position.toLowerCase()}">${p.position}</span>`;
        html += `<span class="rec-name">${p.name}</span>`;
        html += `<span class="rec-pts">${p.vbd} VBD</span>`;
        html += '</div>';
    });
    container.innerHTML = html;
}

function showMyRoster(roster) {
    const container = document.getElementById("my-roster");
    let html = '<h3>My Roster</h3>';
    if (roster.length === 0) {
        html += '<p class="text-secondary">No players drafted yet</p>';
    } else {
        html += '<table class="data-table compact"><tbody>';
        roster.forEach(e => {
            html += `<tr><td><span class="pos-badge pos-${e.position.toLowerCase()}">${e.position}</span></td>`;
            html += `<td>${e.player}</td><td>${e.slot}</td></tr>`;
        });
        html += '</tbody></table>';
    }
    container.innerHTML = html;
}

function updateDraftLog() {
    const container = document.getElementById("draft-log");
    let html = '<h3>Draft Log</h3><div class="draft-log-entries">';
    // Show last 20 picks
    const recent = draftLog.slice(-20).reverse();
    recent.forEach(p => {
        html += `<div class="log-entry">`;
        html += `<span class="log-pick">R${p.round} P${p.pick}</span>`;
        html += `<span class="log-team">${p.team}</span>`;
        html += `<span class="pos-badge pos-${p.position.toLowerCase()}">${p.position}</span>`;
        html += `<span>${p.player}</span>`;
        html += '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
}
