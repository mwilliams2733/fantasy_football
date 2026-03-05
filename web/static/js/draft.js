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

function renderTeamResults(teams, userTeamName) {
    const container = document.getElementById("team-results");
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
