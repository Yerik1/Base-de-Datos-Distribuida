-- =====================================================================
-- Proyecto 1 · Opción A — Banca / billetera regional
-- Esquema FÍSICO para CockroachDB (Fase B / Entregable 2).
--
-- Este archivo es la traducción a CockroachDB del esquema LÓGICO ya
-- aprobado en el Entregable 1 (PK/FK, fragmentación horizontal primaria
-- de cliente y cuenta, fragmentación horizontal derivada de movimiento,
-- réplica de catalogo_region). No cambia entidades, atributos, predicados
-- ni cardinalidades del E1: solo agrega la sintaxis de localidad que el
-- motor exige para materializar esa fragmentación y esa réplica.
--
-- Requisito previo: 00_configurar_regiones.sql ya debe haberse ejecutado
-- (la base "ti4601" debe tener las 3 regiones: cr-sj, cr-limon, us-east).
--
-- DECISIONES DE FASE B QUE EL EQUIPO DEBE PODER EXPLICAR EN LA DEFENSA
-- (ninguna contradice el E1; todas son necesarias para implementarlo en
-- CockroachDB y se documentan aquí explícitamente, no se asumen en silencio):
--
-- (1) codigo_region pasa de STRING libre (E1) a crdb_internal_region: el
--     tipo ENUM que CockroachDB genera automáticamente al ejecutar
--     ALTER DATABASE ... PRIMARY REGION / ADD REGION. Sigue siendo la
--     llave primaria de catalogo_region y sigue significando lo mismo
--     (el código de una de las 3 regiones); el cambio de tipo es lo que
--     permite declarar cliente.region_apertura y cuenta.region con
--     REGIONAL BY ROW AS <columna>, que es la forma nativa de Cockroach
--     de expresar "fragmentación horizontal primaria por región" (ver
--     labs/lab1-cluster/README.md, sección 2).
--
-- (2) cuenta y movimiento quedan con llave primaria compuesta
--     (region, <llave_natural>) en vez de la llave natural sola. Esto
--     replica exactamente el patrón que usa el propio ejemplo del curso
--     (labs/lab1-cluster/schema.sql, tabla "pedido": PRIMARY KEY (region,
--     pedido_id)) y es requisito de CockroachDB para que REGIONAL BY ROW
--     particione el índice primario por región. La llave natural
--     (num_cuenta, id_movimiento) se conserva sin cambios de significado.
--
-- (3) La FK de movimiento hacia cuenta se declara como
--     FOREIGN KEY (region, num_cuenta) REFERENCES cuenta (region, num_cuenta)
--     en vez de solo (num_cuenta). Esto no es un cambio de diseño: es el
--     refuerzo que el propio E1 dejó pendiente ("invariante a reforzar por
--     trigger o columna calculada en Fase B", sección de fragmentación
--     derivada). Con esta FK compuesta, CockroachDB rechaza a nivel de
--     motor cualquier fila de movimiento cuya región no coincida con la
--     región de su cuenta —ya no depende solo de que la aplicación sea
--     disciplinada—.
--
-- (4) movimiento.region NO tiene DEFAULT ni se autocompleta con
--     gateway_region(): la aplicación (seed.py) siempre la asigna
--     explícitamente igual a cuenta.region, porque nuestra fragmentación
--     es por predicado de negocio, no por región del nodo que atiende la
--     conexión.
-- =====================================================================

-- ---------------------------------------------------------------------
-- catalogo_region: réplica completa en las 3 regiones (E1, sección 5).
-- LOCALITY GLOBAL es la primitiva de Cockroach pensada exactamente para
-- este caso: catálogos pequeños y de baja escritura que se leen desde
-- cualquier región con latencia local, sin necesitar join remoto.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalogo_region (
    codigo_region  crdb_internal_region NOT NULL PRIMARY KEY,
    nombre         STRING NOT NULL,
    pais           STRING NOT NULL
) LOCALITY GLOBAL;

-- ---------------------------------------------------------------------
-- cliente: fragmentación horizontal primaria por region_apertura (E1).
-- PII (nombre, documento, correo, telefono) reside solo en la región de
-- apertura, tal como exige la Opción A del enunciado del proyecto.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cliente (
    region_apertura   crdb_internal_region NOT NULL,
    id_cliente        UUID NOT NULL DEFAULT gen_random_uuid(),
    nombre            STRING NOT NULL,
    documento         STRING NOT NULL,
    correo            STRING,
    telefono          STRING,
    PRIMARY KEY (region_apertura, id_cliente),
    UNIQUE INDEX cliente_id_cliente_key (id_cliente),
    CONSTRAINT fk_cliente_region
        FOREIGN KEY (region_apertura) REFERENCES catalogo_region (codigo_region)
) LOCALITY REGIONAL BY ROW AS region_apertura;

-- ---------------------------------------------------------------------
-- cuenta: fragmentación horizontal primaria por region (E1).
-- FK a cliente independiente de la región de la cuenta (E1 permite que
-- una cuenta se abra en una región distinta a la de registro del
-- cliente; ambas FK viajan por separado, como en el diseño aprobado).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cuenta (
    region          crdb_internal_region NOT NULL,
    num_cuenta      UUID NOT NULL DEFAULT gen_random_uuid(),
    tipo_cuenta     STRING NOT NULL,
    saldo           DECIMAL(14, 2) NOT NULL DEFAULT 0 CHECK (saldo >= 0),
    fecha_apertura  TIMESTAMPTZ NOT NULL DEFAULT now(),
    id_cliente      UUID NOT NULL,
    PRIMARY KEY (region, num_cuenta),
    CONSTRAINT fk_cuenta_region
        FOREIGN KEY (region) REFERENCES catalogo_region (codigo_region),
    CONSTRAINT fk_cuenta_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente (id_cliente)
) LOCALITY REGIONAL BY ROW AS region;

-- ---------------------------------------------------------------------
-- movimiento: fragmentación horizontal DERIVADA de cuenta (E1): cada
-- movimiento vive en la misma región que su cuenta. region es la copia
-- denormalizada documentada en E1; aquí queda garantizada por la FK
-- compuesta (region, num_cuenta), no solo por convención de aplicación.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS movimiento (
    region           crdb_internal_region NOT NULL,
    id_movimiento    UUID NOT NULL DEFAULT gen_random_uuid(),
    tipo_movimiento  STRING NOT NULL,
    monto            DECIMAL(14, 2) NOT NULL CHECK (monto > 0),
    fecha            TIMESTAMPTZ NOT NULL DEFAULT now(),
    num_cuenta       UUID NOT NULL,
    PRIMARY KEY (region, id_movimiento),
    CONSTRAINT fk_movimiento_cuenta
        FOREIGN KEY (region, num_cuenta) REFERENCES cuenta (region, num_cuenta)
) LOCALITY REGIONAL BY ROW AS region;
