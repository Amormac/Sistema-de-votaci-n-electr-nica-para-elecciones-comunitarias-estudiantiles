import psycopg2
import psycopg2.extras
import os
import click
import bcrypt
from flask import g, current_app

def get_db():
    """Conecta a la base de datos y adjunta la conexión al contexto global de Flask."""
    if 'db' not in g:
        try:
            g.db = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                database=os.getenv('DB_NAME', 'votacion_db'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASS', 'password'),
                port=os.getenv('DB_PORT', 5432)
            )
            g.db.autocommit = False # Manejo manual de transacciones
        except Exception as e:
            print(f"Error conectando a DB: {e}")
            raise e
    return g.db

def close_db(e=None):
    """Cierra la conexión al finalizar el request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Inicializa la DB ejecutando schema.sql y seed.sql"""
    db = get_db()
    cursor = db.cursor()
    
    # Leer schema
    with current_app.open_resource('../db/schema.sql') as f:
        cursor.execute(f.read().decode('utf8'))
    
    # Leer seed
    with current_app.open_resource('../db/seed.sql') as f:
        cursor.execute(f.read().decode('utf8'))
        
    db.commit()
    cursor.close()

def seed_users():
    """Crea usuarios iniciales: un admin y 10 votantes de prueba."""
    db = get_db()
    cur = db.cursor()
    
    users = [
        # Admin
        {'cedula': '0000000001', 'nombres': 'Administrador', 'apellidos': 'Sistema',
         'fecha_nacimiento': '1990-01-01', 'clave': 'admin123', 'rol': 'ADMIN', 'genero': 'M'},
        # 10 Votantes de prueba
        {'cedula': '1712345678', 'nombres': 'María José', 'apellidos': 'García López',
         'fecha_nacimiento': '2001-03-15', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'F'},
        {'cedula': '0923456789', 'nombres': 'Carlos Andrés', 'apellidos': 'Mendoza Ruiz',
         'fecha_nacimiento': '2000-07-22', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'M'},
        {'cedula': '1304567890', 'nombres': 'Ana Lucía', 'apellidos': 'Torres Vega',
         'fecha_nacimiento': '2002-01-10', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'F'},
        {'cedula': '0705678901', 'nombres': 'Luis Fernando', 'apellidos': 'Pérez Moreira',
         'fecha_nacimiento': '1999-11-05', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'M'},
        {'cedula': '1806789012', 'nombres': 'Sofía Valentina', 'apellidos': 'Ramírez Castro',
         'fecha_nacimiento': '2001-09-28', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'F'},
        {'cedula': '0107890123', 'nombres': 'Diego Sebastián', 'apellidos': 'Morales Andrade',
         'fecha_nacimiento': '2000-04-17', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'M'},
        {'cedula': '1508901234', 'nombres': 'Camila Alejandra', 'apellidos': 'Herrera Solís',
         'fecha_nacimiento': '2002-06-03', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'F'},
        {'cedula': '2209012345', 'nombres': 'Andrés Felipe', 'apellidos': 'Cevallos Bravo',
         'fecha_nacimiento': '1999-12-20', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'M'},
        {'cedula': '0610123456', 'nombres': 'Valentina Isabel', 'apellidos': 'Guzmán Paredes',
         'fecha_nacimiento': '2001-08-14', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'F'},
        {'cedula': '1111234567', 'nombres': 'Mateo Nicolás', 'apellidos': 'Salazar Villacís',
         'fecha_nacimiento': '2000-02-09', 'clave': 'voter123', 'rol': 'VOTANTE', 'genero': 'M'},
    ]
    
    for u in users:
        hashed = bcrypt.hashpw(u['clave'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cur.execute("""
            INSERT INTO usuarios (cedula, nombres, apellidos, fecha_nacimiento, genero, clave, rol, habilitado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (cedula) DO UPDATE SET clave = EXCLUDED.clave, genero = EXCLUDED.genero
        """, (u['cedula'], u['nombres'], u['apellidos'], u['fecha_nacimiento'], u['genero'], hashed, u['rol']))
        click.echo(f"  Usuario {u['rol']} creado: cedula={u['cedula']}, password={u['clave']}")
    
    db.commit()
    cur.close()

@click.command('init-db')
def init_db_command():
    """Elimina las tablas existentes, crea nuevas y siembra datos iniciales."""
    click.echo('Inicializando base de datos...')
    init_db()
    click.echo('Tablas creadas. Creando usuarios iniciales...')
    seed_users()
    click.echo('¡Base de datos inicializada correctamente!')

def query_db(query, args=(), one=False):
    """Ejecuta una consulta y devuelve resultados como dict."""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    """Ejecuta un comando (INSERT, UPDATE, DELETE) y hace commit."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(query, args)
        db.commit()
        last_row_id = cur.fetchone()[0] if cur.description else None
        cur.close()
        return last_row_id
    except Exception as e:
        db.rollback()
        cur.close()
        raise e
