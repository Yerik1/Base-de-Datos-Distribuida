# Proyecto 1 — Base de datos distribuida a pequeña escala
 
**TI-4601 Bases de Datos Avanzados · Instituto Tecnológico de Costa Rica**
Profesor: Manuel Zumbado Corrales
 
| Integrante | Carné |
| --- | --- |
| Emmanuel Esquivel Chavarría | 2022312336 |
| Yerik Chaves Serrano | 2022437493 |
| Jose Pablo Guerrero Duarte | 2022099311 |
 
## Descripción
 
Implementación y medición de una base de datos distribuida sobre tres regiones
simuladas, correspondiente a la **Opción A (banca / billetera regional)** del enunciado.
El dominio se fragmenta horizontalmente por región, de manera que la información
personal de cada cliente reside únicamente en la región donde abrió su cuenta.
 
- **Motor:** CockroachDB CCL v23.2.31, tres nodos en Docker Compose.
- **Regiones:** `cr-sj` (nodo 1), `cr-limon` (nodo 2), `us-east` (nodo 3).
- **Cliente:** Python 3.12 con `psycopg`, ejecutado siempre dentro del contenedor `app-crdb`.
- **Tablas:** `catalogo_region` con localidad `GLOBAL`; `cliente`, `cuenta` y `movimiento`
  con localidad `REGIONAL BY ROW`.