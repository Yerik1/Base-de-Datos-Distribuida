#!/usr/bin/env python3
"""Verifica, de solo lectura, que el esquema propio del Proyecto 1 (Opción A)
está configurado según el Entregable 1: 3 regiones, catalogo_region GLOBAL,
cliente/cuenta/movimiento REGIONAL BY ROW, y una fila por región en cada
tabla fragmentada. Inspirado en labs/lab1-cluster/verify_cluster.py, pero
sobre el esquema propio (no crea ni corrige nada).
"""

from __future__ import annotations

import sys
from collections.abc import Callable

import psycopg

EXPECTED_REGIONS = {"cr-sj", "cr-limon", "us-east"}


def live_regions(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT locality FROM crdb_internal.gossip_nodes WHERE is_live"
    ).fetchall()
    return {
        item.removeprefix("region=")
        for row in rows
        for item in str(row[0]).split(",")
        if item.startswith("region=")
    }


def check(label: str, assertion: Callable[[], bool], hint: str) -> bool:
    try:
        passed = assertion()
    except (psycopg.Error, IndexError, TypeError) as exc:
        print(f"[FAIL] {label}: {str(exc).splitlines()[0]}")
        print(f"       Pista: {hint}")
        return False
    if passed:
        print(f"[ OK ] {label}")
        return True
    print(f"[FAIL] {label}")
    print(f"       Pista: {hint}")
    return False


def main() -> int:
    try:
        conn = psycopg.connect(autocommit=True)
    except psycopg.Error as exc:
        print(f"[FAIL] conexión: {str(exc).splitlines()[0]}")
        print("       Pista: levante el clúster (make lab1-up) y revise make lab1-status.")
        return 1

    with conn:
        results = [
            check(
                "tres nodos/localities vivos",
                lambda: EXPECTED_REGIONS <= live_regions(conn),
                "revise localities y logs de crdb-1, crdb-2 y crdb-3",
            ),
            check(
                "tres regiones configuradas en ti4601",
                lambda: EXPECTED_REGIONS
                <= {
                    str(row[1])
                    for row in conn.execute("SHOW REGIONS FROM DATABASE ti4601").fetchall()
                },
                "ejecute sql/00_configurar_regiones.sql",
            ),
            check(
                "catalogo_region es GLOBAL",
                lambda: "LOCALITY GLOBAL"
                in str(conn.execute("SHOW CREATE TABLE catalogo_region").fetchone()[1]).upper(),
                "aplique sql/01_schema.sql después de configurar las regiones",
            ),
            check(
                "cliente es REGIONAL BY ROW AS region_apertura",
                lambda: "REGIONAL BY ROW AS REGION_APERTURA"
                in str(conn.execute("SHOW CREATE TABLE cliente").fetchone()[1]).upper(),
                "revise la cláusula LOCALITY de cliente en sql/01_schema.sql",
            ),
            check(
                "cuenta es REGIONAL BY ROW AS region",
                lambda: "REGIONAL BY ROW AS region".upper()
                in str(conn.execute("SHOW CREATE TABLE cuenta").fetchone()[1]).upper(),
                "revise la cláusula LOCALITY de cuenta en sql/01_schema.sql",
            ),
            check(
                "movimiento es REGIONAL BY ROW AS region",
                lambda: "REGIONAL BY ROW AS region".upper()
                in str(conn.execute("SHOW CREATE TABLE movimiento").fetchone()[1]).upper(),
                "revise la cláusula LOCALITY de movimiento en sql/01_schema.sql",
            ),
            check(
                "hay clientes en las 3 regiones",
                lambda: EXPECTED_REGIONS
                == {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT DISTINCT region_apertura FROM cliente"
                    ).fetchall()
                },
                "corra scripts/seed.py",
            ),
            check(
                "hay cuentas en las 3 regiones",
                lambda: EXPECTED_REGIONS
                == {
                    str(row[0])
                    for row in conn.execute("SELECT DISTINCT region FROM cuenta").fetchall()
                },
                "corra scripts/seed.py",
            ),
            check(
                "todo movimiento coincide en región con su cuenta",
                lambda: conn.execute(
                    """
                    SELECT count(*) FROM movimiento m
                    JOIN cuenta c ON c.num_cuenta = m.num_cuenta
                    WHERE c.region <> m.region
                    """
                ).fetchone()[0]
                == 0,
                "no debería poder pasar: la FK compuesta (region, num_cuenta) lo impide",
            ),
        ]

    passed = sum(results)
    print(f"\nResultado: {passed}/{len(results)} verificaciones.")
    if passed != len(results):
        print("El verificador no modificó nada. Corrija el primer FAIL y repita.")
        return 1
    print("Esquema propio (Opción A) listo para mediciones (E3).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
