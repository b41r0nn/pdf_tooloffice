"""
Arranque local de PDF ToolOffice.

    python run.py            (desde la carpeta del proyecto)

Host y puerto se leen de .env (FLASK_HOST / FLASK_PORT). En producción usar
gunicorn (ver app/Dockerfile).
"""

import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('FLASK_PORT', '5000')),
        debug=False,
        threaded=True,
    )
