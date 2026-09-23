-- Configuración de regiones (banca / billetera regional)
-- Este script convierte la base de datos "ti4601" en una base multi-región,
-- siguiendo el procedimiento estudiado del Laboratorio 1, con el fin de
-- habilitar en Fase B la fragmentación horizontal por región del proyecto.
--
-- Ejecutar cada sentencia por separado desde psql, dentro del contenedor
-- app-crdb (ver README.md de esta carpeta para el comando completo).

ALTER DATABASE ti4601 PRIMARY REGION "cr-sj";   -- región primaria: San José
ALTER DATABASE ti4601 ADD REGION "cr-limon";    -- región secundaria: Limón
ALTER DATABASE ti4601 ADD REGION "us-east";     -- región secundaria: US East

-- Verificación: debe listar las 3 regiones, con cr-sj como primaria.
SHOW REGIONS FROM DATABASE ti4601;
