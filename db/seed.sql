-- Cargos Base
INSERT INTO cargos (nombre, descripcion) VALUES 
('Presidente del Consejo Estudiantil', 'Representante principal de los estudiantes'),
('Vicepresidente', 'Segundo al mando'),
('Tesorero', 'Encargado de finanzas');

-- Usuario Admin inicial se creará vía script python para hashear password correctamente.
-- Pero podemos insertar usuarios demo (sin acceso real o con password conocido "1234" si usamos generador externo, 
-- pero mejor dejar que el script python haga el seed de usuarios para garantizar el hash correcto).

-- Aquí solo seed de estructura base si hiciera falta.
