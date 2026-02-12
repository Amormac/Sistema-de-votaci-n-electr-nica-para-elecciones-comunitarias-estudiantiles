import os
import csv
import io
import datetime
import bcrypt
from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, current_app
)
from app.db import get_db, query_db, execute_db
from app.blueprints.auth import admin_required

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/')
@admin_required
def dashboard():
    # Estadisticas rapidas
    votos_totales = query_db("SELECT COUNT(*) as c FROM votos", one=True)['c']
    elecciones_activas = query_db("SELECT COUNT(*) as c FROM elecciones WHERE activa = TRUE", one=True)['c']
    usuarios_totales = query_db("SELECT COUNT(*) as c FROM usuarios WHERE rol='VOTANTE'", one=True)['c']
    
    # Ultimos eventos auditoria
    auditoria = query_db("SELECT * FROM auditoria ORDER BY fecha_evento DESC LIMIT 10")
    
    return render_template('admin/dashboard.html', 
                           stats={'votos': votos_totales, 'elecciones': elecciones_activas, 'usuarios': usuarios_totales},
                           auditoria=auditoria)

# --- ELECCIONES ---
@bp.route('/elecciones', methods=('GET', 'POST'))
@admin_required
def elecciones():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            titulo = request.form['titulo']
            f_inicio = request.form['fecha_inicio']
            f_fin = request.form['fecha_fin']
            segunda = 'tiene_segunda_vuelta' in request.form
            
            execute_db("""
                INSERT INTO elecciones (titulo, fecha_inicio, fecha_fin, tiene_segunda_vuelta)
                VALUES (%s, %s, %s, %s)
            """, (titulo, f_inicio, f_fin, segunda))
            
            # Obtener el ID de la elección recién creada
            nueva = query_db("SELECT id FROM elecciones ORDER BY id DESC LIMIT 1", one=True)
            
            execute_db("INSERT INTO auditoria (evento, detalle, usuario_id) VALUES (%s, %s, %s)",
                       ('ADMIN_CREA_ELECCION', f'Eleccion: {titulo}', g.user['id']))
            flash('Elección creada. Ahora configura los cargos y candidatos.', 'success')
            return redirect(url_for('admin.eleccion_detalle', id=nueva['id']))
            
        elif action == 'toggle_active':
            eid = request.form['id']
            curr = query_db("SELECT activa FROM elecciones WHERE id=%s", (eid,), one=True)
            new_state = not curr['activa']
            execute_db("UPDATE elecciones SET activa = %s WHERE id = %s", (new_state, eid))
            flash(f'Estado cambiado a {"ACTIVA" if new_state else "INACTIVA"}', 'success')
            
        elif action == 'close':
            eid = request.form['id']
            execute_db("UPDATE elecciones SET cerrada = TRUE, activa = FALSE WHERE id = %s", (eid,))
            flash('Elección cerrada definitivamente.', 'warning')
            
    elecciones = query_db("SELECT * FROM elecciones ORDER BY fecha_inicio DESC")
    return render_template('admin/elecciones.html', elecciones=elecciones)

