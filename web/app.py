"""Flask application entry-point.

Expose ``app`` at module level so Flask's built-in dev-server can discover it::

    flask --app web.app run --debug
"""

from web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
