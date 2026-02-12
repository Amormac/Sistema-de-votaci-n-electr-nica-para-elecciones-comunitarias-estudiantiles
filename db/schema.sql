-- Eliminar tablas si existen (orden inverso a dependencias)
DROP TABLE IF EXISTS auditoria;
DROP TABLE IF EXISTS certificados;
DROP TABLE IF EXISTS votos;
DROP TABLE IF EXISTS candidatos_vuelta;
DROP TABLE IF EXISTS candidatos;
DROP TABLE IF EXISTS eleccion_votantes;
DROP TABLE IF EXISTS eleccion_cargos;
DROP TABLE IF EXISTS cargos;
DROP TABLE IF EXISTS elecciones;
DROP TABLE IF EXISTS usuarios;

-- 1. Tabla de Usuarios
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    cedula VARCHAR(10) UNIQUE NOT NULL,
    nombres VARCHAR(100) NOT NULL,
    apellidos VARCHAR(100) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    genero VARCHAR(1) CHECK (genero IN ('M', 'F')),
    clave VARCHAR(255) NOT NULL, -- Hash bcrypt
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('ADMIN', 'VOTANTE')),
    habilitado BOOLEAN DEFAULT TRUE,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla de Elecciones
CREATE TABLE elecciones (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT,
    fecha_inicio TIMESTAMP NOT NULL,
    fecha_fin TIMESTAMP NOT NULL,
    activa BOOLEAN DEFAULT FALSE,
    cerrada BOOLEAN DEFAULT FALSE,
    vuelta_actual INT DEFAULT 1,
    tiene_segunda_vuelta BOOLEAN DEFAULT FALSE,
    todos_habilitados BOOLEAN DEFAULT TRUE
);

-- 3. Tabla de Cargos (Globales, pero se asocian a elecciones)
CREATE TABLE cargos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT
);

-- 4. Relación Elección-Cargos
CREATE TABLE eleccion_cargos (
    election_id INT REFERENCES elecciones(id) ON DELETE CASCADE,
    cargo_id INT REFERENCES cargos(id) ON DELETE CASCADE,
    PRIMARY KEY (election_id, cargo_id)
);

-- 5. Votantes habilitados por elección (si todos_habilitados=FALSE)
CREATE TABLE eleccion_votantes (
    election_id INT REFERENCES elecciones(id) ON DELETE CASCADE,
    votante_id INT REFERENCES usuarios(id) ON DELETE CASCADE,
    PRIMARY KEY (election_id, votante_id)
);

-- 6. Candidatos
CREATE TABLE candidatos (
    id SERIAL PRIMARY KEY,
    election_id INT REFERENCES elecciones(id) ON DELETE CASCADE,
    cargo_id INT REFERENCES cargos(id) ON DELETE CASCADE,
    nombres VARCHAR(100) NOT NULL,
    partido VARCHAR(100),
    genero VARCHAR(1) CHECK (genero IN ('M', 'F')),
    foto_url VARCHAR(255),
    estado VARCHAR(20) DEFAULT 'ACTIVO',
    FOREIGN KEY (election_id, cargo_id) REFERENCES eleccion_cargos(election_id, cargo_id)
);

-- 7. Candidatos Segunda Vuelta
CREATE TABLE candidatos_vuelta (
    id SERIAL PRIMARY KEY,
    original_candidato_id INT REFERENCES candidatos(id) ON DELETE CASCADE,
    election_id INT REFERENCES elecciones(id) ON DELETE CASCADE,
    cargo_id INT REFERENCES cargos(id) ON DELETE CASCADE,
    vuelta INT DEFAULT 2,
    UNIQUE(election_id, cargo_id, original_candidato_id)
);

-- 8. Votos
CREATE TABLE votos (
    id SERIAL PRIMARY KEY,
    election_id INT REFERENCES elecciones(id),
    cargo_id INT REFERENCES cargos(id),
    candidato_id INT REFERENCES candidatos(id),
    votante_id INT REFERENCES usuarios(id),
    vuelta INT NOT NULL,
    fecha_voto TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(election_id, cargo_id, vuelta, votante_id)
);

-- 9. Certificados
CREATE TABLE certificados (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(64) UNIQUE NOT NULL,
    election_id INT REFERENCES elecciones(id),
    votante_id INT REFERENCES usuarios(id),
    vuelta INT NOT NULL,
    fecha_emision TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    contenido_hash TEXT
);

-- 10. Auditoría
CREATE TABLE auditoria (
    id SERIAL PRIMARY KEY,
    evento VARCHAR(50) NOT NULL,
    detalle TEXT,
    usuario_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
    ip_origen VARCHAR(45),
    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indices
CREATE INDEX idx_votos_candidato ON votos(election_id, cargo_id, vuelta, candidato_id);
CREATE INDEX idx_usuarios_cedula ON usuarios(cedula);
CREATE INDEX idx_eleccion_votantes ON eleccion_votantes(election_id, votante_id);