# --- DETALLE / CONFIGURACIÓN DE ELECCIÓN (Vista Unificada) ---
@bp.route('/elecciones/<int:id>', methods=('GET', 'POST'))
@admin_required
def eleccion_detalle(id):
    eleccion = query_db("SELECT * FROM elecciones WHERE id=%s", (id,), one=True)
    if not eleccion:
        flash("Elección no encontrada.", "error")
        return redirect(url_for('admin.elecciones'))
    
    es_editable = not eleccion['activa'] and not eleccion['cerrada']
    
    if request.method == 'POST':
        if not es_editable:
            flash("No se puede modificar una elección activa o cerrada.", "error")
            return redirect(url_for('admin.eleccion_detalle', id=id))
        
        action = request.form.get('action')
        
        if action == 'update_info':
            titulo = request.form['titulo']
            f_inicio = request.form['fecha_inicio']
            f_fin = request.form['fecha_fin']
            segunda = 'tiene_segunda_vuelta' in request.form
            execute_db("""
                UPDATE elecciones SET titulo=%s, fecha_inicio=%s, fecha_fin=%s, tiene_segunda_vuelta=%s
                WHERE id=%s
            """, (titulo, f_inicio, f_fin, segunda, id))
            flash("Datos de la elección actualizados.", "success")
        
        elif action == 'save_cargos':
            cargos_selec = request.form.getlist('cargos')
            execute_db("DELETE FROM eleccion_cargos WHERE election_id = %s", (id,))
            for cid in cargos_selec:
                execute_db("INSERT INTO eleccion_cargos (election_id, cargo_id) VALUES (%s, %s)", (id, cid))
            flash("Cargos actualizados.", "success")
        
        elif action == 'add_cargo_nuevo':
            nombre = request.form['cargo_nombre'].strip()
            desc = request.form.get('cargo_descripcion', '').strip()
            if nombre:
                # Crear cargo si no existe
                existe = query_db("SELECT id FROM cargos WHERE lower(nombre)=lower(%s)", (nombre,), one=True)
                if existe:
                    cargo_id = existe['id']
                else:
                    execute_db("INSERT INTO cargos (nombre, descripcion) VALUES (%s, %s)", (nombre, desc))
                    nuevo = query_db("SELECT id FROM cargos ORDER BY id DESC LIMIT 1", one=True)
                    cargo_id = nuevo['id']
                # Asignar a la elección
                ya_asignado = query_db("SELECT election_id FROM eleccion_cargos WHERE election_id=%s AND cargo_id=%s", (id, cargo_id), one=True)
                if not ya_asignado:
                    execute_db("INSERT INTO eleccion_cargos (election_id, cargo_id) VALUES (%s, %s)", (id, cargo_id))
                    flash(f"Cargo '{nombre}' agregado.", "success")
                else:
                    flash(f"El cargo '{nombre}' ya está asignado.", "warning")
        
        elif action == 'remove_cargo':
            cargo_id = request.form['cargo_id']
            # También borrar candidatos de ese cargo en esta elección
            execute_db("DELETE FROM candidatos WHERE election_id=%s AND cargo_id=%s", (id, cargo_id))
            execute_db("DELETE FROM eleccion_cargos WHERE election_id=%s AND cargo_id=%s", (id, cargo_id))
            flash("Cargo y sus candidatos removidos.", "success")
        
        elif action == 'add_candidato':
            cargo_id = request.form['cargo_id']
            nombres = request.form['nombres']
            partido = request.form['partido']
            genero = request.form.get('genero', 'M')
            
            # Handle photo upload
            foto_filename = None
            foto = request.files.get('foto')
            if foto and foto.filename:
                import uuid
                from werkzeug.utils import secure_filename
                ext = foto.filename.rsplit('.', 1)[-1].lower() if '.' in foto.filename else 'jpg'
                if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                    flash("Formato de imagen no válido. Use JPG, PNG, GIF o WEBP.", "error")
                    return redirect(url_for('admin.eleccion_detalle', id=id))
                foto_filename = f"{uuid.uuid4().hex}.{ext}"
                upload_dir = os.path.join(current_app.static_folder, 'uploads', 'candidatos')
                os.makedirs(upload_dir, exist_ok=True)
                foto.save(os.path.join(upload_dir, foto_filename))
            
            execute_db("""
                INSERT INTO candidatos (election_id, cargo_id, nombres, partido, genero, foto_url)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id, cargo_id, nombres, partido, genero, foto_filename))
            flash("Candidato agregado.", "success")
            return redirect(url_for('admin.eleccion_detalle', id=id) + '#candidatos')
        
        elif action == 'edit_candidato':
            candidato_id = request.form['candidato_id']
            nombres = request.form['nombres']
            partido = request.form['partido']
            genero = request.form.get('genero', 'M')
            
            # Handle optional new photo
            foto = request.files.get('foto')
            if foto and foto.filename:
                import uuid
                ext = foto.filename.rsplit('.', 1)[-1].lower() if '.' in foto.filename else 'jpg'
                if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                    # Delete old photo
                    old = query_db("SELECT foto_url FROM candidatos WHERE id=%s", (candidato_id,), one=True)
                    if old and old['foto_url']:
                        old_path = os.path.join(current_app.static_folder, 'uploads', 'candidatos', old['foto_url'])
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    foto_filename = f"{uuid.uuid4().hex}.{ext}"
                    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'candidatos')
                    os.makedirs(upload_dir, exist_ok=True)
                    foto.save(os.path.join(upload_dir, foto_filename))
                    execute_db("UPDATE candidatos SET nombres=%s, partido=%s, genero=%s, foto_url=%s WHERE id=%s AND election_id=%s",
                               (nombres, partido, genero, foto_filename, candidato_id, id))
                else:
                    flash("Formato de imagen no válido.", "error")
                    return redirect(url_for('admin.eleccion_detalle', id=id))
            else:
                execute_db("UPDATE candidatos SET nombres=%s, partido=%s, genero=%s WHERE id=%s AND election_id=%s",
                           (nombres, partido, genero, candidato_id, id))
            flash("Candidato actualizado.", "success")
            return redirect(url_for('admin.eleccion_detalle', id=id) + '#candidatos')
        
        elif action == 'delete_candidato':
            candidato_id = request.form['candidato_id']
            # Remove photo file if exists
            cand = query_db("SELECT foto_url FROM candidatos WHERE id=%s", (candidato_id,), one=True)
            if cand and cand['foto_url']:
                foto_path = os.path.join(current_app.static_folder, 'uploads', 'candidatos', cand['foto_url'])
                if os.path.exists(foto_path):
                    os.remove(foto_path)
            execute_db("DELETE FROM candidatos WHERE id=%s AND election_id=%s", (candidato_id, id))
            flash("Candidato eliminado.", "success")
            return redirect(url_for('admin.eleccion_detalle', id=id) + '#candidatos')
        
        elif action == 'toggle_todos_habilitados':
            todos = request.form.get('todos_habilitados') == 'on'
            execute_db("UPDATE elecciones SET todos_habilitados=%s WHERE id=%s", (todos, id))
            if todos:
                execute_db("DELETE FROM eleccion_votantes WHERE election_id=%s", (id,))
            flash("Configuración de votantes actualizada.", "success")
            return redirect(url_for('admin.eleccion_detalle', id=id) + '#votantes')
        
        elif action == 'save_votantes':
            votante_ids = request.form.getlist('votante_ids')
            execute_db("DELETE FROM eleccion_votantes WHERE election_id=%s", (id,))
            for vid in votante_ids:
                execute_db("INSERT INTO eleccion_votantes (election_id, votante_id) VALUES (%s, %s)", (id, int(vid)))
            flash(f"{len(votante_ids)} votantes habilitados para esta elección.", "success")
            return redirect(url_for('admin.eleccion_detalle', id=id) + '#votantes')
        
        elif action == 'activate':
            # Validar que tenga al menos 1 cargo con al menos 2 candidatos
            cargos_asignados = query_db("""
                SELECT c.id, c.nombre, COUNT(cand.id) as num_candidatos
                FROM cargos c
                JOIN eleccion_cargos ec ON c.id = ec.cargo_id
                LEFT JOIN candidatos cand ON cand.cargo_id = c.id AND cand.election_id = %s
                WHERE ec.election_id = %s
                GROUP BY c.id, c.nombre
            """, (id, id))
            
            if not cargos_asignados:
                flash("Debe agregar al menos un cargo antes de activar.", "error")
            else:
                cargos_sin_candidatos = [c for c in cargos_asignados if c['num_candidatos'] < 2]
                if cargos_sin_candidatos:
                    nombres = ', '.join([c['nombre'] for c in cargos_sin_candidatos])
                    flash(f"Los siguientes cargos necesitan al menos 2 candidatos: {nombres}", "error")
                else:
                    execute_db("UPDATE elecciones SET activa = TRUE WHERE id = %s", (id,))
                    execute_db("INSERT INTO auditoria (evento, detalle, usuario_id) VALUES (%s, %s, %s)",
                               ('ADMIN_ACTIVA_ELECCION', f'Eleccion ID: {id}', g.user['id']))
                    flash("¡Elección activada exitosamente!", "success")
                    return redirect(url_for('admin.elecciones'))
        
        return redirect(url_for('admin.eleccion_detalle', id=id))
    
    # --- GET: Cargar datos ---
    todos_cargos = query_db("SELECT * FROM cargos ORDER BY nombre")
    cargos_asignados = query_db("""
        SELECT c.* FROM cargos c
        JOIN eleccion_cargos ec ON c.id = ec.cargo_id
        WHERE ec.election_id = %s
        ORDER BY c.nombre
    """, (id,))
    asignados_ids = [c['id'] for c in cargos_asignados]
    
    # Candidatos agrupados por cargo
    candidatos_por_cargo = {}
    for cargo in cargos_asignados:
        cands = query_db("""
            SELECT * FROM candidatos
            WHERE election_id = %s AND cargo_id = %s
            ORDER BY nombres
        """, (id, cargo['id']))
        candidatos_por_cargo[cargo['id']] = cands
    
    # Votantes para gestión de elegibilidad
    todos_votantes = query_db("SELECT id, cedula, nombres, apellidos FROM usuarios WHERE rol='VOTANTE' AND habilitado=TRUE ORDER BY apellidos, nombres")
    votantes_asignados_ids = []
    if not eleccion['todos_habilitados']:
        rows = query_db("SELECT votante_id FROM eleccion_votantes WHERE election_id=%s", (id,))
        votantes_asignados_ids = [r['votante_id'] for r in rows]
    
    return render_template('admin/eleccion_detalle.html',
                           eleccion=eleccion,
                           es_editable=es_editable,
                           todos_cargos=todos_cargos,
                           cargos_asignados=cargos_asignados,
                           asignados_ids=asignados_ids,
                           candidatos_por_cargo=candidatos_por_cargo,
                           todos_votantes=todos_votantes,
                           votantes_asignados_ids=votantes_asignados_ids)

# --- USUARIOS CSV ---
@bp.route('/usuarios', methods=('GET', 'POST'))
@admin_required
def usuarios():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        
        if file:
            # Procesar CSV
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)
            
            exitos = 0
            errores = []
            
            for row in csv_input:
                try:
                    # Validaciones
                    cedula = row['cedula'].strip()
                    if len(cedula) != 10 or not cedula.isdigit():
                         raise Exception(f"Cédula inválida: {cedula}")
                    
                    # Validar password (simple)
                    clave = row['clave']
                    if len(clave) < 8:
                        raise Exception("Clave muy corta")
                    
                    hashed = bcrypt.hashpw(clave.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    habilitado = row.get('habilitado', 'true').lower() == 'true'
                    
                    execute_db("""
                        INSERT INTO usuarios (cedula, nombres, apellidos, fecha_nacimiento, clave, rol, habilitado)
                        VALUES (%s, %s, %s, %s, %s, 'VOTANTE', %s)
                        ON CONFLICT (cedula) DO NOTHING
                    """, (cedula, row['nombres'], row['apellidos'], row['fecha_nacimiento'], hashed, habilitado))
                    exitos += 1
                except Exception as e:
                    errores.append(f"Fila {row.get('cedula', '?')}: {str(e)}")
            
            flash(f"Carga completada. Exitos: {exitos}. Errores: {len(errores)}", "info")
            if errores:
                flash(f"Detalle errores: {'; '.join(errores[:5])}...", "warning")
            
            execute_db("INSERT INTO auditoria (evento, detalle, usuario_id) VALUES (%s, %s, %s)",
                       ('ADMIN_CARGA_CSV', f'Usuarios importados: {exitos}', g.user['id']))

    # Listar usuarios registrados
    usuarios_list = query_db("SELECT * FROM usuarios ORDER BY rol DESC, id ASC")
    return render_template('admin/usuarios.html', usuarios=usuarios_list)

# --- RESULTADOS ---
@bp.route('/resultados/<int:election_id>')
@admin_required
def resultados(election_id):
    eleccion = query_db("SELECT * FROM elecciones WHERE id=%s", (election_id,), one=True)
    cargos = query_db("""
        SELECT c.* FROM cargos c 
        JOIN eleccion_cargos ec ON c.id = ec.cargo_id 
        WHERE ec.election_id = %s
    """, (election_id,))
    
    vuelta = eleccion['vuelta_actual']
    resultados_data = {}
    
    for cargo in cargos:
        rows = query_db("""
            SELECT cand.nombres, cand.partido, cand.genero, cand.foto_url, COUNT(v.id) as total
            FROM candidatos cand
            LEFT JOIN votos v ON v.candidato_id = cand.id AND v.vuelta = %s AND v.election_id = %s
            WHERE cand.cargo_id = %s AND cand.election_id = %s
            GROUP BY cand.id
            ORDER BY total DESC
        """, (vuelta, election_id, cargo['id'], election_id))
        
        resultados_data[cargo['nombre']] = rows
    
    # Estadísticas de participación
    votos_row = query_db("SELECT COUNT(DISTINCT votante_id) as total FROM votos WHERE election_id=%s AND vuelta=%s",
                         (election_id, vuelta), one=True)
    total_votos = votos_row['total'] if votos_row else 0
    
    # Total votantes: si la elección usa votantes específicos, contar solo esos
    if eleccion['todos_habilitados']:
        votantes_row = query_db("SELECT COUNT(*) as total FROM usuarios WHERE rol='VOTANTE' AND habilitado=TRUE", one=True)
    else:
        votantes_row = query_db("SELECT COUNT(*) as total FROM eleccion_votantes WHERE election_id=%s", (election_id,), one=True)
    total_votantes = votantes_row['total'] if votantes_row else 0
    
    participacion = round((total_votos / total_votantes * 100), 1) if total_votantes > 0 else 0
    
    # Obtener lista de votantes que ya votaron
    votantes_que_votaron = query_db("""
        SELECT DISTINCT u.cedula, u.nombres, u.apellidos, u.genero, MIN(v.fecha_voto) as fecha_voto
        FROM votos v
        JOIN usuarios u ON u.id = v.votante_id
        WHERE v.election_id = %s AND v.vuelta = %s
        GROUP BY u.id, u.cedula, u.nombres, u.apellidos, u.genero
        ORDER BY MIN(v.fecha_voto) DESC
    """, (election_id, vuelta))
    
    # Obtener lista de votantes que NO han votado (pendientes / ausentes)
    if eleccion['todos_habilitados']:
        votantes_pendientes = query_db("""
            SELECT u.cedula, u.nombres, u.apellidos, u.genero
            FROM usuarios u
            WHERE u.rol = 'VOTANTE' AND u.habilitado = TRUE
              AND u.id NOT IN (
                  SELECT DISTINCT v.votante_id FROM votos v
                  WHERE v.election_id = %s AND v.vuelta = %s
              )
            ORDER BY u.apellidos, u.nombres
        """, (election_id, vuelta))
    else:
        votantes_pendientes = query_db("""
            SELECT u.cedula, u.nombres, u.apellidos, u.genero
            FROM usuarios u
            JOIN eleccion_votantes ev ON ev.votante_id = u.id
            WHERE ev.election_id = %s
              AND u.id NOT IN (
                  SELECT DISTINCT v.votante_id FROM votos v
                  WHERE v.election_id = %s AND v.vuelta = %s
              )
            ORDER BY u.apellidos, u.nombres
        """, (election_id, election_id, vuelta))
    
    return render_template('admin/resultados.html', 
                           eleccion=eleccion, 
                           resultados=resultados_data,
                           total_votos=total_votos,
                           total_votantes=total_votantes,
                           participacion=participacion,
                           votantes_que_votaron=votantes_que_votaron,
                           votantes_pendientes=votantes_pendientes)

# --- GENERAR SEGUNDA VUELTA ---
@bp.route('/segunda-vuelta/<int:election_id>', methods=['POST'])
@admin_required
def generar_segunda_vuelta(election_id):
    eleccion = query_db("SELECT * FROM elecciones WHERE id=%s", (election_id,), one=True)
    if eleccion['vuelta_actual'] != 1 or not eleccion['tiene_segunda_vuelta']:
        flash("La elección no cumple condiciones para segunda vuelta.", "error")
        return redirect(url_for('admin.resultados', election_id=election_id))
    
    # Logica: Para cada cargo, tomar Top 2
    cargos = query_db("SELECT cargo_id FROM eleccion_cargos WHERE election_id = %s", (election_id,))
    
    for c in cargos:
        cid = c['cargo_id']
        top2 = query_db("""
            SELECT candidato_id, COUNT(*) as votos
            FROM votos
            WHERE election_id = %s AND cargo_id = %s AND vuelta = 1
            GROUP BY candidato_id
            ORDER BY votos DESC
            LIMIT 2
        """, (election_id, cid))
        
        if len(top2) < 2:
            # Edge case: Menos de 2 candidatos con votos?
            # En un sistema real habria reglas complejas. Aqui asumo pasamos lo que haya.
            pass
            
        for cand in top2:
             execute_db("""
                INSERT INTO candidatos_vuelta (original_candidato_id, election_id, cargo_id, vuelta)
                VALUES (%s, %s, %s, 2)
             """, (cand['candidato_id'], election_id, cid))
             
    # Actualizar eleccion
    execute_db("UPDATE elecciones SET vuelta_actual = 2 WHERE id = %s", (election_id,))
    
    execute_db("INSERT INTO auditoria (evento, detalle, usuario_id) VALUES (%s, %s, %s)",
                       ('GENERA_SEGUNDA_VUELTA', f'Eleccion {election_id} a Vuelta 2', g.user['id']))
    
    flash("Segunda vuelta generada con éxito.", "success")
    return redirect(url_for('admin.resultados', election_id=election_id))

