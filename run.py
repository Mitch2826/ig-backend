"""
run.py
Local development entry point.
    python run.py
For production, gunicorn calls create_app() directly (see Dockerfile, later).
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])