# 🐒 monkeyVerse

Un **laboratorio de vida artificial** persistente: un ecosistema digital en 2D,
de mundo abierto, que funciona de forma autónoma **24/7** (pensado para una
Raspberry Pi) y que puedes observar desde el navegador como una entidad
omnipresente.

No es un videojuego ni una IA tradicional. Es un experimento: se proporcionan
**solo las condiciones mínimas para la existencia y la evolución**, y se observa
si aparecen —por sí solos— comportamientos complejos como la comunicación, la
formación de grupos, la territorialidad, la cooperación o la competencia.

> **Principio rector:** ninguna conducta de alto nivel está programada. No existe
> código para "cooperar", "hablar", "liderar" ni "comerciar". Los agentes nacen
> casi en blanco, con un cerebro diminuto y unos pocos genes que **evolucionan**.
> Lo interesante es lo que emerge, no lo que se impone.

---

## Versiones

Cada versión vive en su propia rama y su propio puerto, sin pisarse:

| Versión | Puerto | Qué es | Detalle |
|--------|--------|--------|---------|
| **v1** | 8000 | El ecosistema base 24/7 | este README |
| **v2** | 8001 | Planeta vivo (clima, especies, catástrofes, línea de tiempo) | [README-v2.md](README-v2.md) |
| **v3** | 8002 | Planeta **observable** (seguir individuos, lenguaje, cognición) | [README-v3.md](README-v3.md) |
| **v4** | 8003 | **Isla Simple**: pequeña, lenta y muy observable — 20 agentes, sonidos sin significado impuesto, reproducción A+B con requisitos | [README-v4.md](README-v4.md) |

---

## ¿Qué es cada individuo?

Cada agente tiene únicamente las capacidades mínimas para existir:

| Capacidad | Cómo está implementada |
|---|---|
| **Percibir** (parcialmente) | Ve un pequeño parche local: comida alrededor, su energía/edad, señales cercanas y el individuo más próximo. |
| **Actuar** | Una red neuronal recurrente diminuta decide moverse, reproducirse y emitir señales. Nada más. |
| **Consumir energía** | Existir y moverse cuesta energía; comer la repone. Sin energía, muere. |
| **Recordar** | Un pequeño vector de memoria recurrente que la red actualiza cada paso. |
| **Reproducirse** | Reproducción asexual con **mutación** de pesos y genes. |
| **Morir** | Por inanición o por vejez. |
| **Adaptarse** | La selección natural sobre reproducción/muerte es la única "maestra". |

El **cerebro** (pesos de la red) y los **genes** (metabolismo, digestión, umbral
de reproducción, inversión parental, longevidad, tasa de mutación, color de
linaje) se heredan con variación. No hay objetivos ni recompensas: solo
sobrevivir y dejar descendencia.

### Comunicación emergente

Existe un **campo de señales** (varios canales) que los agentes pueden escribir y
leer. Al inicio las señales **no significan nada**. Si emitir o reaccionar a
ciertas señales resulta ventajoso para sobrevivir, la selección podría hacer que
adquieran un significado compartido. Nadie les enseña un lenguaje.

### Un mundo dinámico

El entorno cambia por sí solo: terreno heterogéneo con zonas fértiles, recursos
que crecen de forma logística, **estaciones** y **eventos climáticos** (sequías y
florecimientos) que obligan a las poblaciones a readaptarse continuamente.

---

## Instalación en la Raspberry Pi

```bash
git clone <URL-de-tu-repositorio> monkeyVerse
cd monkeyVerse
bash deploy/install-pi.sh
```

El instalador crea el entorno virtual, instala dependencias y (opcionalmente)
registra un servicio **systemd** para que arranque solo con la Pi y funcione 24/7.
Al terminar te muestra la dirección `http://<ip-de-tu-pi>:8000`.

### Ejecución manual (cualquier máquina)

```bash
./run.sh                      # crea .venv la primera vez y arranca
# o bien:
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
HOST=0.0.0.0 PORT=8000 ./.venv/bin/python main.py
```

Abre `http://<ip>:8000` desde cualquier dispositivo de tu red local.

---

## Cómo se usa (el observador omnipresente)

1. **Crea un mundo** con "＋ Nuevo mundo". Un menú te deja definir las condiciones
   iniciales (tamaño, población, escasez, mutación, estaciones, señales…). Cada
   parámetro tiene una descripción.
2. **Observa** el mundo en vivo: los puntos son individuos (el color codifica el
   linaje), el verde es el alimento. Arriba, estadísticas en tiempo real.
