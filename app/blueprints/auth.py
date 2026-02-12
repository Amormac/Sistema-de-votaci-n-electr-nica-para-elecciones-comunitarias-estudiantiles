import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
import bcrypt
from app.db import get_db, query_db, execute_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

# --- Decoradores ---
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        
        if g.user['rol'] != 'ADMIN':
            flash("Acceso denegado. Se requiere administrador.", "error")
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view

# --- Carga de usuario en cada request ---
@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = query_db("SELECT * FROM usuarios WHERE id = %s", (user_id,), one=True)

# --- Rutas ---
@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        cedula = request.form['cedula']
        password = request.form['password']
        db = get_db()
        error = None
        
        user = query_db("SELECT * FROM usuarios WHERE cedula = %s", (cedula,), one=True)

        if user is None:
            error = 'Usuario no encontrado.'
        elif not user['habilitado']:
             error = 'Usuario deshabilitado.'
        else:
            # Validar password
            # La password en DB debe ser bytes para bcrypt, asegurarnos de encode
            if not bcrypt.checkpw(password.encode('utf-8'), user['clave'].encode('utf-8')):
                error = 'Contraseña incorrecta.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            session['user_rol'] = user['rol']
            
            # Auditoría
            execute_db("INSERT INTO auditoria (evento, detalle, usuario_id, ip_origen) VALUES (%s, %s, %s, %s)",
                       ('LOGIN_OK', f'Ingreso de {user["rol"]}', user['id'], request.remote_addr))
            
            if user['rol'] == 'ADMIN':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('voter.votar'))

        flash(error, 'error')
        # Registrar fallo login (sin usuario id si no existe, o con si existe pero falló pass)
        execute_db("INSERT INTO auditoria (evento, detalle, ip_origen) VALUES (%s, %s, %s)",
                   ('LOGIN_FAIL', f'Intento fallido cedula: {cedula}', request.remote_addr))

    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
