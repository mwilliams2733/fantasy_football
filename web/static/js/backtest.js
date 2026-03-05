let backtestSocket = null;

function initBacktestSocket() {
    if (backtestSocket) return;
    backtestSocket = io();

    backtestSocket.on('backtest_status', (data) => {
        document.getElementById('backtest-status').textContent = data.message;
    });

    backtestSocket.on('backtest_complete', (data) => {
        document.getElementById('backtest-status').textContent = 'Complete!';
        document.getElementById('run-backtest-btn').disabled = false;
        document.getElementById('backtest-progress-bar').style.width = '100%';
        renderStrategyComparison(data);
        renderDraftPositionChart(data);
        renderBacktestSummary(data);
    });

    backtestSocket.on('tuner_status', (data) => {
        document.getElementById('tuner-status').textContent = data.message;
        if (data.progress !== undefined) {
            const bar = document.getElementById('tuner-progress-bar');
            bar.style.width = (data.progress * 100) + '%';
        }
    });

    backtestSocket.on('tuner_complete', (data) => {
        document.getElementById('tuner-status').textContent = 'Complete!';
        document.getElementById('run-tuner-btn').disabled = false;
        document.getElementById('tuner-progress-bar').style.width = '100%';
        renderTunerResults(data.results);
    });
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.tab-group .tab').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.remove('hidden');
    event.target.classList.add('active');
}

function runBacktest() {
    initBacktestSocket();
    const seasons = [];
    document.querySelectorAll('.season-checkbox:checked').forEach(cb => {
        seasons.push(parseInt(cb.value));
    });
    if (seasons.length === 0) { alert('Select at least one season'); return; }
    const iterations = parseInt(document.getElementById('backtest-iterations').value) || 100;

    document.getElementById('run-backtest-btn').disabled = true;
    document.getElementById('backtest-status').textContent = 'Starting...';
    document.getElementById('backtest-progress-bar').style.width = '0%';

    backtestSocket.emit('run_backtest', { seasons, iterations });
}

function runTuner() {
    initBacktestSocket();
    const seasons = [];
    document.querySelectorAll('.tuner-season-checkbox:checked').forEach(cb => {
        seasons.push(parseInt(cb.value));
    });
    if (seasons.length === 0) { alert('Select at least one season'); return; }
    const numConfigs = parseInt(document.getElementById('tuner-configs').value) || 50;
    const searchIters = parseInt(document.getElementById('tuner-iterations').value) || 50;

    document.getElementById('run-tuner-btn').disabled = true;
    document.getElementById('tuner-status').textContent = 'Starting...';
    document.getElementById('tuner-progress-bar').style.width = '0%';

    backtestSocket.emit('run_tuner', { seasons, num_configs: numConfigs, search_iterations: searchIters });
}

function renderStrategyComparison(data) {
    const seasons = data.seasons;
    const years = seasons.map(s => String(s.year));

    const traces = [
        { name: 'VBD', x: years, y: seasons.map(s => s.vbd_mean), type: 'bar', marker: { color: '#2ecc71' } },
        { name: 'ADP', x: years, y: seasons.map(s => s.adp_mean), type: 'bar', marker: { color: '#3498db' } },
        { name: 'Random', x: years, y: seasons.map(s => s.random_mean), type: 'bar', marker: { color: '#e74c3c' } },
    ];

    Plotly.newPlot('strategy-comparison-chart', traces, {
        title: 'Strategy Comparison: Mean Points by Season',
        barmode: 'group',
        paper_bgcolor: '#1a1a2e',
        plot_bgcolor: '#16213e',
        font: { color: '#e0e0e0' },
        xaxis: { title: 'Season' },
        yaxis: { title: 'Mean Points' },
    });
}

function renderDraftPositionChart(data) {
    const seasons = data.seasons;
    const z = seasons.map(s => {
        return Array.from({length: 12}, (_, i) => s.by_position[String(i + 1)] || 0);
    });

    Plotly.newPlot('draft-position-chart', [{
        z: z,
        x: Array.from({length: 12}, (_, i) => 'Pick ' + (i + 1)),
        y: seasons.map(s => String(s.year)),
        type: 'heatmap',
        colorscale: 'Viridis',
    }], {
        title: 'VBD Points by Draft Position',
        paper_bgcolor: '#1a1a2e',
        plot_bgcolor: '#16213e',
        font: { color: '#e0e0e0' },
    });
}

function renderBacktestSummary(data) {
    const container = document.getElementById('backtest-summary');
    let html = '';
    data.seasons.forEach(s => {
        html += '<div class="card" style="margin-top: 1rem;">' +
            '<h3>Season ' + s.year + '</h3>' +
            '<p>VBD: <strong>' + s.vbd_mean + '</strong> | ADP: <strong>' + s.adp_mean + '</strong> | Random: <strong>' + s.random_mean + '</strong></p>' +
            '<p>VBD Advantage: <strong>+' + (s.vbd_mean - s.adp_mean).toFixed(1) + '</strong> over ADP</p>' +
            '<p>Bust Rate: ' + s.bust_rate + '% | Hit Rate: ' + s.hit_rate + '%</p>' +
            '</div>';
    });
    container.innerHTML = html;
}

function renderTunerResults(results) {
    const container = document.getElementById('tuner-results');
    let html = '<div class="card"><h3>Top 5 Strategy Configurations</h3>';
    html += '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th>Rank</th><th>Mean Pts</th><th>Need Boost</th><th>Scarcity</th>';
    html += '<th>Rd 1-2</th><th>Rd 3-5</th><th>QB Rd</th><th>TE Rd</th>';
    html += '</tr></thead><tbody>';
    results.forEach(r => {
        html += '<tr>' +
            '<td>' + r.rank + '</td>' +
            '<td><strong>' + r.mean_points + '</strong></td>' +
            '<td>' + r.config.need_boost + '</td>' +
            '<td>' + r.config.scarcity_penalty + '</td>' +
            '<td>' + r.config.round_1_2_bias + '</td>' +
            '<td>' + r.config.round_3_5_bias + '</td>' +
            '<td>' + r.config.qb_target_round + '</td>' +
            '<td>' + r.config.te_target_round + '</td>' +
            '</tr>';
    });
    html += '</tbody></table></div></div>';
    container.innerHTML = html;
}

function loadResultFiles() {
    fetch('/api/backtest/results')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('results-file-list');
            if (data.files.length === 0) {
                container.innerHTML = '<p class="text-secondary">No saved results found. Run a backtest or tuner first.</p>';
                return;
            }
            let html = '<ul style="list-style: none; padding: 0;">';
            data.files.forEach(f => {
                const icon = f.endsWith('.csv') ? '&#128196;' : '&#128203;';
                html += '<li style="padding: 0.4rem 0; border-bottom: 1px solid rgba(15,52,96,0.4);">' +
                    icon + ' ' + f + '</li>';
            });
            html += '</ul>';
            container.innerHTML = html;
        })
        .catch(() => {
            document.getElementById('results-file-list').innerHTML =
                '<p class="text-secondary">Error loading results.</p>';
        });
}
