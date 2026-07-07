# 🏝️ monkeyVerse v4 — Isla Simple

Cuarta versión, en su propia rama (`feature/v4-simple-island`) junto a v1, v2 y
v3, que quedan **intactas**. La Isla Simple corre en `main4.py` (puerto **8003**
por defecto), sobre `monkeyverse4/` y `web4/`, con su propia carpeta de datos
`data4/`.

Convive sin chocar con las versiones anteriores:

| Versión | Puerto | Carpeta | Servicio systemd |
|--------|--------|---------|------------------|
| v1 | 8000 | `monkeyverse/` | `monkeyverse.service` |
| v2 | 8001 | `monkeyverse2/` | `monkeyverse2.service` |
| v3 | 8002 | `monkeyverse3/` | `monkeyverse3.service` |
| **v4** | **8003** | **`monkeyverse4/`** | **`monkeyverse4.service`** |

## Qué es v4 (y en qué se diferencia)

v3 era un planeta grande, rápido y lleno de sistemas. v4 va en la dirección
**opuesta a propósito**: un mundo **pequeño, lento y muy observable** donde se
pueden ver las decisiones de cada individuo una por una. No hay depredadores, ni
fuego, ni catástrofes, ni clima. Solo una islita con vegetación, 20 agentes, y
tiempo para mirar cómo aprenden, se comunican y se emparejan.

### 1. El mundo: una isla pequeña

- Rejilla de ~50×50 con una mancha de tierra **ovalada rodeada de agua**.
- El agua **no mata**: es un borde blando. Si un agente intenta meterse al agua,
  rebota y se desvía (incluso hacia el centro de la isla si se queda atrapado en
  la orilla), así que el agua no es la causa principal de muerte.
- Vegetación que rebrota despacio, más rica hacia el centro. Hay comida de sobra
  para que **no mueran de hambre demasiado rápido**.

### 2. Los agentes: 20 individuos, dos sexos

Arranca con exactamente **10 tipo A + 10 tipo B**. Cada uno tiene: ID único,
sexo visible (A naranja / B azul), energía, hambre, edad, estado, posición, su
**propia red neuronal recurrente**, memoria interna, historial de interacciones
y de sonidos emitidos/oídos, **matriz de relaciones sociales**, genealogía y
unos pocos **genes fisiológicos heredables** (metabolismo, velocidad, tasa de
aprendizaje, longevidad — nada de genes de "conducta", para que el
comportamiento **emerja** del cerebro y no venga de fábrica).

### 3. Tiempo real y control de velocidad

A diferencia de v3 (que no tenía dial de velocidad), v4 sí lo tiene, porque su
objetivo es la observación: **⏸ pausa · 0.5× · 1× · 2× · 5×**. El ritmo base es
lento (3 ticks/segundo a 1×) para que cada decisión sea visible. La barra
espaciadora pausa/reanuda.

### 4. Cerebro recurrente y aprendizaje de por vida

Cada agente lleva una **GRU simplificada** (con memoria a corto plazo) que le
permite, en principio, asociar sonidos y contexto con consecuencias a lo largo
del tiempo. El núcleo recurrente es **heredable** (se cruza de ambos padres); el
aprendizaje **durante la vida** ocurre en la capa de salida como **plasticidad
modulada por recompensa** (pesos rápidos que refuerzan lo que acaba de funcionar
y se olvidan poco a poco). Sin backprop, sin objetivo: solo ensayo y error.

Recompensas: comer, sobrevivir, interacciones mutuas, reproducirse y que
sobreviva la cría → positivo. Hambre extrema y rachas de intentos fallidos →
negativo.

### 5. Sonido: diez tonos, **sin significado impuesto**

Los agentes comparten un canal de **10 sonidos (0-9)**, cada uno con un tono
audible distinto en el navegador (Web Audio, sin archivos, funciona offline). El
número del sonido aparece en una burbuja sobre el agente; el volumen depende de
la distancia (y sube si estás **siguiendo** a un agente).

**Este es el punto clave del proyecto:** el motor **no asume que ningún sonido
significa nada**. No hay tabla de significados. Se registra quién emitió, quién
oyó y qué pasó después, y *solo se mide* la relación. Un "posible significado
emergente" únicamente se marca si un sonido está fuertemente ligado a un
contexto **y** ese vínculo supera claramente la frecuencia base (prueba de
*lift*), de forma coherente con la información mutua. Si no hay evidencia, la
interfaz lo dice: *"todavía no hay evidencia de que ningún sonido signifique
nada"*.

### 6. Interacción social

