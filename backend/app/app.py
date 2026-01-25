import socket
import threading
import uuid
from functools import wraps
from flask import Flask, request, make_response
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


@app.route("/api/process_git_data_to_neo4j/")
def process_git_data_to_neo4j():
    # Generate a unique ID for this run
    run_id = str(uuid.uuid4())
    
    # Launch processing in a background thread
    thread = threading.Thread(
        target=process_git_data, 
        kwargs={"use_new_schema": True, "run_id": run_id}
    )
    thread.daemon = True  # Ensure thread closes if app does
    thread.start()

    # Return immediate feedback with a link to check status
    html = (
        "<h3>Ingestion Started in Background</h3>"
        "<p><b>Run ID:</b> {run_id}</p>"
        "<p>You can monitor progress here: <a href='/api/ingest_status/{run_id}/'>/api/ingest_status/{run_id}/</a></p>"
        "<br/>"
        "<b>Hostname:</b> {hostname}<br/>"
    )
    return html.format(run_id=run_id, hostname=socket.gethostname())


@app.route("/api/ingest_status/<run_id>/")
@allow_all_origins
def ingest_status(run_id):
    db = Neo4jDriver()
    try:
        status_info = db.get_ingest_run_status(run_id)
        if not status_info:
            return f"<h3>Ingest Run {run_id} not found</h3>", 404
            
        return f"""
            <h3>Ingest Run Status</h3>
            <p><b>ID:</b> {run_id}</p>
            <p><b>Status:</b> {status_info['status']}</p>
            <p><b>Commits Processed:</b> {status_info.get('totalCommitsProcessed', 0)}</p>
            <p><b>Signatures Verified:</b> {status_info.get('totalSignaturesProcessed', 0)}</p>
            <p><b>Merge Relationships:</b> {status_info.get('totalMergesProcessed', 0)}</p>
            <p><b>Started At:</b> {status_info['pulledAt']}</p>
            <hr/>
            <p><small><a href="">Refresh this page</a> for updates.</small></p>
        """
    finally:
        db.close()


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
