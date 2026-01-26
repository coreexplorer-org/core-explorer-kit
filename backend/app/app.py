import socket
import threading
import uuid
from datetime import datetime
from functools import wraps
from flask import Flask, request, make_response, redirect, url_for
from flask_graphql import GraphQLView

from git_processor import process_git_data
from neo4j_driver import Neo4jDriver
from schema import schema

app = Flask(__name__)

# --- tiny CORS helper (stand-alone) -------------------------
def allow_all_origins(view_fn):
    @wraps(view_fn)
    def _wrapped(*args, **kwargs):
        # Pre-flight request
        if request.method == "OPTIONS":
            resp = make_response()
        else:
            resp = make_response(view_fn(*args, **kwargs))

        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        return resp
    return _wrapped
# ------------------------------------------------------------

@app.route("/api/")
def hello():
    html = (
        "<h3>Hello Fullstack!</h3>"
        "<b>Hostname:</b> {hostname}<br/>"
    )
    return html.format(hostname=socket.gethostname())


@app.route("/api/initiate_data_ingest/", methods=["GET", "POST"])
def initiate_data_ingest():
    db = Neo4jDriver()
    try:
        # Check for active ingest runs
        active_runs = db.get_active_ingest_runs()
        
        warning_html = ""
        if active_runs:
            warning_html = "<div style='background-color: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin: 10px 0; border-radius: 4px;'>"
            warning_html += "<strong>⚠ Warning:</strong> There are already active ingest runs:<ul>"
            for run in active_runs:
                run_pulled_at = run.get('pulledAt', 'Unknown')
                if hasattr(run_pulled_at, 'strftime'):
                    run_pulled_at = run_pulled_at.strftime("%Y-%m-%d %H:%M:%S")
                warning_html += f"<li><a href='/api/ingest_status/{run['id']}/'>{run['id'][:8]}...</a> - Status: {run['status']} (Started: {run_pulled_at})</li>"
            warning_html += "</ul>"
            warning_html += "<p>Concurrent runs are allowed but may consume significant resources. Consider waiting for active runs to complete.</p>"
            warning_html += "</div>"
        
        # If POST request, start the processing
        if request.method == "POST":
            # Generate a unique ID for this run
            run_id = str(uuid.uuid4())
            
            # Launch processing in a background thread
            thread = threading.Thread(
                target=process_git_data, 
                kwargs={"use_new_schema": True, "run_id": run_id}
            )
            thread.daemon = True  # Ensure thread closes if app does
            thread.start()

            # Return styled feedback with a link to check status
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Ingestion Started - {run_id[:8]}</title>
    <meta http-equiv="refresh" content="2;url=/api/ingest_status/{run_id}/">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 700px;
            margin: 40px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h3 {{
            margin-top: 0;
            color: #333;
        }}
        .success-box {{
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }}
        .run-id {{
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            font-family: monospace;
            margin: 15px 0;
        }}
        .status-link {{
            display: inline-block;
            background-color: #007bff;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 4px;
            font-weight: bold;
            margin: 20px 0;
        }}
        .status-link:hover {{
            background-color: #0056b3;
        }}
        .info-text {{
            color: #666;
            font-size: 0.9em;
            margin: 15px 0;
        }}
        .redirect-notice {{
            background-color: #e7f3ff;
            border-left: 4px solid #007bff;
            padding: 10px;
            margin: 20px 0;
            border-radius: 4px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h3>Ingestion Started</h3>
        {warning_html}
        <div class="success-box">
            <strong>✓ Ingest process has been started in the background</strong>
        </div>
        <div class="run-id">
            <strong>Run ID:</strong> {run_id}
        </div>
        <div class="redirect-notice">
            <p>Redirecting to status page in 2 seconds...</p>
        </div>
        <a href="/api/ingest_status/{run_id}/" class="status-link">View Status Page →</a>
        <p class="info-text">
            <strong>Note:</strong> Total ingest job time for large repositories can take 1hr+ or more on slower machines. 
            The status page will update as processing progresses.
        </p>
        <hr/>
        <p><small><b>Hostname:</b> {socket.gethostname()}</small></p>
    </div>
</body>
</html>
            """
            return html
        
        # GET request - show the button/form
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Start Git Data Ingest</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 700px;
            margin: 40px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h3 {{
            margin-top: 0;
            color: #333;
        }}
        .start-button {{
            background-color: #007bff;
            color: white;
            border: none;
            padding: 15px 30px;
            font-size: 16px;
            font-weight: bold;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            margin: 20px 0;
        }}
        .start-button:hover {{
            background-color: #0056b3;
        }}
        .start-button:active {{
            background-color: #004085;
        }}
        form {{
            margin: 20px 0;
        }}
        .info-box {{
            background-color: #e7f3ff;
            border-left: 4px solid #007bff;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h3>Start Git Data Ingest</h3>
        {warning_html}
        <div class="info-box">
            <p><strong>What this does:</strong></p>
            <ul>
                <li>Processes commits from the Git repository</li>
                <li>Extracts PGP signatures</li>
                <li>Computes merge relationships</li>
                <li>Tracks file changes for sensitive paths</li>
            </ul>
            <p><strong>Note:</strong> Initial ingest of large repositories can take 10+ minutes or more on slower machines.</p>
        </div>
        <form method="POST" action="/api/initiate_data_ingest/">
            <button type="submit" class="start-button">Start Ingest Process</button>
        </form>
        <p><small><b>Hostname:</b> {socket.gethostname()}</small></p>
    </div>
</body>
</html>
        """
        return html
    finally:
        db.close()


@app.route("/api/ingest_status/<run_id>/")
@allow_all_origins
def ingest_status(run_id):
    db = Neo4jDriver()
    try:
        try:
            status_info = db.get_ingest_run_status(run_id)
        except Exception as e:
            # If there's an error querying (e.g., node was deleted), treat as not found
            status_info = None
        
        if not status_info:
            # Redirect to initiate page if ingest run not found
            # Use immediate redirect with a fallback HTML page
            return redirect('/api/initiate_data_ingest/', code=302)
        
        # Helper to convert Neo4j datetime to Python datetime (naive)
        def to_python_datetime(dt):
            """Convert Neo4j DateTime or string to Python datetime (naive)."""
            if dt is None:
                return None
            if isinstance(dt, datetime):
                # If it's timezone-aware, convert to naive (UTC)
                if dt.tzinfo is not None:
                    return dt.replace(tzinfo=None)
                return dt
            if isinstance(dt, str):
                parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                # Convert to naive if timezone-aware
                if parsed.tzinfo is not None:
                    return parsed.replace(tzinfo=None)
                return parsed
            # Handle Neo4j DateTime objects (neo4j.time.DateTime)
            try:
                # Try to_native() method first (most common)
                if hasattr(dt, 'to_native'):
                    native = dt.to_native()
                    # Ensure it's naive
                    if isinstance(native, datetime) and native.tzinfo is not None:
                        return native.replace(tzinfo=None)
                    return native
                # Fallback: construct from attributes
                if hasattr(dt, 'year') and hasattr(dt, 'month') and hasattr(dt, 'day'):
                    microsecond = 0
                    if hasattr(dt, 'nanosecond'):
                        microsecond = dt.nanosecond // 1000
                    elif hasattr(dt, 'microsecond'):
                        microsecond = dt.microsecond
                    return datetime(
                        dt.year, dt.month, dt.day,
                        dt.hour if hasattr(dt, 'hour') else 0,
                        dt.minute if hasattr(dt, 'minute') else 0,
                        dt.second if hasattr(dt, 'second') else 0,
                        microsecond
                    )
            except Exception as e:
                # If conversion fails, try string representation
                try:
                    parsed = datetime.fromisoformat(str(dt).replace('Z', '+00:00'))
                    if parsed.tzinfo is not None:
                        return parsed.replace(tzinfo=None)
                    return parsed
                except:
                    pass
            return None
        
        # Calculate elapsed time
        started_at_raw = status_info.get('pulledAt')
        last_progress_raw = status_info.get('lastProgressAt', started_at_raw)
        elapsed_seconds = 0
        elapsed_str = "0s"
        
        started_at = to_python_datetime(started_at_raw)
        last_progress = to_python_datetime(last_progress_raw)
        
        if started_at and last_progress:
            elapsed = (last_progress - started_at).total_seconds()
            elapsed_seconds = int(elapsed)
            
            if elapsed < 60:
                elapsed_str = f"{int(elapsed)}s"
            elif elapsed < 3600:
                elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
            else:
                hours = int(elapsed // 3600)
                minutes = int((elapsed % 3600) // 60)
                elapsed_str = f"{hours}h {minutes}m"
        
        # Format timestamps
        started_str = started_at.strftime("%Y-%m-%d %H:%M:%S") if started_at else "Unknown"
        last_update_str = last_progress.strftime("%Y-%m-%d %H:%M:%S") if last_progress else "Unknown"
        
        # Get Cypher suggestions based on stage
        cypher_suggestions = get_cypher_suggestions(status_info.get('status', ''), status_info)
        
        # Status-specific messaging
        status_msg = ""
        if status_info['status'] == 'ENRICHING':
            status_msg = "<p style='color: #0c5460; background-color: #d1ecf1; padding: 10px; border-radius: 4px;'><strong>Enrichment in progress:</strong> Processing signatures, merges, and file changes. This step can take several minutes for large repositories.</p>"
        elif status_info['status'] == 'COMPLETED':
            status_msg = "<p style='color: #155724; background-color: #d4edda; padding: 10px; border-radius: 4px;'><strong>✓ Ingest completed successfully!</strong></p>"
        elif status_info['status'] == 'COMMITS_COMPLETE':
            status_msg = "<p style='color: #856404; background-color: #fff3cd; padding: 10px; border-radius: 4px;'><strong>Commit backbone complete.</strong> Proceeding with enrichment stages...</p>"
        
        # Only auto-refresh if not completed
        auto_refresh_tag = "" if status_info['status'] == 'COMPLETED' else '<meta http-equiv="refresh" content="5">'
        refresh_message = "" if status_info['status'] == 'COMPLETED' else '<p><small><span class="refresh-indicator"></span>Auto-refreshing every 5 seconds. <a href="">Refresh manually</a></small></p>'
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Ingest Status - {run_id[:8]}</title>
    {auto_refresh_tag}
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 900px;
            margin: 20px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h3 {{
            margin-top: 0;
            color: #333;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: bold;
            font-size: 0.9em;
        }}
        .status-STARTED {{ background-color: #cce5ff; color: #004085; }}
        .status-COMMITS_COMPLETE {{ background-color: #fff3cd; color: #856404; }}
        .status-ENRICHING {{ background-color: #d1ecf1; color: #0c5460; }}
        .status-COMPLETED {{ background-color: #d4edda; color: #155724; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-box {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            border-left: 4px solid #007bff;
        }}
        .stat-label {{
            font-size: 0.85em;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-value {{
            font-size: 1.5em;
            font-weight: bold;
            color: #333;
            margin-top: 5px;
        }}
        .cypher-section {{
            margin-top: 30px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 4px;
            border-left: 4px solid #28a745;
        }}
        .cypher-query {{
            background-color: #282c34;
            color: #abb2bf;
            padding: 12px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            margin: 10px 0;
            overflow-x: auto;
        }}
        .refresh-indicator {{
            display: inline-block;
            width: 12px;
            height: 12px;
            background-color: #28a745;
            border-radius: 50%;
            animation: pulse 2s infinite;
            margin-right: 8px;
        }}
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
            100% {{ opacity: 1; }}
        }}
        hr {{
            border: none;
            border-top: 1px solid #ddd;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h3 style="margin: 0;">Ingest Run Status</h3>
            <a href="/api/initiate_data_ingest/" style="color: #007bff; text-decoration: none; font-size: 0.9em;">← Start New Ingest</a>
        </div>
        <p><b>ID:</b> <code>{run_id}</code></p>
        <p><b>Status:</b> <span class="status-badge status-{status_info['status']}">{status_info['status']}</span></p>
        {status_msg}
        
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-label">Total Elapsed Time</div>
                <div class="stat-value">{elapsed_str}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Commits Processed</div>
                <div class="stat-value">{(status_info.get('totalCommitsProcessed') or 0):,}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Signatures Verified</div>
                <div class="stat-value">{(status_info.get('totalSignaturesProcessed') or 0):,}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Merge Relationships</div>
                <div class="stat-value">{(status_info.get('totalMergesProcessed') or 0):,}</div>
            </div>
        </div>
        
        <hr/>
        
        <p><b>Started At:</b> {started_str}</p>
        <p><b>Last Update:</b> {last_update_str}</p>
        
        {cypher_suggestions}
        
        <hr/>
        {refresh_message}
    </div>
</body>
</html>
        """
    finally:
        db.close()


def get_cypher_suggestions(status: str, status_info: dict) -> str:
    """Generate Cypher query suggestions based on current ingest stage."""
    suggestions = []
    
    if status in ['ENRICHING', 'COMPLETED']:
        # After enrichment starts, suggest schema visualization
        suggestions.append({
            'title': 'View Database Schema',
            'query': 'CALL db.schema.visualization()',
            'description': 'See the graph structure as it evolves during ingestion.'
        })
        
        # Count nodes
        suggestions.append({
            'title': 'Count All Nodes',
            'query': 'MATCH (a) RETURN count(a) AS total_nodes',
            'description': 'See how many nodes have been created so far.'
        })
        
        if (status_info.get('totalSignaturesProcessed') or 0) > 0:
            suggestions.append({
                'title': 'View PGP Signatures',
                'query': 'MATCH (c:Commit)-[:HAS_SIGNATURE]->(k:PGPKey) RETURN c.commit_hash, k.fingerprint LIMIT 10',
                'description': 'Explore commits with verified PGP signatures.'
            })
    
    if status == 'COMPLETED':
        suggestions.append({
            'title': 'Explore Merge Relationships',
            'query': 'MATCH (m:Commit {{isMerge: true}})-[:MERGED_INCLUDES]->(c:Commit) RETURN m, c LIMIT 25',
            'description': 'Visualize merge commit relationships.'
        })
    
    if not suggestions:
        return ""
    
    html = '<div class="cypher-section">'
    html += '<h4>🔍 While You Wait: Try These Neo4j Queries</h4>'
    html += '<p style="color: #666; font-size: 0.9em;">Copy and paste these queries into your Neo4j Browser to explore the data as it loads:</p>'
    
    for i, suggestion in enumerate(suggestions[:3], 1):  # Limit to 3 suggestions
        html += f'<div style="margin: 15px 0;">'
        html += f'<strong>{i}. {suggestion["title"]}</strong>'
        html += f'<p style="color: #666; font-size: 0.85em; margin: 5px 0;">{suggestion["description"]}</p>'
        html += f'<div class="cypher-query">{suggestion["query"]}</div>'
        html += '</div>'
    
    html += '</div>'
    return html


# GraphQL endpoint with CORS:
graphql_view = allow_all_origins(
    GraphQLView.as_view(
        "graphql",
        schema=schema,
        graphiql=True
    )
)
app.add_url_rule(
    "/api/graphql",
    view_func=graphql_view,
    methods=["GET", "POST", "OPTIONS"]
)

if __name__ == "__main__":
    # IPv6 + IPv4
    app.run(host="::", debug=True)
