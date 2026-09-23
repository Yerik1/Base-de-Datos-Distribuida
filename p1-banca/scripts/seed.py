#!/usr/bin/env python3
"""Genera y carga un dataset sintético para el esquema de banca regional
(Entregable 1), reutilizando el patrón de conexión del Laboratorio 1.

Por cada una de las 3 regiones siembra ~50 clientes, 1-2 cuentas por cliente
y 2-6 movimientos por cuenta, además de una fila de prueba con UUID fijo
que measure_latency.py usa como objetivo estable de medición.

Uso (dentro del contenedor app-crdb):

    python3 p1-banca/scripts/seed.py
    python3 p1-banca/scripts/seed.py --reset   # vacía las tablas antes de sembrar
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg

REGIONES = {
    "cr-sj": ("San José", "Costa Rica"),
    "cr-limon": ("Limón", "Costa Rica"),
    "us-east": ("Este de EE. UU.", "Estados Unidos"),
}

# Cliente/cuenta "de prueba" con UUID fijo por región: fila estable que
# measure_latency.py reutiliza en cada corrida, aparte de la muestra aleatoria.
CLIENTE_PRUEBA = {
    "cr-sj": "1e000000-0000-0000-0000-000000000001",
    "cr-limon": "1e000000-0000-0000-0000-000000000002",
    "us-east": "1e000000-0000-0000-0000-000000000003",
}
CUENTA_PRUEBA = {
    "cr-sj": "2e000000-0000-0000-0000-000000000001",
    "cr-limon": "2e000000-0000-0000-0000-000000000002",
    "us-east": "2e000000-0000-0000-0000-000000000003",
}

NOMBRES = [
    "María", "José", "Ana", "Carlos", "Luisa", "Diego", "Sofía", "Andrés",
    "Valeria", "Esteban", "Camila", "Ricardo", "Paula", "Manuel", "Laura",
    "Kevin", "Daniela", "Gustavo", "Marcela", "Fernando",
]
APELLIDOS = [
    "Rodríguez", "Chaves", "Guerrero", "Esquivel", "Vargas", "Solano",
    "Jiménez", "Mora", "Alvarado", "Salas", "Brenes", "Rojas", "Araya",
    "Castro", "Fallas",
]
TIPOS_CUENTA = ["ahorro", "corriente"]
TIPOS_MOVIMIENTO = ["deposito", "retiro", "transferencia", "pago"]

N_CLIENTES_POR_REGION = 50


def nombre_falso(rng: random.Random) -> str:
    # Combina un nombre y un apellido tomados al azar de las listas fijas.
    return f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"


def documento_falso(rng: random.Random) -> str:
    # Genera un número de cédula ficticio con el formato típico costarricense.
    return f"{rng.randint(1, 9)}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"


def correo_falso(nombre: str, rng: random.Random) -> str:
    # Deriva un correo ficticio a partir del nombre, agregando un sufijo numérico.
    slug = nombre.lower().replace(" ", ".")
    return f"{slug}{rng.randint(1, 999)}@correo-ficticio.test"


def telefono_falso(rng: random.Random) -> str:
    # Genera un número telefónico ficticio de 8 dígitos.
    return f"{rng.randint(6000, 8999)}-{rng.randint(1000, 9999)}"


def fecha_pasada(rng: random.Random, dias_max: int = 900) -> datetime:
    # Devuelve una fecha/hora en el pasado, hasta dias_max días antes de ahora.
    delta = timedelta(days=rng.randint(0, dias_max), hours=rng.randint(0, 23))
    return datetime.now(timezone.utc) - delta


def reset(conn: psycopg.Connection) -> None:
    # Orden inverso a las FK (movimiento -> cuenta -> cliente -> catalogo_region).
    print("--reset: vaciando movimiento, cuenta, cliente, catalogo_region ...")
    conn.execute("DELETE FROM movimiento")
    conn.execute("DELETE FROM cuenta")
    conn.execute("DELETE FROM cliente")
    conn.execute("DELETE FROM catalogo_region")


def sembrar_catalogo(conn: psycopg.Connection) -> None:
    # Carga (o actualiza) la fila de catalogo_region correspondiente a cada región.
    for codigo, (nombre, pais) in REGIONES.items():
        conn.execute(
            """
            UPSERT INTO catalogo_region (codigo_region, nombre, pais)
            VALUES (%s, %s, %s)
            """,
            (codigo, nombre, pais),
        )


def sembrar_fila_de_prueba(conn: psycopg.Connection, region: str, rng: random.Random) -> None:
    # Inserta el cliente y la cuenta con UUID fijo de la región (idempotente).
    nombre = f"Cliente prueba {region}"
    conn.execute(
        """
        INSERT INTO cliente (region_apertura, id_cliente, nombre, documento, correo, telefono)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_cliente) DO NOTHING
        """,
        (
            region,
            CLIENTE_PRUEBA[region],
            nombre,
            documento_falso(rng),
            correo_falso(nombre, rng),
            telefono_falso(rng),
        ),
    )
    conn.execute(
        """
        INSERT INTO cuenta (region, num_cuenta, tipo_cuenta, saldo, fecha_apertura, id_cliente)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (region, num_cuenta) DO NOTHING
        """,
        (
            region,
            CUENTA_PRUEBA[region],
            "ahorro",
            1000.00,
            fecha_pasada(rng, 30),
            CLIENTE_PRUEBA[region],
        ),
    )


def sembrar_region(conn: psycopg.Connection, region: str, rng: random.Random) -> tuple[int, int, int]:
    # Puebla una región con clientes, cuentas y movimientos aleatorios.
    n_clientes = n_cuentas = n_movimientos = 0

    sembrar_fila_de_prueba(conn, region, rng)

    for _ in range(N_CLIENTES_POR_REGION):
        id_cliente = str(uuid.uuid4())
        nombre = nombre_falso(rng)
        conn.execute(
            """
            INSERT INTO cliente (region_apertura, id_cliente, nombre, documento, correo, telefono)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                region,
                id_cliente,
                nombre,
                documento_falso(rng),
                correo_falso(nombre, rng),
                telefono_falso(rng),
            ),
        )
        n_clientes += 1

        for _ in range(rng.randint(1, 2)):  # 1-2 cuentas por cliente
            num_cuenta = str(uuid.uuid4())
            saldo_inicial = round(rng.uniform(0, 5000), 2)
            conn.execute(
                """
                INSERT INTO cuenta (region, num_cuenta, tipo_cuenta, saldo, fecha_apertura, id_cliente)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    region,
                    num_cuenta,
                    rng.choice(TIPOS_CUENTA),
                    saldo_inicial,
                    fecha_pasada(rng),
                    id_cliente,
                ),
            )
            n_cuentas += 1

            for _ in range(rng.randint(2, 6)):  # 2-6 movimientos por cuenta
                conn.execute(
                    """
                    INSERT INTO movimiento (region, id_movimiento, tipo_movimiento, monto, fecha, num_cuenta)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        region,  # copia denormalizada de cuenta.region
                        str(uuid.uuid4()),
                        rng.choice(TIPOS_MOVIMIENTO),
                        round(rng.uniform(5, 800), 2),
                        fecha_pasada(rng, 400),
                        num_cuenta,
                    ),
                )
                n_movimientos += 1

    return n_clientes, n_cuentas, n_movimientos


