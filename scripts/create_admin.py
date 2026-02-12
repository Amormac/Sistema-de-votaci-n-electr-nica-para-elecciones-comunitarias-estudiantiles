import sys
import os
import bcrypt

# Add path to be able to import app
sys.path.append(os.getcwd())

from flask import Flask
from app.db import init_db, execute_db

from app import create_app

app = create_app()

def create_admin_user():
    print("Creando usuario ADMIN...")
    cedula = input("Cedula Admin: ") or "0000000000"
    nombres = "Administrador"
    apellidos = "Sistema"
    clave = input("Password Admin (default: admin123): ") or "admin123"
    
    hashed = bcrypt.hashpw(clave.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    with app.app_context():
        # Inicializar DB primero
        print("Inicializando base de datos (schema)...")
        init_db()
        
        try:
            execute_db("""
                INSERT INTO usuarios (cedula, nombres, apellidos, fecha_nacimiento, clave, rol, habilitado)
                VALUES (%s, %s, %s, '1990-01-01', %s, 'ADMIN', TRUE)
                ON CONFLICT (cedula) DO UPDATE SET clave = EXCLUDED.clave;
            """, (cedula, nombres, apellidos, hashed))
            print(f"Admin creado exitosamente. Cedula: {cedula}")
        except Exception as e:
            print(f"Error creando admin: {e}")

if __name__ == '__main__':
    create_admin_user()
