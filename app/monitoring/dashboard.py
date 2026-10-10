"""Lightweight local dashboard for monitoring."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from flask import Flask, jsonify, render_template_string, request

from app.monitoring.store import MonitoringStore, get_store


# HTML Templates
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Agent Monitoring Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; line-height: 1.6; }
        header { background: #16213e; padding: 1rem 2rem; border-bottom: 1px solid #0f3460; display: flex; justify-content: space-between; align-items: center; }
        header h1 { font-size: 1.5rem; color: #e94560; }
        .status-badge { padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
        .status-running { background: #0f3460; color: #4ade80; }
        .status-stopped { background: #0f3460; color: #f87171; }
        main { padding: 2rem; max-width: 1400px; margin: 0 auto; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
        .card { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 1.5rem; }
        .card h2 { font-size: 1rem; color: #e94560; margin-bottom: 1rem; border-bottom: 1px solid #0f3460; padding-bottom: 0.5rem; }
        .metric { display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #888; }
        .metric-value { font-weight: 600; }
        .metric-value.success { color: #4ade80; }
        .metric-value.warning { color: #fbbf24; }
        .metric-value.error { color: #f87171; }
        .table-container { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); }
        th { color: #e94560; font-weight: 600; background: rgba(233, 69, 96, 0.1); }
        tr:hover { background: rgba(255,255,255,0.02); }
        .badge { padding: 0.125rem 0.5rem; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
        .badge-healthy { background: #064e3b; color: #4ade80; }
        .badge-degraded { background: #78350f; color: #fbbf24; }
        .badge-unavailable { background: #7f1d1d; color: #f87171; }
        .badge-success { background: #064e3b; color: #4ade80; }
        .badge-failure { background: #7f1d1d; color: #f87171; }
        .controls { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
        .controls select, .controls input { padding: 0.5rem; border: 1px solid #0f3460; background: #1a1a2e; color: #eee; border-radius: 4px; }
        .section { margin-bottom: 2rem; }
        .empty-state { text-align: center; color: #666; padding: 3rem; }
        .refresh-btn { background: #e94560; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #d63a55; }
        @media (max-width: 768px) {
            header { flex-direction: column; gap: 0.5rem; text-align: center; }
            main { padding: 1rem; }
        }
    </style>
</head>
<body>
    <header>
        <h1>🤖 AI Agent Monitoring Dashboard</h1>
        <div>
            <span class="status-badge status-running">● Live</span>
            <button class="refresh-btn" onclick="location.reload()">Refresh</button>
        </div>
    </header>
    <main>
        <div class="controls">
            <select id="timeRange" onchange="loadDashboard()">
                <option value="1h">Last Hour</option>
                <option value="24h" selected>Last 24 Hours</option>
                <option value="7d">Last 7 Days</option>
                <option value="30d">Last 30 Days</option>
            </select>
            <input type="text" id="taskFilter" placeholder="Filter by Task ID" onchange="loadDashboard()">
        </div>

        <section class="grid" id="overview">
            <div class="card">
                <h2>Overview</h2>
                <div class="metric"><span class="metric-label">Total Events</span><span class="metric-value" id="totalEvents">-</span></div>
                <div class="metric"><span class="metric-label">Events (Last Hour)</span><span class="metric-value" id="eventsLastHour">-</span></div>
                <div class="metric"><span class="metric-label">Unique Tasks</span><span class="metric-value" id="uniqueTasks">-</span></div>
                <div class="metric"><span class="metric-label">Task Success Rate</span><span class="metric-value" id="taskSuccessRate">-</span></div>
                <div class="metric"><span class="metric-label">Avg Task Duration</span><span class="metric-value" id="avgTaskDuration">-</span></div>
                <div class="metric"><span class="metric-label">Permission Approval Rate</span><span class="metric-value" id="permApprovalRate">-</span></div>
            </div>
            <div class="card">
                <h2>Provider Health</h2>
                <div class="table-container">
                    <table>
                        <thead><tr><th>Provider</th><th>Status</th><th>Success Rate</th><th>Requests</th></tr></thead>
                        <tbody id="providerHealth"></tbody>
                    </table>
                </div>
            </div>
        </section>

        <section class="grid">
            <div class="card">
                <h2>Provider Metrics</h2>
                <div class="table-container">
                    <table>
                        <thead><tr><th>Provider</th><th>Requests</th><th>Successes</th><th>Failures</th><th>Success Rate</th><th>Avg Latency</th></tr></thead>
                        <tbody id="providerMetrics"></tbody>
                    </table>
                </div>
            </div>
            <div class="card">
                <h2>Tool Metrics</h2>
                <div class="table-container">
                    <table>
                        <thead><tr><th>Tool</th><th>Invocations</th><th>Successes</th><th>Failures</th><th>Failure Rate</th><th>Avg Latency</th></tr></thead>
                        <tbody id="toolMetrics"></tbody>
                    </table>
                </div>
            </div>
        </section>

        <section class="grid">
            <div class="card">
                <h2>Permission Metrics</h2>
                <div class="metric"><span class="metric-label">Requested</span><span class="metric-value" id="permRequested">-</span></div>
                <div class="metric"><span class="metric-label">Granted</span><span class="metric-value success" id="permGranted">-</span></div>
                <div class="metric"><span class="metric-label">Denied</span><span class="metric-value error" id="permDenied">-</span></div>
            </div>
            <div class="card">
                <h2>Task Metrics</h2>
                <div class="metric"><span class="metric-label">Started</span><span class="metric-value" id="tasksStarted">-</span></div>
                <div class="metric"><span class="metric-label">Completed</span><span class="metric-value success" id="tasksCompleted">-</span></div>
                <div class="metric"><span class="metric-label">Failed</span><span class="metric-value error" id="tasksFailed">-</span></div>
                <div class="metric"><span class="metric-label">Avg Iterations</span><span class="metric-value" id="avgIterations">-</span></div>
                <div class="metric"><span class="metric-label">Local Model Fallbacks</span><span class="metric-value warning" id="localFallbacks">-</span></div>
            </div>
        </section>

        <section>
            <div class="card">
                <h2>Recent Events</h2>
                <div class="table-container">
                    <table>
                        <thead><tr><th>Time</th><th>Type</th><th>Task</th><th>Provider/Tool</th><th>Duration</th><th>Status</th></tr></thead>
                        <tbody id="recentEvents"></tbody>
                    </table>
                </div>
            </div>
        </section>
    </main>

    <script>
        async function loadDashboard() {
            const timeRange = document.getElementById('timeRange').value;
            const taskFilter = document.getElementById('taskFilter').value;
            const params = new URLSearchParams({ range: timeRange });
            if (taskFilter) params.append('task_id', taskFilter);

            try {
                const [overview, providers, tools, perms, tasks, events] = await Promise.all([
                    fetch(`/api/overview?${params}`).then(r => r.json()),
                    fetch(`/api/providers?${params}`).then(r => r.json()),
                    fetch(`/api/tools?${params}`).then(r => r.json()),
                    fetch(`/api/permissions?${params}`).then(r => r.json()),
                    fetch(`/api/tasks?${params}`).then(r => r.json()),
                    fetch(`/api/events?${params}&limit=50`).then(r => r.json()),
                ]);

                renderOverview(overview);
                renderProviders(providers);
                renderTools(tools);
                renderPermissions(perms);
                renderTasks(tasks);
                renderEvents(events);
            } catch (e) {
                console.error('Failed to load dashboard:', e);
            }
        }

        function renderOverview(data) {
            document.getElementById('totalEvents').textContent = data.total_events || 0;
            document.getElementById('eventsLastHour').textContent = data.events_last_hour || 0;
            document.getElementById('uniqueTasks').textContent = data.unique_tasks || 0;
            document.getElementById('taskSuccessRate').textContent = `${(data.task_success_rate * 100).toFixed(1)}%`;
            document.getElementById('avgTaskDuration').textContent = `${(data.average_task_duration_ms || 0).toFixed(0)}ms`;
            document.getElementById('permApprovalRate').textContent = `${(data.permission_approval_rate * 100).toFixed(1)}%`;

            const providerHealth = data.provider_health || {};
            const tbody = document.getElementById('providerHealth');
            tbody.innerHTML = Object.entries(providerHealth).map(([provider, health]) => `
                <tr>
                    <td>${provider}</td>
                    <td><span class="badge badge-${health.status}">${health.status}</span></td>
                    <td>${(health.success_rate * 100).toFixed(1)}%</td>
                    <td>${health.requests}</td>
                </tr>
            `).join('') || '<tr><td colspan="4">No provider data</td></tr>';
        }

        function renderProviders(data) {
            const tbody = document.getElementById('providerMetrics');
            tbody.innerHTML = Object.entries(data).filter(([k]) => !k.startsWith('_')).map(([provider, stats]) => `
                <tr>
                    <td>${provider}</td>
                    <td>${stats.requests}</td>
                    <td class="success">${stats.successes}</td>
                    <td class="error">${stats.failures}</td>
                    <td>${(stats.success_rate * 100).toFixed(1)}%</td>
                    <td>${stats.average_latency_ms?.toFixed(0) || 0}ms</td>
                </tr>
            `).join('') || '<tr><td colspan="6">No provider data</td></tr>';
        }

        function renderTools(data) {
            const tbody = document.getElementById('toolMetrics');
            tbody.innerHTML = Object.entries(data).map(([tool, stats]) => `
                <tr>
                    <td>${tool}</td>
                    <td>${stats.invocations}</td>
                    <td class="success">${stats.successes}</td>
                    <td class="error">${stats.failures}</td>
                    <td>${(stats.failure_rate * 100).toFixed(1)}%</td>
                    <td>${stats.average_latency_ms?.toFixed(0) || 0}ms</td>
                </tr>
            `).join('') || '<tr><td colspan="6">No tool data</td></tr>';
        }

        function renderPermissions(data) {
            document.getElementById('permRequested').textContent = data.requested || 0;
            document.getElementById('permGranted').textContent = data.granted || 0;
            document.getElementById('permDenied').textContent = data.denied || 0;
        }

        function renderTasks(data) {
            document.getElementById('tasksStarted').textContent = data.total_started || 0;
            document.getElementById('tasksCompleted').textContent = data.completed || 0;
            document.getElementById('tasksFailed').textContent = data.failed || 0;
            document.getElementById('avgIterations').textContent = data.average_iterations?.toFixed(1) || 0;
            document.getElementById('localFallbacks').textContent = data.local_model_fallbacks || 0;
        }

        function renderEvents(events) {
            const tbody = document.getElementById('recentEvents');
            tbody.innerHTML = events.map(e => `
                <tr>
                    <td>${new Date(e.timestamp).toLocaleTimeString()}</td>
                    <td>${e.event_type.replace(/_/g, ' ')}</td>
                    <td>${e.task_id?.slice(0, 8) || '-'}</td>
                    <td>${e.provider || e.tool || '-'}</td>
                    <td>${e.duration_ms?.toFixed(0) || '-'}ms</td>
                    <td><span class="badge ${e.success ? 'badge-success' : 'badge-failure'}">${e.success ? '✓' : '✗'}</span></td>
                </tr>
            `).join('') || '<tr><td colspan="6">No events</td></tr>';
        }

        // Initial load
        loadDashboard();

        // Auto-refresh every 30 seconds
        setInterval(loadDashboard, 30000);
    </script>
</body>
</html>
"""