def main() -> int:
    # Punto de entrada: parsea argumentos y orquesta el sembrado de las 3 regiones.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="vaciar las tablas antes de sembrar")
    parser.add_argument("--seed", type=int, default=42, help="semilla del generador (reproducibilidad)")
    args = parser.parse_args()

    rng = random.Random(args.seed)  # semilla fija: corridas reproducibles

    with psycopg.connect(autocommit=True) as conn:
        if args.reset:
            reset(conn)

        sembrar_catalogo(conn)
        print("catalogo_region: 3 filas (cr-sj, cr-limon, us-east)")

        total = (0, 0, 0)
        for region in REGIONES:  # siembra cada región y acumula los totales
            counts = sembrar_region(conn, region, rng)
            total = tuple(a + b for a, b in zip(total, counts))
            print(f"{region}: {counts[0]} clientes, {counts[1]} cuentas, {counts[2]} movimientos"
                  f" (+ 1 cliente/cuenta de prueba con UUID fijo)")

        print(f"\nTotal: {total[0]} clientes, {total[1]} cuentas, {total[2]} movimientos"
              " (sin contar filas de prueba)")
        print("Filas de prueba (UUID fijo, usadas por measure_latency.py):")
        for region in REGIONES:
            print(f"  {region}: cuenta {CUENTA_PRUEBA[region]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
