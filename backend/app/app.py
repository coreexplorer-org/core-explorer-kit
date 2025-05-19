import socket
from functools import wraps

from flask import Flask, request, make_response
from flask_graphql import GraphQLView
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