def create_dashboard_app(store: Optional[MonitoringStore] = None) -> Flask:
    """Create the Flask dashboard application."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(INDEX_HTML)

    @app.route("/api/overview")
    def api_overview():
        store_instance = store or get_store()
        return jsonify(store_instance.get_overview())

    @app.route("/api/providers")
    def api_providers():
        store_instance = store or get_store()
        range_param = request.args.get("range", "24h")
        start_time = _parse_time_range(range_param)
        task_id = request.args.get("task_id")
        return jsonify(store_instance.get_provider_stats(start_time=start_time))

    @app.route("/api/tools")
    def api_tools():
        store_instance = store or get_store()
        range_param = request.args.get("range", "24h")
        start_time = _parse_time_range(range_param)
        return jsonify(store_instance.get_tool_stats(start_time=start_time))

    @app.route("/api/permissions")
    def api_permissions():
        store_instance = store or get_store()
        range_param = request.args.get("range", "24h")
        start_time = _parse_time_range(range_param)
        return jsonify(store_instance.get_permission_stats(start_time=start_time))

    @app.route("/api/tasks")
    def api_tasks():
        store_instance = store or get_store()
        range_param = request.args.get("range", "24h")
        start_time = _parse_time_range(range_param)
        return jsonify(store_instance.get_task_stats(start_time=start_time))

    @app.route("/api/events")
    def api_events():
        store_instance = store or get_store()
        range_param = request.args.get("range", "24h")
        start_time = _parse_time_range(range_param)
        task_id = request.args.get("task_id")
        event_type = request.args.get("event_type")
        limit = int(request.args.get("limit", 100))
        return jsonify([e.to_dict() for e in store_instance.query_events(
            start_time=start_time,
            task_id=task_id,
            event_type=event_type,
            limit=limit,
        )])

    @app.route("/api/health")
    def api_health():
        return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"})

    return app


def _parse_time_range(range_str: str) -> Optional[datetime]:
    """Parse time range string to datetime."""
    now = datetime.utcnow()
    if range_str == "1h":
        return now - timedelta(hours=1)
    elif range_str == "24h":
        return now - timedelta(days=1)
    elif range_str == "7d":
        return now - timedelta(days=7)
    elif range_str == "30d":
        return now - timedelta(days=30)
    return None


def run_dashboard(
    host: str = "127.0.0.1",
    port: int = 8080,
    db_path: Optional[str] = None,
    debug: bool = False,
) -> None:
    """Run the dashboard server."""
    if db_path:
        store = MonitoringStore(db_path=db_path)
    else:
        store = get_store()

    app = create_dashboard_app(store)
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard()