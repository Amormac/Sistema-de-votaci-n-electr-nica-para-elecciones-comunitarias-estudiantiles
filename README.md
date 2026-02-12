# Sistema de Votación Electrónica

Sistema de votación desarrollado en Python con Flask y PostgreSQL.

## Requisitos
- Python 3.8+
- PostgreSQL 14+
- `virtualenv`

## Configuración e Instalación (Ubuntu 22.04)

1. **Clonar repositorio**
   ```bash
   git clone <repo_url>
   cd Sistema-de-votaci-n-electr-nica-para-elecciones-comunitarias-estudiantiles
   ```

2. **Crear entorno virtual**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar Base de Datos**
   - Asegúrate de tener PostgreSQL corriendo.
   - Crea la base de datos:
     ```sql
     CREATE DATABASE votacion_db;
     ```
   - Configura el archivo `.env`:
     ```bash
     cp .env.example .env
     nano .env
     # Edita DB_HOST, DB_NAME, DB_USER, DB_PASS según tu config local
     ```

5. **Inicializar Sistema y Crear Admin**
   Este script creará las tablas y un usuario administrador.
   ```bash
   python scripts/create_admin.py
   # Sigue las instrucciones en pantalla
   ```

6. **Ejecutar Aplicación**
   ```bash
   python app.py
   ```
   La aplicación correrá en `http://localhost:5001`.

## Uso

### Administrador
- Accede a `/login` con la cédula y contraseña del admin creado.
- **Crear Elección**: Define título y fechas.
- **Crear Cargos**: Define los cargos disponibles (ej: Alcalde).
- **Asignar Cargos**: En la lista de elecciones, asigna qué cargos se votan.
- **Registrar Candidatos**: Agrega candidatos a la elección.
- **Cargar Votantes**: Sube un CSV con la lista de votantes.
- **Activar Elección**: Permite que los usuarios voten.

### Votante
- Accede a `/login` con cédula y contraseña.
- Si hay una elección activa, verá la papeleta digital.
- Debe seleccionar un candidato por cada cargo.
- Al confirmar, recibe un certificado digital con un hash de verificación.

## Estructura del Proyecto
- `app/`: Código fuente
  - `blueprints/`: Lógica de negocio (auth, admin, voter)
  - `templates/`: Archivos HTML Jinja2
  - `static/`: CSS y Assets
  - `db.py`: Conexión a PostgreSQL (psycopg2)
- `db/`: Scripts SQL (schema, seed)
- `scripts/`: Scripts de utilidad

## Auditoría
Todas las acciones críticas (Login, Voto, Creación de Elección) quedan registradas en la tabla `auditoria` y son visibles en el Dashboard del Admin.
