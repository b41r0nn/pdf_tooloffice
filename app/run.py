"""Alternativa: python -m app.run (desde la carpeta del proyecto)."""

import os

from . import create_app

app = create_app()

if __name__ == '__main__':
    app.run(
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('FLASK_PORT', '5000')),
        debug=False,
        threaded=True,
    )
