#!/usr/bin/env python3
"""Mide p50/p99 de lecturas y escrituras locales y remotas sobre "cuenta".

Adaptación, para el dominio propio del equipo (Opción A: Banca), del método
de labs/lab1-cluster/measure_latency.py: gateway fijo (crdb-1, región
cr-sj), 4 casos, descarte de warm-up, percentil por "nearest rank", salida
en consola + CSV. La tabla objetivo, las columnas y las filas de prueba son
las del Entregable 1 (no las del Lab 1).

Los 4 casos exigidos por el enunciado del Proyecto 1 (E2/E3):

    Desde región      Operación              Fila hogar
    R1 = cr-sj         lectura local          cr-sj   (mismo nodo/región)
    R1 -> R2 = cr-limon lectura remota        cr-limon
    R1 = cr-sj         escritura local        cr-sj
    R1 -> R2 = cr-limon escritura que cruza   cr-limon

"Local" = el gateway que recibe la conexión (crdb-1, región cr-sj) y la fila
leída/escrita tienen la misma región hogar. "Cruza región" = el gateway es
cr-sj pero la fila hogar está en cr-limon, por lo que Cockroach debe resolver
el leaseholder de esa partición en el nodo de cr-limon.

Uso (dentro de app-crdb, después de correr seed.py):

    python3 p1-banca/scripts/measure_latency.py \\
        --runs 50 --warmup 5 --csv p1-banca/evidence/latency.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import time
from dataclasses import dataclass

import psycopg

# Cuentas de prueba fijas sembradas por seed.py (mismo UUID en cada corrida).
CUENTAS_PRUEBA = {
    "cr-sj": "2e000000-0000-0000-0000-000000000001",
    "cr-limon": "2e000000-0000-0000-0000-000000000002",
    "us-east": "2e000000-0000-0000-0000-000000000003",
}


@dataclass(frozen=True)
class Case:
    operation: str   # "read" | "write"
    locality: str    # "local" | "remote"
    region: str      # región hogar de la fila objetivo


CASES = (
    Case("read", "local", "cr-sj"),
    Case("read", "remote", "cr-limon"),
    Case("write", "local", "cr-sj"),
    Case("write", "remote", "cr-limon"),
)


def connect(host: str) -> psycopg.Connection:
    return psycopg.connect(
        host=host,
        port=26257,
        user="root",
        dbname="ti4601",
        sslmode="disable",
        connect_timeout=3,
        autocommit=True,
    )


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def execute_case(conn: psycopg.Connection, case: Case) -> None:
    num_cuenta = CUENTAS_PRUEBA[case.region]
    if case.operation == "read":
        row = conn.execute(
            """
            SELECT saldo, tipo_cuenta
            FROM cuenta
            WHERE region = %s AND num_cuenta = %s
            """,
            (case.region, num_cuenta),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"No existe la cuenta de prueba de {case.region}; corra seed.py primero"
            )
    else:
        conn.execute(
            """
            UPDATE cuenta
            SET saldo = saldo + 0.01
            WHERE region = %s AND num_cuenta = %s
            """,
            (case.region, num_cuenta),
        )


def measure(conn: psycopg.Connection, case: Case, warmup: int, runs: int) -> list[float]:
    for _ in range(warmup):
        execute_case(conn, case)

    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter_ns()
        execute_case(conn, case)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        samples.append(elapsed_ms)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="crdb-1", help="nodo de entrada fijo (región cr-sj)")
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--csv", default="")
    args = parser.parse_args()
    if args.runs < 30:
        parser.error("--runs debe ser >= 30 (mínimo exigido por el enunciado del Proyecto 1)")
    if args.warmup < 1:
        parser.error("--warmup debe ser >= 1 (para descartar cold start)")

    print(
        f"=== Proyecto 1 · Opción A (Banca) · gateway={args.gateway} · "
        f"warmup={args.warmup} · n={args.runs} ==="
    )
    summaries: list[dict[str, str | int | float]] = []
    raw: list[dict[str, str | int | float]] = []

    with connect(args.gateway) as conn:
        gateway_region = conn.execute("SELECT gateway_region()").fetchone()[0]
        print(f"Región del gateway: {gateway_region}")
        for case in CASES:
            samples = measure(conn, case, args.warmup, args.runs)
            for run, elapsed_ms in enumerate(samples, start=1):
                raw.append(
                    {
                        "operation": case.operation,
                        "locality": case.locality,
                        "home_region": case.region,
                        "run": run,
                        "latency_ms": f"{elapsed_ms:.3f}",
                    }
                )
            summaries.append(
                {
                    "operation": case.operation,
                    "locality": case.locality,
                    "home_region": case.region,
                    "n": len(samples),
                    "p50_ms": statistics.median(samples),
                    "p99_ms": percentile_nearest_rank(samples, 0.99),
                }
            )

    print("\noperation locality home_region  n  p50_ms  p99_ms")
    for row in summaries:
        print(
            f"{row['operation']:9} {row['locality']:8} "
            f"{row['home_region']:11} {row['n']:>2} "
            f"{row['p50_ms']:>7.3f} {row['p99_ms']:>7.3f}"
        )

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=raw[0].keys())
            writer.writeheader()
            writer.writerows(raw)
        print(f"\nMuestras crudas: {args.csv}")

    print(
        "\nNota metodológica (obligatoria citarla en el PDF): las 3 regiones corren "
        "como localidades lógicas en una sola máquina (Docker); no se inyectó "
        "latencia de red adicional. Un cociente remoto/local cercano a 1 es un "
        "resultado válido en este entorno y debe documentarse como límite, no "
        "ocultarse."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