Haz clic en un agente para seleccionarlo y **seguirlo** con la cámara. Su ficha
muestra estado, energía, genes, últimos sonidos emitidos/oídos, agentes
cercanos, y su **relación con cada conocido** (familiaridad, afinidad, confianza,
interacciones + / −, sonidos oídos). En el mapa se dibujan **líneas doradas**
entre agentes que interactúan y burbujas con el número de sonido.

### 7. Reproducción sexual A + B (con requisitos reales)

No basta la cercanía. Para que nazca una cría hacen falta: **dos sexos
distintos**, ambos vivos y **maduros**, con **energía suficiente**, **cerca**,
que **ya se hayan interactuado** antes (afinidad y nº de interacciones mínimos),
que **haya habido comunicación** (al menos una señal), fuera de **cooldown**, y
que **ambos elijan** activamente reproducirse (con una pequeña ventana de
cortejo para que la intención de la pareja no tenga que coincidir en el mismo
tick exacto). La cría **hereda** el cerebro y los genes de ambos padres con
pequeñas mutaciones, sexo aleatorio, y se registra con generación y padres A/B.

### 8. Paneles

- **Barra superior**: tick, población, A, B, nacimientos, muertes,
  reproducciones, vegetación, interacciones y sonidos por intervalo, diversidad,
  control de velocidad, audio, debug, reiniciar, nueva, exportar.
- **Agente**: todos los campos + decisión actual de la red + resumen de memoria.
- **Comunicación**: uso de cada sonido, más usado, diversidad (entropía),
  información mutua sonido↔contexto, matriz contexto/respuesta y significados
  emergentes (si los hay).
- **Reproducción**: intentos, éxitos, afinidad media previa, parejas más
  fecundas, requisitos y generaciones presentes.
- **Análisis**: lectura automática del mundo que **solo afirma lo que los datos
  sostienen**.

### 9. Modo debug (🐞)

Con el agente seleccionado, muestra las **entradas** de la red, las **salidas**
más activas, la acción elegida, la recompensa reciente y la norma de los pesos
rápidos (cuánto ha aprendido). Es el "por qué hizo lo que hizo".

### 10. Registro y exportación

Todo evento (nacimiento, muerte, movimiento, comer, emitir/oír sonido,
interacción, seguir, evitar, intento y éxito de reproducción…) se guarda en una
base **SQLite** por mundo (escritura por lotes, tamaño acotado para correr 24/7
en la Pi). Botones de exportación:

- **Run completo (JSON)** — configuración, métricas, comunicación, reproducción,
  análisis, agentes vivos y genealogía.
- **Eventos (CSV)** · **Métricas (CSV)** · **Genealogía (JSON)** · **Agentes
  vivos (JSON)**.

## Instalación en la Raspberry Pi

```bash
# desde el repo clonado, en la rama feature/v4-simple-island
git checkout feature/v4-simple-island
./deploy/install-v4-pi.sh          # crea/reutiliza .venv e instala el servicio 8003
# o, para probar sin servicio:
./run4.sh                          # arranca en el puerto 8003
```

Abre `http://<ip-de-la-pi>:8003` desde cualquier dispositivo de tu red. El
servicio `monkeyverse4.service` reinicia solo y arranca en el boot, así que
**sigue corriendo aunque cierres la sesión SSH** (esa fue la causa de que el
8001 "se apagara" en su día: el proceso moría con la sesión; systemd lo
resuelve).

Variables de entorno: `HOST` (por defecto `0.0.0.0`), `PORT` (8003),
`MONKEYVERSE_DATA` (`data4`).

## Criterios de éxito (todos cumplidos)

Abre en 8003 · 20 agentes (10A/10B) · terreno de isla · movimiento lento ·
selección y seguimiento · comen vegetación · emiten sonidos 0-9 audibles con el
número visible · oyen sonidos cercanos · se registra emisión/escucha ·
interacciones visibles · reproducción A+B con prerequisitos · descendencia
heredada · genealogías · descarga de run/CSV · paneles de comunicación,
reproducción, aprendizaje y relaciones · **ningún significado de sonido
hardcodeado**.

## Una nota honesta sobre el "significado"

Con cerebros nuevos y sin entrenar, los sonidos empiezan (y suelen quedarse
mucho tiempo) **ambiguos**: entropía alta e información mutua casi nula. Eso es
lo correcto y lo honesto — la interfaz **no fingirá** que un tono significa algo
hasta que los datos lo sostengan. Si en una corrida larga emerge una asociación
real, aparecerá marcada como "posible significado emergente", con su fuerza, su
*lift* sobre la base y su tamaño de muestra. Nunca antes.
