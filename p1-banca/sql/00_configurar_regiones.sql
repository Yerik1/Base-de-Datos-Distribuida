-- Proyecto 1 · Opción A (Banca / billetera regional)
-- Paso 0 (Fase B): convertir "ti4601" en base multi-región.
-- Reutiliza el procedimiento del Lab 1 (README §5, Paso 3) sobre la MISMA base
-- que ya usa el equipo (no se crea una base nueva).
--
-- Ejecutar UNA sentencia a la vez desde psql (PSQL), dentro del contenedor
-- app-crdb (ver README.md de esta carpeta para el comando completo).

ALTER DATABASE ti4601 PRIMARY REGION "cr-sj";
ALTER DATABASE ti4601 ADD REGION "cr-limon";
ALTER DATABASE ti4601 ADD REGION "us-east";

-- Verificación (debe listar las 3 regiones, cr-sj como primaria):
SHOW REGIONS FROM DATABASE ti4601;