3. **Analiza** en el panel derecho: series históricas de población, natalidad,
   generación máxima y actividad de señales, además de los rasgos genéticos
   promedio de la población (puedes ver la evolución en directo).
4. **Interviene** en el ambiente (nunca en las decisiones): sembrar comida,
   provocar una sequía o un florecimiento, calmar el clima.
5. **Análisis de sensibilidad:** lanza **varios mundos en paralelo** con distintos
   parámetros y compáralos. Cada uno corre en su propio hilo y su propia base de
   datos.

Todo sigue corriendo aunque cierres el navegador. El servidor puede tener varias
simulaciones activas a la vez.

---

## Persistencia total

Cada mundo tiene su propia base de datos SQLite en `data/<id>.db` con la historia
completa:

- **Genealogía** de cada individuo (padre, generación, nacimiento y muerte, genes).
- **Series temporales** (población, energía, generación, natalidad/mortalidad,
  actividad de señales, comida total, clima…).
- **Eventos** (climáticos, intervenciones, génesis).
- **Snapshots** periódicos para **reanudar** exactamente donde quedó.

Al reiniciar la Raspberry Pi (o el servicio), monkeyVerse **retoma
automáticamente** todos los mundos que estaban activos desde su último snapshot.
El registro `data/registry.json` lista los mundos existentes.

Puedes analizar la historia después con cualquier herramienta que lea SQLite
(por ejemplo `sqlite3 data/<id>.db`), o desde la propia API (ver abajo).

---

## Ejecución sin interfaz (experimentos por lotes)

```bash
./.venv/bin/python run_headless.py --steps 5000 --pop 150 --seed 42
```

Útil para explorar parámetros rápidamente o para reproducir un mundo exacto con
una semilla fija.

---

## API (para tus propios análisis)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/config/schema` | Esquema y valores por defecto del menú. |
| GET | `/api/simulations` | Lista de mundos y su estado. |
| POST | `/api/simulations` | Crea un mundo (cuerpo JSON con la config). |
| DELETE | `/api/simulations/{id}` | Elimina un mundo y su historia. |
| GET | `/api/simulations/{id}/state` | Estado actual (una foto). |
| POST | `/api/simulations/{id}/control` | `{action: pause|resume|speed|snapshot, value}`. |
| POST | `/api/simulations/{id}/intervene` | `{kind: food|drought|bloom|calm, params}`. |
| GET | `/api/simulations/{id}/stats?since=` | Serie temporal para gráficos. |
| GET | `/api/simulations/{id}/events` | Últimos eventos. |
| GET | `/api/simulations/{id}/agent/{aid}` | Detalle + genealogía de un individuo. |
| WS  | `/ws/{id}` | Flujo en vivo del estado del mundo. |

---

## Arquitectura

```
main.py                 arranque (uvicorn)
monkeyverse/
  config.py             condiciones iniciales + esquema del menú
  genome.py             cerebro (red recurrente) + genes heredables + mutación
  world.py              terreno, recursos, estaciones, eventos, campo de señales
  simulation.py         el bucle: percibir → actuar → comer → reproducir → morir
  persistence.py        SQLite: genealogía, series, eventos, snapshots
  manager.py            varios mundos en paralelo (hilos) + reanudación 24/7
  server.py             API REST + WebSocket + estáticos
web/                    interfaz del observador (HTML/CSS/JS, sin dependencias)
deploy/                 servicio systemd + instalador para la Pi
```

Dependencias: `numpy`, `fastapi`, `uvicorn`. El frontend no usa CDNs, así que
funciona aunque la Pi no tenga salida a internet.

---

## Rendimiento en la Raspberry Pi

El coste depende sobre todo del número de individuos vivos. Los valores por
defecto (mundo 128×96, tope de 450 individuos) están pensados para correr con
holgura en una Pi 4/5. Si notas que va lenta, baja `Población máxima` o la
`Velocidad (pasos/seg)` al crear el mundo, o desde los controles en vivo. Varios
mundos en paralelo reparten el mismo núcleo, así que reduce la velocidad de cada
uno si lanzas muchos a la vez.

---

## Notas de diseño

- **Extinción vs. persistencia.** Un mundo puede colapsar por mala suerte
  evolutiva. Para que el laboratorio no se apague, si la población baja de
  `Población mínima` aparece vida nueva (una especie de migración/abiogénesis).
  Ponlo en `0` si prefieres permitir la extinción definitiva.
- **Nada de conductas impuestas.** Lo único "social" que se ofrece es percepción
  del vecino más próximo y un canal de señales sin significado. Cualquier
  estructura social que observes **emergió sola**.
```
