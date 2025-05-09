import socket
from .schema import schema
from flask_graphql import GraphQLView

from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    html = "<h3>Hello Fullstack!</h3>" \
           "<b>Hostname:</b> {hostname}<br/>" 

    return html.format(hostname=socket.gethostname())

app.add_url_rule('/graphql', view_func=GraphQLView.as_view('graphql',
                                                                 schema=schema,
                                                                 graphiql=True))

if __name__ == "__main__":

    app.run(host='0.0.0.0')
