import os
from flask import Flask, render_template

def create_app(test_config=None):
    # Crear y configurar la app
    app = Flask(__name__, instance_relative_config=True)
    
    # Cargar configuración desde .env se hace fuera o aquí si usamos python-dotenv antes de llamar a create_app
    # Asumimos que las variables de entorno ya están cargadas en el entry point (wsgi.py o app.py)
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev'),
    )

    # Registrar funciones de cierre de DB y CLI
    from . import db
    app.teardown_appcontext(db.close_db)
    app.cli.add_command(db.init_db_command)

    # Ruta principal
    @app.route('/')
    def index():
        return render_template('index.html')

    # Registrar Blueprints
    from .blueprints import auth, admin, voter
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(voter.bp)

    # Context processor para saber si el votante tiene elecciones pendientes
    @app.context_processor
    def inject_voter_pending():
        from flask import g
        tiene_pendientes = False
        if hasattr(g, 'user') and g.user and g.user['rol'] == 'VOTANTE':
            from .db import query_db
            elecciones = query_db("SELECT * FROM elecciones WHERE activa = TRUE")
            for e in elecciones:
                if e['todos_habilitados']:
                    ya_voto = query_db(
                        "SELECT id FROM votos WHERE election_id=%s AND vuelta=%s AND votante_id=%s LIMIT 1",
                        (e['id'], e['vuelta_actual'], g.user['id']), one=True)
                    if not ya_voto:
                        tiene_pendientes = True
                        break
                else:
                    hab = query_db(
                        "SELECT votante_id FROM eleccion_votantes WHERE election_id=%s AND votante_id=%s",
                        (e['id'], g.user['id']), one=True)
                    if hab:
                        ya_voto = query_db(
                            "SELECT id FROM votos WHERE election_id=%s AND vuelta=%s AND votante_id=%s LIMIT 1",
                            (e['id'], e['vuelta_actual'], g.user['id']), one=True)
                        if not ya_voto:
                            tiene_pendientes = True
                            break
        return dict(tiene_pendientes=tiene_pendientes)

    return app
