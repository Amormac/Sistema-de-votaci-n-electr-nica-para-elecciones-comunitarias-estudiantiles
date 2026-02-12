import hashlib
import json
import datetime
from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for
)
from app.db import get_db, query_db, execute_db
from app.blueprints.auth import login_required

bp = Blueprint('voter', __name__, url_prefix='/votar')

@bp.route('/')
@login_required
def votar():
    user = g.user
    if user['rol'] != 'VOTANTE':
        return redirect(url_for('admin.dashboard'))
    
    # Buscar elecciones activas
    elecciones = query_db("SELECT * FROM elecciones WHERE activa = TRUE")
    
    if not elecciones:
        return render_template('voter/no_elecciones.html')
    
    # Filtrar por elegibilidad del votante
    elegibles = []
    for e in elecciones:
        if e['todos_habilitados']:
            elegibles.append(e)
        else:
            hab = query_db(
                "SELECT votante_id FROM eleccion_votantes WHERE election_id=%s AND votante_id=%s",
                (e['id'], user['id']), one=True)
            if hab:
                elegibles.append(e)
    
    if not elegibles:
        return render_template('voter/no_elecciones.html')
    
    # Clasificar: pendientes vs ya votadas
    pendientes = []
    votadas = []
    for e in elegibles:
        ya_voto = query_db(
            "SELECT id FROM votos WHERE election_id=%s AND vuelta=%s AND votante_id=%s LIMIT 1",
            (e['id'], e['vuelta_actual'], user['id']), one=True)
        if ya_voto:
            cert = query_db("SELECT * FROM certificados WHERE election_id=%s AND vuelta=%s AND votante_id=%s",
                            (e['id'], e['vuelta_actual'], user['id']), one=True)
            votadas.append({'eleccion': e, 'certificado': cert})
        else:
            pendientes.append(e)
    
    # Si solo hay 1 pendiente, ir directo a la boleta
    if len(pendientes) == 1 and not votadas:
        return redirect(url_for('voter.votar_eleccion', election_id=pendientes[0]['id']))
    
    # Mostrar selector de elecciones
    return render_template('voter/selector_elecciones.html',
                           pendientes=pendientes, votadas=votadas)

@bp.route('/<int:election_id>', methods=('GET',))
@login_required
def votar_eleccion(election_id):
    user = g.user
    if user['rol'] != 'VOTANTE':
        return redirect(url_for('admin.dashboard'))
    
    selected_election = query_db("SELECT * FROM elecciones WHERE id=%s AND activa=TRUE", (election_id,), one=True)
    if not selected_election:
        flash("Elección no disponible.", "error")
        return redirect(url_for('voter.votar'))
    
    # Verificar elegibilidad
    if not selected_election['todos_habilitados']:
        habilitado = query_db(
            "SELECT votante_id FROM eleccion_votantes WHERE election_id=%s AND votante_id=%s",
            (election_id, user['id']), one=True)
        if not habilitado:
            flash("No estás habilitado para esta elección.", "error")
            return redirect(url_for('voter.votar'))
    
    eid = selected_election['id']
    vuelta = selected_election['vuelta_actual']
    
    # Verificar si ya votó
    ya_voto = query_db("SELECT id FROM votos WHERE election_id=%s AND vuelta=%s AND votante_id=%s LIMIT 1", 
                       (eid, vuelta, user['id']), one=True)
    
    if ya_voto:
        cert = query_db("SELECT * FROM certificados WHERE election_id=%s AND vuelta=%s AND votante_id=%s",
                        (eid, vuelta, user['id']), one=True)
        return render_template('voter/ya_voto.html', certificado=cert)
    
    # Obtener cargos y candidatos
    cargos = query_db("""
        SELECT c.* FROM cargos c 
        JOIN eleccion_cargos ec ON c.id = ec.cargo_id 
        WHERE ec.election_id = %s
    """, (eid,))
    
    datos_boleta = []
    for cargo in cargos:
        if vuelta == 1:
            candidatos = query_db("SELECT * FROM candidatos WHERE election_id=%s AND cargo_id=%s AND estado='ACTIVO'", (eid, cargo['id']))
        else:
            candidatos = query_db("""
                SELECT c.* FROM candidatos c
                JOIN candidatos_vuelta cv ON c.id = cv.original_candidato_id
                WHERE cv.election_id=%s AND cv.cargo_id=%s AND cv.vuelta=2
            """, (eid, cargo['id']))
            
        datos_boleta.append({
            'cargo': cargo,
            'candidatos': candidatos
        })
        
    return render_template('voter/boleta.html', eleccion=selected_election, boleta=datos_boleta)

@bp.route('/confirmar', methods=['POST'])
@login_required
def confirmar_voto():
    user = g.user
    eid = request.form['election_id']
    vuelta = request.form['vuelta']
    
    # Validaciones server-side rápidas
    cargos_ids = request.form.getlist('cargo_ids') # IDs de cargos que SE DEBEN votar
    
    # Iniciar Transacción manual
    db = get_db()
    cur = db.cursor()
    
    try:
        # Verificar doble voto again (bloqueo)
        cur.execute("SELECT id FROM votos WHERE election_id=%s AND vuelta=%s AND votante_id=%s LIMIT 1",
                    (eid, vuelta, user['id']))
        if cur.fetchone():
            raise Exception("Ya has votado en esta elección.")

        selections = []
        for cid in cargos_ids:
            field_name = f"candidato_{cid}"
            candidate_selected = request.form.get(field_name)
            if not candidate_selected:
                raise Exception(f"Falta seleccionar candidato para el cargo ID {cid}")
            
            selections.append((eid, cid, candidate_selected, user['id'], vuelta))
        
        # Insertar votos
        for sel in selections:
            cur.execute("""
                INSERT INTO votos (election_id, cargo_id, candidato_id, votante_id, vuelta)
                VALUES (%s, %s, %s, %s, %s)
            """, sel)
            
        # Generar Certificado
        # Hash simple de datos
        raw_data = f"{eid}-{vuelta}-{user['id']}-{datetime.datetime.now().isoformat()}"
        cert_code = hashlib.sha256(raw_data.encode()).hexdigest()
        
        cur.execute("""
            INSERT INTO certificados (codigo, election_id, votante_id, vuelta, contenido_hash)
            VALUES (%s, %s, %s, %s, %s)
        """, (cert_code, eid, user['id'], vuelta, raw_data))
        
        # Auditoria
        cur.execute("""
            INSERT INTO auditoria (evento, detalle, usuario_id, ip_origen)
            VALUES (%s, %s, %s, %s)
        """, ('VOTO_EMITIDO', f'Voto completo eleccion {eid}', user['id'], request.remote_addr))
        
        db.commit()
        return redirect(url_for('voter.certificado', codigo=cert_code))

    except Exception as e:
        db.rollback()
        flash(f"Error al votar: {str(e)}", "error")
        return redirect(url_for('voter.votar'))
    finally:
        cur.close()

@bp.route('/certificado/<codigo>')
@login_required
def certificado(codigo):
    cert = query_db("SELECT * FROM certificados WHERE codigo=%s", (codigo,), one=True)
    if not cert:
        return "Certificado no encontrado", 404
        
    usuario = query_db("SELECT * FROM usuarios WHERE id=%s", (cert['votante_id'],), one=True)
    eleccion = query_db("SELECT * FROM elecciones WHERE id=%s", (cert['election_id'],), one=True)
    
    return render_template('voter/certificado.html', certificado=cert, usuario=usuario, eleccion=eleccion)
