#!/usr/bin/env python3
"""Instala (opcionalmente) una licencia Enterprise/docente de CockroachDB.

Referenciado por p1-banca/README.md paso 1. Si COCKROACH_LICENSE /
COCKROACH_ORGANIZATION no están definidas en el .env (ver .env.example en la
raíz del repo), el script no hace nada: el clúster sigue funcionando bajo el
período de prueba automático que CockroachDB otorga a las funciones
Enterprise/multi-región (REGIONAL BY ROW, LOCALITY GLOBAL) que usa el
esquema propio del equipo (p1-banca/sql/01_schema.sql). Con una licencia
docente real, instala las cluster settings correspondientes.

Uso (dentro del contenedor app-crdb):

    python3 labs/lab1-cluster/install_license.py
"""

from __future__ import annotations

import os

import psycopg
from psycopg import sql


def main() -> int:
    license_key = os.environ.get("COCKROACH_LICENSE", "").strip()
    organization = os.environ.get("COCKROACH_ORGANIZATION", "").strip()

    if not license_key or not organization:
        print(
            "COCKROACH_LICENSE / COCKROACH_ORGANIZATION no configuradas en .env: "
            "se omite la instalación de licencia. El cluster usara el periodo de "
            "prueba automatico de CockroachDB para las funciones multi-region."
        )
        return 0

    # SET CLUSTER SETTING no acepta parámetros ligados (bind params) en el
    # protocolo extendido de Postgres/CockroachDB; se compone el literal de
    # forma segura con psycopg.sql en vez de interpolar el string a mano.
    with psycopg.connect(autocommit=True) as conn:
        conn.execute(
            sql.SQL("SET CLUSTER SETTING cluster.organization = {}").format(
                sql.Literal(organization)
            )
        )
        conn.execute(
            sql.SQL("SET CLUSTER SETTING enterprise.license = {}").format(
                sql.Literal(license_key)
            )
        )
    print(f"Licencia instalada para la organizacion: {organization}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
