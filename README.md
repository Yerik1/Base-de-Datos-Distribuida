# Proyecto 1 — Opción A (Banca / billetera regional)

## E2 (implementación) y E3 (mediciones) — versión final, entorno Docker incluido

**Equipo:** Yerik Chaves Serrano (2022437493) · Emmanuel Esquivel Chavarría
(2022312336) · Jose Pablo Guerrero Duarte (2022099311)

Este repo es **autocontenido**: la infraestructura Docker (`docker-compose.yml`,
`Dockerfile.app-crdb`, `Makefile`, `.env.example`, `labs/lab1-cluster/`) vive
en la **raíz del repo**, junto a esta carpeta `p1-banca/`. Reutiliza el mismo
patrón del Lab 1 que pide el Proyecto 1 ("Fases B–C": clúster
CockroachDB ×3, imagen `app-crdb`, variables `PG*`), pero el esquema, el
seed, el script de medición y el verificador son propios del equipo — no son
los del Lab 1.

**Cómo está organizado este documento:** hay **dos guías completas e
independientes**, cada una de principio a fin — no hace falta saltar entre
ellas ni mezclar comandos:

- **[Guía A — Windows (PowerShell)](#guía-a--windows-powershell)**
- **[Guía B — Linux / macOS / WSL (bash)](#guía-b--linux--macos--wsl-bash)**

Elijan **una sola** según la terminal que estén usando y síganla completa.


```text
(raíz del repo)
├── docker-compose.yml           clúster CockroachDB ×3 (cr-sj, cr-limon, us-east) + app-crdb
├── Dockerfile.app-crdb          imagen cliente: python3 + psycopg + psql
├── Makefile                     make lab1-up / lab1-status / lab1-shell / lab1-license / lab1-down-v
├── .env.example                 COCKROACH_LICENSE / COCKROACH_ORGANIZATION (opcionales)
├── .gitignore
├── labs/lab1-cluster/
│   └── install_license.py       instala licencia docente si se define en .env
└── p1-banca/
    ├── README.md                 (este archivo)
    ├── sql/
    │   ├── 00_configurar_regiones.sql
    │   └── 01_schema.sql
    ├── scripts/
    │   ├── seed.py
    │   ├── measure_latency.py
    │   └── verify_p1.py
    └── evidence/                 se llena al ejecutar los pasos; no versionar
```

Esquema lógico, predicados de fragmentación, propiedades y réplica: ver el
**Entregable 1** (`Entregable_1_BDA.pdf`). Este README solo cubre la parte
de implementación (E2), medición (E3) y cómo levantar el entorno Docker; no
repite ese diseño.

**Requisito único para ambas guías:** Docker Desktop instalado y
**corriendo**, con puertos `26257` y `8080` libres en el host.

---
---

# Guía A — Windows (PowerShell)

Todos los comandos de esta guía son para **PowerShell** (`powershell.exe` o
`pwsh`, la terminal por defecto de Windows/VS Code). No usa `make` porque
Windows normalmente no lo trae instalado — todo se hace con `docker compose`
directo. Cada comando va en **una sola línea**; péguenlo tal cual, sin
partirlo.

## A0. Preparar el `.env`

```powershell
Copy-Item .env.example .env -ErrorAction SilentlyContinue
```

`.env` guarda `COCKROACH_LICENSE` / `COCKROACH_ORGANIZATION` (opcionales —
ver paso A1). No lo versionen ni lo peguen en capturas.

## A1. Levantar el clúster

```powershell
docker compose --profile lab1 up -d crdb-1 crdb-2 crdb-3
docker compose --profile lab1 run --rm --no-deps crdb-init
docker exec ti4601-crdb-1 cockroach node status --insecure --host=crdb-1:26257
```

**Resultado esperado:** 3 contenedores (`ti4601-crdb-1/2/3`) corriendo, 3
filas en la salida de `cockroach node status`, `is_live=true`, localidades
`cr-sj`, `cr-limon`, `us-east`. El segundo comando (`crdb-init`) inicializa
el clúster y crea la base `ti4601`; es seguro volver a correrlo, no falla si
el clúster ya estaba inicializado. Si falta un nodo, esperen 10-20 s y
repitan el tercer comando — no borren volúmenes.

Instalar la licencia docente (**opcional**: sin ella, CockroachDB corre bajo
su período de prueba automático para funciones multi-región — `REGIONAL BY
ROW` / `LOCALITY GLOBAL` funcionan igual, ya se comprobó — ver sección
"Estado de validación"):

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb python3 labs/lab1-cluster/install_license.py
```

## A2. Configurar las regiones de la base `ti4601`

Un solo comando, sin abrir `psql` a mano:

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb psql -X -v ON_ERROR_STOP=1 -f p1-banca/sql/00_configurar_regiones.sql
```

**Resultado esperado:** 3 filas, `cr-sj` como región primaria.

> Si alguna sentencia dice que la región ya existe, no la repitan a ciegas:
> revisen la salida de `SHOW REGIONS` (última tabla que imprime el comando)
> y sigan con lo que falte.

## A3. Aplicar el esquema propio (Fase B del E1)

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb psql -X -v ON_ERROR_STOP=1 -f p1-banca/sql/01_schema.sql -c "SHOW CREATE TABLE catalogo_region;" -c "SHOW CREATE TABLE cliente;" -c "SHOW CREATE TABLE cuenta;" -c "SHOW CREATE TABLE movimiento;"
```

**Resultado esperado:**

- `catalogo_region` termina en `LOCALITY GLOBAL`.
- `cliente` termina en `LOCALITY REGIONAL BY ROW AS region_apertura`.
- `cuenta` y `movimiento` terminan en `LOCALITY REGIONAL BY ROW AS region`.

Las tres decisiones físicas que se apartan literalmente del E1 (tipo
`crdb_internal_region`, llave compuesta `(region, …)`, FK compuesta de
`movimiento`) están explicadas en los comentarios de `sql/01_schema.sql`.

## A4. Cargar el dataset sintético (seed propio)

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/seed.py --reset
```

`--reset` vacía las 4 tablas antes de sembrar, así el dataset queda limpio y
reproducible (semilla fija, `--seed 42` por defecto).

**Resultado esperado:** el script imprime el conteo por región y termina sin
error (con la semilla por defecto: 150 clientes, 228 cuentas, ~937
movimientos en total, sin contar las filas de prueba).

## A5. Verificar antes de medir

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/verify_p1.py | Tee-Object -FilePath p1-banca/evidence/config-check.txt
```

**Meta:** `9/9` verificaciones en `[ OK ]`. Si algo falla, corrijan ese paso
específico (el mensaje trae una pista) y repitan; el verificador no
modifica nada.

## A6. Evidencia de E2 

Este paso necesita el prompt interactivo de `psql` (para poder usar `\o`), así
que primero abrimos una shell dentro del contenedor:

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb bash
```

Ya **dentro del contenedor** (el prompt cambia a algo como `root@...:/workspace#`):

```bash
psql -X -v ON_ERROR_STOP=1
```

Ya **dentro de psql** (prompt `root=#`), pegar todo este bloque tal cual:

```sql
\o p1-banca/evidence/schema-evidence.txt
SHOW REGIONS FROM DATABASE ti4601;
SHOW CREATE TABLE catalogo_region;
SHOW CREATE TABLE cliente;
SHOW CREATE TABLE cuenta;
SHOW CREATE TABLE movimiento;
SHOW RANGES FROM TABLE cuenta WITH DETAILS;
SHOW RANGES FROM TABLE movimiento WITH DETAILS;
\d cuenta
\o
```

Salir de psql y del contenedor:

```text
\q
exit
```

De vuelta en **PowerShell** (host), confirmar que el archivo se generó:

```powershell
if ((Get-Item p1-banca/evidence/schema-evidence.txt).Length -gt 0) { "Evidencia E2: OK" } else { "Evidencia E2: FALTA" }
```



## A7. Medir p50/p99 (E3)

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/measure_latency.py --runs 50 --warmup 5 --csv p1-banca/evidence/latency.csv | Tee-Object -FilePath p1-banca/evidence/latency-summary.txt
```

**Resultado esperado:** `p1-banca/evidence/latency.csv` con 201 líneas (1
cabecera + 200 muestras: 4 casos × 50 corridas) y un resumen en consola con
4 filas (`read/write` × `local/remote`), cada una con `p50_ms` y `p99_ms`.

```powershell
(Get-Content p1-banca/evidence/latency.csv | Measure-Object -Line).Lines
```



## A8. Apagar el entorno

```powershell
docker compose --profile lab1 down -v
```

`-v` borra los volúmenes de datos (`crdb1-data`, `crdb2-data`,
`crdb3-data`): el próximo `up` arranca un clúster completamente nuevo. Para
apagar sin borrar datos (conservar lo sembrado):

```powershell
docker compose --profile lab1 down
```



# E4 — Falla de sitio (nodo): RTO y RPO

`scripts/e4_failover.py` mide cuánto tarda el clúster en recuperar escrituras
después de perder el nodo de una región (RTO) y verifica que ninguna
escritura confirmada se haya perdido ni duplicado (RPO). Requiere que el
clúster ya esté arriba y sembrado (pasos 1-4 de su guía).

Necesitan **dos terminales** abiertas a la vez: una donde el script corre en
primer plano (no lo cierren hasta que termine), y otra donde ustedes,
como operador, derriban manualmente el nodo — el script se los pide con un
mensaje en pantalla y no lo hace por ustedes, para que quede como una acción
explícita con su propio timestamp.

> **Importante — `docker kill`, no `docker stop`.** `docker stop` manda
> `SIGTERM`, y CockroachDB reacciona a esa señal con un *drenado ordenado*:
> transfiere sus *leases* a otros nodos **antes** de apagarse, así que el
> cliente nunca nota interrupción (esto simula un mantenimiento planificado,
> no una falla). Ya lo comprobamos dos veces: con `docker stop` el script
> siempre termina reportando "no se detectó ninguna caída", incluso con el
> nodo realmente detenido. `docker kill` manda `SIGKILL` de inmediato, sin
> darle chance de drenar nada, y ahí sí se ve un RTO real (la evidencia
> `e4-kill-log-v2.txt` de este repo muestra ~5.1 s). Usen `docker kill` para
> la corrida "oficial"; `docker stop` sirve como corrida de contraste para
> documentar que un apagado ordenado no genera downtime.

## Windows (PowerShell)

Terminal 1:

```powershell
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/e4_failover.py --region cr-limon --interval 0.5 --max-seconds 120 --csv p1-banca/evidence/e4-failover.csv | Tee-Object -FilePath p1-banca/evidence/e4-failover-log.txt
```

Cuando imprima `Ahora, en OTRA terminal, corra: docker stop ti4601-crdb-2`, en la **Terminal 2** corran en su lugar:

```powershell
docker kill ti4601-crdb-2
```

Cuando el script termine (reporta el "Resumen E4" con RTO y RPO), reinicien el nodo para dejar el clúster sano:

```powershell
docker start ti4601-crdb-2
docker exec ti4601-crdb-1 cockroach node status --insecure --host=crdb-1:26257
```



# Guía B — Linux / macOS / WSL (bash)

Todos los comandos de esta guía son para **bash** (Linux, macOS o WSL en
Windows). Usa los atajos del `Makefile`; cada target también tiene su
equivalente directo con `docker compose` por si no tienen `make` instalado.

## B0. Preparar el `.env`

```bash
test -f .env || cp .env.example .env
```

`.env` guarda `COCKROACH_LICENSE` / `COCKROACH_ORGANIZATION` (opcionales —
ver paso B1). No lo versionen ni lo peguen en capturas.

## B1. Levantar el clúster

```bash
make lab1-up
make lab1-status
```

Equivalente sin `make`:

```bash
docker compose --profile lab1 up -d crdb-1 crdb-2 crdb-3
docker compose --profile lab1 run --rm --no-deps crdb-init
docker exec ti4601-crdb-1 cockroach node status --insecure --host=crdb-1:26257
```

**Resultado esperado:** 3 contenedores (`ti4601-crdb-1/2/3`) corriendo, 3
filas en `cockroach node status`, `is_live=true`, localidades `cr-sj`,
`cr-limon`, `us-east`. `crdb-init`/`lab1-up` inicializa el clúster y crea la
base `ti4601`; es seguro repetirlo. Si falta un nodo, esperen 10-20 s y
repitan `make lab1-status` — no borren volúmenes.

Instalar la licencia docente (**opcional**: sin ella, CockroachDB corre bajo
su período de prueba automático para funciones multi-región — `REGIONAL BY
ROW` / `LOCALITY GLOBAL` funcionan igual, ya se comprobó — ver sección
"Estado de validación"):

```bash
make lab1-license
```

Equivalente sin `make`:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb python3 labs/lab1-cluster/install_license.py
```

## B2. Configurar las regiones de la base `ti4601`

Un solo comando, sin abrir `psql` a mano:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb psql -X -v ON_ERROR_STOP=1 -f p1-banca/sql/00_configurar_regiones.sql
```

**Resultado esperado:** 3 filas, `cr-sj` como región primaria.

> Si alguna sentencia dice que la región ya existe, no la repitan a ciegas:
> revisen la salida de `SHOW REGIONS` (última tabla que imprime el comando)
> y sigan con lo que falte.

## B3. Aplicar el esquema propio (Fase B del E1)

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb psql -X -v ON_ERROR_STOP=1 -f p1-banca/sql/01_schema.sql -c "SHOW CREATE TABLE catalogo_region;" -c "SHOW CREATE TABLE cliente;" -c "SHOW CREATE TABLE cuenta;" -c "SHOW CREATE TABLE movimiento;"
```

**Resultado esperado:**

- `catalogo_region` termina en `LOCALITY GLOBAL`.
- `cliente` termina en `LOCALITY REGIONAL BY ROW AS region_apertura`.
- `cuenta` y `movimiento` terminan en `LOCALITY REGIONAL BY ROW AS region`.

Las tres decisiones físicas que se apartan literalmente del E1 (tipo
`crdb_internal_region`, llave compuesta `(region, …)`, FK compuesta de
`movimiento`) están explicadas en los comentarios de `sql/01_schema.sql`.

## B4. Cargar el dataset sintético (seed propio)

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/seed.py --reset
```

`--reset` vacía las 4 tablas antes de sembrar, así el dataset queda limpio y
reproducible (semilla fija, `--seed 42` por defecto).

**Resultado esperado:** el script imprime el conteo por región y termina sin
error (con la semilla por defecto: 150 clientes, 228 cuentas, ~937
movimientos en total, sin contar las filas de prueba).

## B5. Verificar antes de medir

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/verify_p1.py | tee p1-banca/evidence/config-check.txt
```

**Meta:** `9/9` verificaciones en `[ OK ]`. Si algo falla, corrijan ese paso
específico (el mensaje trae una pista) y repitan; el verificador no
modifica nada.

## B6. Evidencia de E2 

```bash
make lab1-shell
```

Equivalente sin `make`:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb bash
```

Ya **dentro del contenedor**:

```bash
psql -X -v ON_ERROR_STOP=1
```

Ya **dentro de psql** (prompt `root=#`), pegar todo este bloque tal cual:

```sql
\o p1-banca/evidence/schema-evidence.txt
SHOW REGIONS FROM DATABASE ti4601;
SHOW CREATE TABLE catalogo_region;
SHOW CREATE TABLE cliente;
SHOW CREATE TABLE cuenta;
SHOW CREATE TABLE movimiento;
SHOW RANGES FROM TABLE cuenta WITH DETAILS;
SHOW RANGES FROM TABLE movimiento WITH DETAILS;
\d cuenta
\o
```

Salir de psql y del contenedor:

```text
\q
exit
```

De vuelta en **bash** (host), confirmar que el archivo se generó:

```bash
test -s p1-banca/evidence/schema-evidence.txt && echo "Evidencia E2: OK" || echo "Evidencia E2: FALTA"
```



## B7. Medir p50/p99 (E3)

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/measure_latency.py --runs 50 --warmup 5 --csv p1-banca/evidence/latency.csv | tee p1-banca/evidence/latency-summary.txt
```

**Resultado esperado:** `p1-banca/evidence/latency.csv` con 201 líneas (1
cabecera + 200 muestras: 4 casos × 50 corridas) y un resumen en consola con
4 filas (`read/write` × `local/remote`), cada una con `p50_ms` y `p99_ms`.

```bash
wc -l p1-banca/evidence/latency.csv
```


## B8. Apagar el entorno

```bash
make lab1-down-v
```

Equivalente sin `make`:

```bash
docker compose --profile lab1 down -v
```

`-v` borra los volúmenes de datos (`crdb1-data`, `crdb2-data`,
`crdb3-data`): el próximo `lab1-up` arranca un clúster completamente nuevo.
Para apagar sin borrar datos (conservar lo sembrado):

```bash
make lab1-down
```

# E4 — Falla de sitio (nodo): RTO y RPO

## Linux / macOS / WSL (bash)

Terminal 1:

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1-banca/scripts/e4_failover.py --region cr-limon --interval 0.5 --max-seconds 120 --csv p1-banca/evidence/e4-failover.csv | tee p1-banca/evidence/e4-failover-log.txt
```

Cuando lo indique, en la **Terminal 2** corran en su lugar:

```bash
docker kill ti4601-crdb-2
```

Al terminar:

```bash
docker start ti4601-crdb-2
docker exec ti4601-crdb-1 cockroach node status --insecure --host=crdb-1:26257
```

## Parámetros

- `--region`: `cr-sj` | `cr-limon` | `us-east` — región cuyo nodo se derriba.
- `--interval`: segundos entre reintentos de escritura (por defecto 0.5).
- `--max-seconds`: duración total del monitoreo; si el script no alcanza a
  ver la recuperación, auméntenlo y repitan.
- `--csv`: ruta del archivo con la evidencia cruda (timestamp, intento,
  estado, latencia y error de cada intento).

**Resultado esperado:** el bloque final `=== Resumen E4 ===` reporta el RTO
observado (segundos entre la caída y la primera escritura rápida tras
recuperarse) y compara el saldo final contra el esperado según las
escrituras confirmadas — si coinciden, es evidencia de RPO = 0.

**Variante con `docker stop` (contraste, opcional):** repitan la misma
corrida sustituyendo `docker kill` por `docker stop` en la Terminal 2 y con
un `--csv` distinto, para dejar evidencia de que un apagado ordenado no
produce downtime — es un resultado válido y vale la pena discutirlo en el
informe, no es un fallo del experimento.

**Antes de repetir cualquiera de las dos corridas:** verifiquen con
`SHOW RANGES FROM TABLE cuenta WITH DETAILS;` (dentro de una sesión `psql`)
que el `lease_holder_locality` de la partición de la región que van a
derribar coincida con esa región. Después de un ciclo de falla/recuperación,
CockroachDB puede dejar el *lease* en el nodo al que migró y no regresarlo
solo a su región "hogar"; si el nodo que detienen ya no es el dueño real de
esa fila, el script no va a detectar ninguna caída aunque el nodo sí esté
abajo.

---
---


# Estado de validación

Todo el flujo de este README (pasos 1 a 7 de cualquiera de las dos guías) ya
se ejecutó de punta a punta sobre este mismo `docker-compose.yml`, sin
licencia (`COCKROACH_LICENSE` vacío):

- 3 nodos `is_live=true` con localidades `cr-sj` / `cr-limon` / `us-east`.
- `crdb-init` inicializó el clúster y creó `ti4601`.
- Las 3 regiones se configuraron y `01_schema.sql` aplicó sin errores:
  `catalogo_region` en `LOCALITY GLOBAL`, `cliente` en `REGIONAL BY ROW AS
  region_apertura`, `cuenta`/`movimiento` en `REGIONAL BY ROW AS region`.
- `seed.py --reset` cargó 150 clientes, 228 cuentas, 937 movimientos.
- `verify_p1.py` → **9/9** `[ OK ]`.
- `measure_latency.py` corrió y escribió CSV con las 4 combinaciones
  `read/write` × `local/remote`.


---

# Solución de problemas

| Síntoma | Guía | Acción |
| --- | --- | --- |
| `The token '\|\|' is not a valid statement separator` | Windows | pegaste un comando de la Guía B (bash) en PowerShell; usá el comando equivalente de la Guía A |
| `exec: "\\": executable file not found in $PATH` / `Python was not found; run without arguments to install from the Microsoft Store` | Windows | pegaste un comando con `\` de fin de línea (continuación de bash); PowerShell no lo interpreta así. Todos los comandos de la Guía A van en una sola línea — pegá la línea completa tal cual |
| Se abrió un prompt `>>>` de Python al correr `docker compose run app-crdb` sin nada más | ambas | eso es el REPL de Python interactivo (o `bash` si ya reconstruyeron la imagen); escriban `exit()` o Ctrl+D para salir, y vuelvan a correr el comando completo en una sola línea (`docker compose ... app-crdb python3 ruta/al/script.py`), no lo escriban dentro del `>>>` |
| `connection refused` | ambas | esperar 10-20 s; `docker compose --profile lab1 ps` |
| `region ... does not exist` al aplicar `01_schema.sql` | ambas | falta el paso 2 (configurar regiones) |
| `No existe la cuenta de prueba de <región>` en `measure_latency.py` | ambas | correr el paso 4 (`seed.py`) primero |
| `unknown command "/bin/sh" for "cockroach"` al tocar `docker-compose.yml` | ambas | el `entrypoint` del servicio `crdb-init` debe quedar en `["/bin/sh", "-c"]`; no lo borren |
| `make: command not found` | Windows | normal, Windows no trae `make`; usen la Guía A completa (no usa `make`) |
| puerto `26257` u `8080` ocupado | ambas | otro proceso/clúster usándolo; `docker compose --profile lab1 down` primero, o liberar el puerto |
| quieren reiniciar todo desde cero | ambas | paso 8 de su guía (`down -v`), y repetir desde el paso 1 (los volúmenes se borran) |
