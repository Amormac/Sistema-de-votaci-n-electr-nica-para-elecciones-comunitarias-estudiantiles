import os
from dotenv import load_dotenv

# Cargar variables de entorno antes de crear la app
load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
