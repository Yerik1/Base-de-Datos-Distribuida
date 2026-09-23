-- Esquema físico para CockroachDB (banca / billetera regional)
-- Traduce a CockroachDB el esquema lógico , añade la sintaxis de localidad (LOCALITY) necesaria para materializar
-- la fragmentación horizontal por región y la réplica del catálogo.
-- Requisito previo: haber ejecutado 00_configurar_regiones.sql.
--
-- Decisiones de diseño:
-- (1) codigo_region usa crdb_internal_region, el ENUM que el motor genera
--     al registrar las regiones; es lo que habilita REGIONAL BY ROW.
-- (2) cuenta y movimiento usan llave primaria compuesta (region, id) porque
--     CockroachDB solo puede particionar el índice primario de este modo.
-- (3) La FK de movimiento hacia cuenta es compuesta (region, num_cuenta)
--     para que el motor obligue a que ambas regiones coincidan.

-- catalogo_region: catálogo pequeño y de baja escritura, replicado por
-- completo en las 3 regiones mediante LOCALITY GLOBAL para lectura local.
CREATE TABLE IF NOT EXISTS catalogo_region (
    codigo_region  crdb_internal_region NOT NULL PRIMARY KEY, -- código de región (llave)
    nombre         STRING NOT NULL,
    pais           STRING NOT NULL
) LOCALITY GLOBAL;

-- cliente: fragmentación horizontal primaria según la región de apertura;
-- los datos personales permanecen almacenados solo en esa región.
CREATE TABLE IF NOT EXISTS cliente (
    region_apertura   crdb_internal_region NOT NULL,
    id_cliente        UUID NOT NULL DEFAULT gen_random_uuid(),
    nombre            STRING NOT NULL,
    documento         STRING NOT NULL,
    correo            STRING,
    telefono          STRING,
    PRIMARY KEY (region_apertura, id_cliente),  -- llave compuesta exigida por REGIONAL BY ROW
    UNIQUE INDEX cliente_id_cliente_key (id_cliente),
    CONSTRAINT fk_cliente_region
        FOREIGN KEY (region_apertura) REFERENCES catalogo_region (codigo_region)
) LOCALITY REGIONAL BY ROW AS region_apertura; -- fragmenta la tabla por región de apertura

-- cuenta: fragmentación horizontal primaria según la región de la cuenta;
-- la FK a cliente es independiente de esa región (una cuenta puede abrirse
-- en una región distinta a la de registro del cliente).
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
) LOCALITY REGIONAL BY ROW AS region; -- fragmenta la tabla por región de la cuenta

-- movimiento: fragmentación horizontal derivada de cuenta; cada movimiento
-- reside en la misma región que su cuenta asociada.
CREATE TABLE IF NOT EXISTS movimiento (
    region           crdb_internal_region NOT NULL, -- copia denormalizada de cuenta.region
    id_movimiento    UUID NOT NULL DEFAULT gen_random_uuid(),
    tipo_movimiento  STRING NOT NULL,
    monto            DECIMAL(14, 2) NOT NULL CHECK (monto > 0),
    fecha            TIMESTAMPTZ NOT NULL DEFAULT now(),
    num_cuenta       UUID NOT NULL,
    PRIMARY KEY (region, id_movimiento),
    CONSTRAINT fk_movimiento_cuenta  -- FK compuesta: exige que la región coincida con la de la cuenta
        FOREIGN KEY (region, num_cuenta) REFERENCES cuenta (region, num_cuenta)
) LOCALITY REGIONAL BY ROW AS region;
