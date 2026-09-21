#!/usr/bin/env python3
"""E4 — Falla de sitio (nodo): mide RTO de escritura y valida RPO.

Automatiza los pasos 1, 3 y 4 del protocolo mínimo de E4 (ver enunciado):

  1. Estado sano: hace una escritura de prueba y confirma que se comprometió
     OK antes de tocar nada.
  2. (manual, en OTRA terminal, mientras este script sigue corriendo):

         docker stop ti4601-crdb-2

     detiene el nodo dueño de la región --region (por defecto cr-limon).
     Este script NO ejecuta el docker stop -- eso lo pide el enunciado como
     acción explícita del operador, con su propio timestamp en la terminal.
  3. Mientras tanto, este script reintenta la MISMA escritura cada
     --interval segundos sobre la fila de prueba de esa región y cronometra
     cuánto tarda en volver a confirmarse rápido (RTO observado).
  4. Al terminar, relee el saldo y lo compara contra
     saldo_inicial + 0.01 * escrituras_confirmadas: si coincide exactamente,
     es evidencia de RPO=0 (ninguna escritura confirmada se perdió ni se
     duplicó). Si no coincide, lo reporta como hallazgo a discutir.
  5. Evidencia: cada intento (timestamp UTC, estado, latencia, error) queda
     en el CSV (--csv) y en la consola -- redirigir con Tee-Object/tee.

Uso (en una terminal DEDICADA -- vas a necesitar otra terminal aparte para
el docker stop/start; dejá esta corriendo en primer plano para ver la
recuperación en vivo):

    docker compose --profile lab1 run --rm --no-deps app-crdb \\
        python3 p1-banca/scripts/e4_failover.py \\
        --region cr-limon --interval 0.5 --max-seconds 120 \\
        --csv p1-banca/evidence/e4-failover.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import psycopg

# Mismas cuentas de prueba fijas que seed.py / measure_latency.py.
CUENTAS_PRUEBA = {
    "cr-sj": "2e000000-0000-0000-0000-000000000001",
    "cr-limon": "2e000000-0000-0000-0000-000000000002",
    "us-east": "2e000000-0000-0000-0000-000000000003",
}

# Encima de este umbral, una escritura "exitosa" igual cuenta como síntoma
# de outage (quedó bloqueada esperando el failover del leaseholder en vez
# de fallar con un error explícito -- ambos comportamientos son válidos en
# CockroachDB durante una relección de Raft).
SLOW_MS = 500.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect(timeout_ms: int) -> psycopg.Connection:
    # PGHOST/PGPORT/PGUSER/PGDATABASE los inyecta docker-compose (fijo a
    # crdb-1, región cr-sj) -- igual que measure_latency.py / seed.py.
    return psycopg.connect(
        connect_timeout=3,
        autocommit=True,
        options=f"-c statement_timeout={timeout_ms}",
    )


def read_saldo(conn: psycopg.Connection, region: str, num_cuenta: str) -> Decimal:
    row = conn.execute(
        "SELECT saldo FROM cuenta WHERE region = %s AND num_cuenta = %s",
        (region, num_cuenta),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"No existe la cuenta de prueba de {region}; corra seed.py primero")
    return row[0]


def try_write(conn: psycopg.Connection, region: str, num_cuenta: str) -> tuple[bool, float, str]:
    started = time.perf_counter()
    try:
        conn.execute(
            "UPDATE cuenta SET saldo = saldo + 0.01 WHERE region = %s AND num_cuenta = %s",
            (region, num_cuenta),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        return True, elapsed_ms, ""
    except psycopg.Error as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return False, elapsed_ms, str(exc).splitlines()[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--region", default="cr-limon", choices=sorted(CUENTAS_PRUEBA))
    parser.add_argument("--interval", type=float, default=0.5, help="segundos entre reintentos")
    parser.add_argument("--max-seconds", type=float, default=120.0, help="duración total del monitoreo")
    parser.add_argument("--timeout-ms", type=int, default=10000, help="statement_timeout por intento")
    parser.add_argument("--csv", default="p1-banca/evidence/e4-failover.csv")
    args = parser.parse_args()

    num_cuenta = CUENTAS_PRUEBA[args.region]
    contenedor = {"cr-sj": "ti4601-crdb-1", "cr-limon": "ti4601-crdb-2", "us-east": "ti4601-crdb-3"}[args.region]
    rows: list[dict[str, str]] = []

    def log(ts: str, attempt: int, status: str, elapsed_ms: float, error: str) -> None:
        rows.append(
            {
                "ts": ts,
                "attempt": str(attempt),
                "status": status,
                "elapsed_ms": f"{elapsed_ms:.1f}",
                "error": error,
            }
        )

    # --- Paso 1: estado sano ---
    conn = connect(args.timeout_ms)
    saldo_inicial = read_saldo(conn, args.region, num_cuenta)
    ok, elapsed_ms, err = try_write(conn, args.region, num_cuenta)
    ts = now_iso()
    log(ts, 0, "OK" if ok else "ERROR", elapsed_ms, err)
    if not ok:
        print(f"[{ts}] ESTADO SANO: FALLO ({err}) -- revise el clúster antes de continuar")
        return 1
    exitos = 1
    print(f"[{ts}] ESTADO SANO: escritura de prueba OK en {elapsed_ms:.1f} ms (saldo inicial={saldo_inicial})")
    print(f"\n>>> Ahora, en OTRA terminal, corra:  docker stop {contenedor}")
    print(f">>> (nodo de la región {args.region}). Este script reintenta cada {args.interval}s")
    print(f">>> durante hasta {args.max_seconds}s y va a marcar cuándo se cae y cuándo se recupera.\n")

    # --- Pasos 2 (manual)/3: monitoreo continuo, detecta caída y RTO ---
    outage_started_at: float | None = None
    rto_seconds: float | None = None
    attempt = 0
    deadline = time.monotonic() + args.max_seconds
    was_healthy = True

    while time.monotonic() < deadline:
        time.sleep(args.interval)
        attempt += 1
        attempt_started_at = time.monotonic()  # antes de la llamada: marca real de "cuándo empezó a fallar"
        try:
            ok, elapsed_ms, err = try_write(conn, args.region, num_cuenta)
        except Exception as exc:  # conexión rota de verdad (no solo lenta)
            ok, elapsed_ms, err = False, 0.0, f"conexión rota: {exc}".splitlines()[0]
            try:
                conn.close()
            except Exception:
                pass
            try:
                conn = connect(args.timeout_ms)
            except Exception as exc2:
                err = f"reconexión falló: {exc2}".splitlines()[0]

        ts = now_iso()
        healthy_now = ok and elapsed_ms < SLOW_MS
        if ok:
            exitos += 1
        log(ts, attempt, "OK" if ok else "ERROR", elapsed_ms, err)

        if was_healthy and not healthy_now:
            # el intento que detecta la caída puede ÉL MISMO haber quedado
            # bloqueado varios segundos (p. ej. docker kill sin drain) -- el
            # inicio real del outage es cuando ARRANCÓ ese intento, no cuando
            # terminó de imprimirse.
            outage_started_at = attempt_started_at
            motivo = err if err else f"escritura lenta ({elapsed_ms:.0f} ms >= {SLOW_MS:.0f} ms)"
            print(f"[{ts}] intento {attempt}: OUTAGE DETECTADO -- {motivo}")
        elif not was_healthy and healthy_now:
            # el fin real es cuando TERMINÓ este intento de recuperación
            # (su propio arranque + lo que tardó), no cuando lo detectamos.
            recovered_at = attempt_started_at + (elapsed_ms / 1000.0)
            rto_seconds = recovered_at - outage_started_at if outage_started_at else None
            extra = f" -- RTO observado ~= {rto_seconds:.1f} s" if rto_seconds is not None else ""
            print(f"[{ts}] intento {attempt}: RECUPERADO ({elapsed_ms:.0f} ms){extra}")
        else:
            estado = "OK" if ok else f"ERROR ({err})"
            print(f"[{ts}] intento {attempt}: {estado} ({elapsed_ms:.0f} ms)")

        was_healthy = healthy_now

    # --- Paso 4: chequeo de RPO ---
    try:
        saldo_final = read_saldo(conn, args.region, num_cuenta)
    except Exception:
        conn = connect(args.timeout_ms)
        saldo_final = read_saldo(conn, args.region, num_cuenta)

    saldo_esperado = (saldo_inicial + Decimal("0.01") * exitos).quantize(Decimal("0.01"))
    saldo_final_r = saldo_final.quantize(Decimal("0.01"))
    rpo_ok = saldo_esperado == saldo_final_r

    print("\n=== Resumen E4 ===")
    print(f"Región / nodo detenido: {args.region} / {contenedor}")
    print(f"Intentos totales (sin contar el de estado sano): {attempt}")
    print(f"Escrituras confirmadas: {exitos}")
    if rto_seconds is not None:
        print(f"RTO observado: {rto_seconds:.1f} s")
    elif outage_started_at is not None:
        print("RTO observado: NO se recuperó dentro de --max-seconds (aumente --max-seconds)")
    else:
        print("RTO observado: no se detectó ninguna caída (¿corriste el docker stop a tiempo?)")
    print(f"Saldo inicial: {saldo_inicial}  |  esperado tras {exitos} escrituras: {saldo_esperado}  |  final real: {saldo_final_r}")
    print(f"RPO: {'0 (sin pérdida ni duplicación detectada)' if rpo_ok else 'DISCREPANCIA -- revisar log, posible ambigüedad de commit'}")

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["ts", "attempt", "status", "elapsed_ms", "error"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nEvidencia cruda (todos los intentos): {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
