# Import the Flask app instance
# When mounted, app.py is at /app/app.py, so this import works
from app import app

if __name__ == "__main__":
    app.run()
