# 🔭 monkeyVerse v3 — el planeta observable

Tercera versión, en su propia rama junto a v1 y v2 (que quedan intactas). El
planeta de v3 corre en `main3.py` (puerto **8002** por defecto), sobre
`monkeyverse3/` y `web3/`, con su propia carpeta de datos `data3/`.

Si v1 y v2 ya están corriendo como servicios en tu Raspberry Pi (puertos 8000 y
8001), v3 puede convivir con ellas sin chocar: usa el 8002.

## Qué añade v3 frente a v2

El foco de esta versión es **observabilidad, lenguaje e interacciones**: dejar
de ver un punto en la pantalla y poder seguir a un individuo, escuchar su
"idioma", y leer la crónica de con quién interactuó y cuándo.

### 1. Tiempo real, no pasos/segundo

Se eliminó el dial de velocidad libre de v1/v2. Cada mundo corre a un **ritmo
fijo en tiempo real** (`tick_rate`, ticks por segundo, ajustable solo en un
rango pequeño al crearlo — por defecto 8/s). No hay "turbo": lo que ves es
literalmente lo que está pasando, para poder observar interacciones reales
entre individuos en vez de un resumen acelerado.

### 2. Selección y seguimiento de agentes

- Haz clic en cualquier punto del mapa (o elige uno en la pestaña **Agentes**)
  para abrir su ficha: ID, especie, edad, energía, generación, posición,
  **estado actual** (descansando, buscando comida, huyendo, reproduciéndose,
  cazando, interactuando, siguiendo…), memoria reciente, últimas interacciones,
  últimos sonidos emitidos, genes y "fitness" (número de hijos).
- **🎯 Seguir**: la cámara se centra y se acerca al individuo seleccionado.
- **◎ radios**: dibuja el radio de percepción del individuo seleccionado.
- **〰 trayectorias**: dibuja su recorrido reciente como una línea.

### 3. Lenguaje: diez símbolos, sin significado impuesto

Los agentes comparten un canal discreto de **10 símbolos (0-9)**. La pestaña
**Lenguaje** muestra una leyenda de referencia (0=neutral, 1=comida, 2=peligro,
3=pareja/reproducción, 4=seguir, 5=alejarse, 6=territorio, 7=ayuda, 8=amenaza,
9=exploración) — pero es solo eso, una leyenda para el observador. **El motor
no le da ningún efecto a ningún símbolo**: emitir "1" no hace aparecer comida.
Lo único que existe es un registro estadístico de qué símbolo emite cada
especie en qué contexto (¿había comida cerca? ¿peligro? ¿otro individuo?). Si
una especie termina asociando fuertemente un símbolo con un contexto, la
pestaña Lenguaje te lo muestra como un **significado medido, no programado**.

### 4. Sonido

Cada símbolo tiene un tono sintetizado corto (Web Audio, sin archivos de
audio: funciona sin conexión a internet). Actívalo con **🔊 sonido** y ajusta
el volumen. Prioriza el sonido del agente seleccionado y evita saturar con
docenas de voces simultáneas.

### 5. Interacciones explícitas

Cada encuentro, ataque, reproducción, señal emitida cerca de otro individuo o
asociación sostenida (seguimiento) queda registrado como un evento:
`{tick, agent_id, target_id, type, signal, result, energy_delta, x, y}`. La
pestaña **Interacciones** los lista con filtros por agente y por tipo. Estas
etiquetas (`cooperación`, `competencia`, `encuentro`…) las aplica el
**observador**, clasificando post-hoc lo que los agentes ya hicieron
mecánicamente — no son conductas que los agentes "sepan" ejecutar.

### 6. Cerebro más rico + aprendizaje

- **Modo cognitivo** al crear un mundo: `liviano` (más agentes, cerebro simple)
  o `avanzado` (cerebro más grande y tope de 100 agentes).
- La percepción ahora incluye una señal explícita de **peligro** (fuego/
  inundación cerca) además de todo lo de v2 (energía, edad, comida, otros
  agentes, señales, clima, memoria, densidad de población).
- El aprendizaje en vida (plasticidad modulada por recompensa) y la memoria
  episódica/social de v2 se mantienen igual.

### 7. Panel de análisis global

Pestaña **Estado** + endpoint `/analytics`: población, especies vivas y
extintas, generación máxima, edad promedio, causas de muerte acumuladas,
diversidad genética, diversidad de lenguaje, interacciones por tick, símbolos
más usados, especies más comunicativas y más exitosas, linajes dominantes.
El mapa de calor de movimiento y de vegetación viven en las capas del mundo
(ya visibles en el mapa).

### 8. Exportación de datos

Botón **⬇ exportar** (o `/api/simulations/{id}/export.json` /
`export.csv?table=interactions`): descarga agentes, interacciones, series
temporales e hitos para análisis externo (Python, Excel, lo que sea).

### 9. Interfaz móvil

En pantallas angostas, la barra lateral y el panel de análisis se convierten
en paneles deslizables (☰ y 📊 arriba a la derecha) para no tapar el mapa.

## Instalación en la Raspberry Pi

```bash
cd monkeyVerse
git pull
git checkout claude/digital-ecosystem-sim-v3-7zzf9w
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt   # si no existe ya
./run3.sh            # arranca en http://<ip>:8002
```

Para que quede 24/7 con systemd (convive con v1 y v2 si ya los tienes):

```bash
sudo cp deploy/monkeyverse3.service /etc/systemd/system/
sudo sed -i -e 's#User=pi#User=TU_USUARIO#' \
  -e 's#/home/pi/monkeyVerse#/ruta/real/a/monkeyVerse#g' \
  /etc/systemd/system/monkeyverse3.service
sudo systemctl daemon-reload
sudo systemctl enable --now monkeyverse3
```

## Notas de rendimiento

v3 es más pesado que v2 por agente (más entradas de percepción, registro de
interacciones y lenguaje). Por eso los valores por defecto son más
conservadores: `Población máxima = 300` (antes 550) y `Ritmo = 8 ticks/seg`
en tiempo real. En pruebas, a esa población el ritmo real se sostiene con
margen; si en tu Raspberry Pi ves que el "ritmo real" se queda muy por debajo
del solicitado, baja la población máxima o usa el modo cognitivo `liviano`
con menos agentes iniciales.

## Capa de análisis cognitivo (v3.1)

v3 dejó de ser un visualizador para convertirse en una **plataforma de estudio
de comportamiento y cognición emergente**. Al seleccionar un individuo, su ficha
ahora incluye:

- **Resumen narrativo automático** en lenguaje natural (edad vs. promedio,
  reproducción, cooperación, señales más usadas, ataques, estado actual).
- **Memoria episódica cronológica**: "Hace N ticks → encontró comida / comió
  (+35) / escuchó señal [7] / emitió señal [1] / atacó / fue atacado / se
  reprodujo / descubrió territorio".
- **Traza de decisión**: qué percibió (energía, comida, peligro, voces, vecino,
  memoria), qué categorías de entrada pesaron más en la red, qué neuronas se
  activaron, la acción resultante y su **confianza**.
- **Objetivos inferidos** (con estrellas), leídos de las salidas de la red —
  nunca programados: buscar comida/explorar, atacar/defender, reproducirse,
  comunicar, descansar.
- **Relaciones sociales**: por cada individuo recordado, relación
  (aliada/hostil/neutral), veces que ayudó/atacó, confianza y hace cuánto se
  vieron. De aquí pueden emerger alianzas y rivalidades reconocibles.
- **Estadísticas de combate**: ataques hechos/ganados/perdidos, daño promedio,
  energía obtenida, heridas recibidas, muertes provocadas.
- **Historial reproductivo**: hijos, hijos vivos, nietos, descendencia total
  (árbol genealógico completo). *(La reproducción es asexual, así que no hay
  "parejas".)*
- **Perfil de personalidad emergente**: agresividad, cooperación, curiosidad,
  exploración, territorialidad, sociabilidad, dominancia — todo **calculado del
  comportamiento histórico**, no fijado como parámetro.
- **Fitness evolutivo** compuesto (supervivencia, descendencia, energía,
  territorio, cooperación, combate, longevidad), no solo el número de hijos.
- **Línea temporal** del individuo (nacimiento, primera comida, primera señal,
  primer ataque, primera reproducción).
- **Métricas cognitivas reales** que reemplazan la vieja "complejidad = distancia
  a la inicial": entropía de activación, neuronas activas por decisión,
  diversidad de activación, estabilidad de decisión, complejidad y variabilidad
  conductual, índice de aprendizaje (cuánto movió la plasticidad los pesos) y
  tendencia de recompensa.

Además:

- **Seguimiento inteligente (documental)**: al pulsar "🎯 Seguir", la cámara se
  centra y acerca al individuo y aparece una tira en vivo con lo que **observa,
  decide, emite** y **con quién interactúa**.
- **Herramienta de comparación**: "⚖ Comparar" y elige un segundo individuo para
  ver genes, edad, personalidad, fitness, descendencia, cognición y resúmenes
  lado a lado, con el "ganador" de cada métrica resaltado.
- **Descubrimientos automáticos** (pestaña *Descubrim.*): el sistema compara
  ventanas temporales y detecta cambios cualitativos (nueva especie dominante,
  giro hacia la cooperación o el conflicto, cambio de estrategia alimenticia,
  símbolo que gana protagonismo, primera cadena de seguimiento).
- **Exportación científica**: "⬇ Agente" descarga el JSON completo de un
  individuo (incluidos los **pesos de su red neuronal**, memoria, eventos,
  decisiones, genealogía); "⬇ Especie" descarga toda la especie; el botón de
  exportar del planeta sigue dando el volcado global (agentes, interacciones,
  series, hitos).

### Rendimiento

Todo esto está pensado para **cientos de agentes**: los contadores baratos
(combate, personalidad, memoria social, eventos) se llevan para todos los
agentes, pero la introspección cara (traza de decisión, buffers de activación,
métricas cognitivas) **solo se registra para los agentes en foco** —el
seleccionado, el seguido o los comparados—, un puñado como mucho. El botón
**⚡ ligero** oculta los paneles de análisis más pesados si quieres máxima
fluidez, y cada sección de la ficha es plegable.

## Estabilidad y emergencia pura (ajustes v3.2)

Tras observar colapsos poblacionales muy bruscos (la población pasaba de ~240 a
~10 una y otra vez, un ciclo de sobreexplotación → hambruna → reseed), se
ajustó el equilibrio para que las poblaciones **se establezcan y se mantengan**
en lugar de estrellarse:

- Vegetación más resiliente (regeneración y valor nutritivo mayores) y buffer de
  comida al inicio, de modo que la capacidad de carga queda holgadamente por
  encima del suelo de génesis en cualquier terreno.
- Población inicial más baja (para no sobreexplotar un terreno pobre de golpe) y
  tope por defecto de 240.
- Umbral de especiación más alto (0.5) y una especie solo cuenta como tal cuando
  tiene ≥3 individuos vivos: así el número de especies refleja linajes reales y
  persistentes, en vez de dispararse a cientos por deriva genética.

En pruebas (varias semillas), la población ahora se establece en ~1.000 ticks y
se mantiene estable cerca del tope, con fluctuaciones suaves por clima y
desastres, sin volver a colapsar a casi cero.

### Emergencia pura (sin sesgos innatos)

Por defecto, **ninguna decisión de un agente está sesgada**: cada movimiento,
ataque o señal proviene únicamente de su cerebro (inicializado al azar, moldeado
por evolución y aprendizaje en vida). Las versiones anteriores añadían dos genes
de "temperamento" (`agg_bias`, `explore_bias`) directamente sobre las salidas de
la red, lo que era un atajo. Ahora eso está **desactivado por defecto**; puedes
reactivarlo con la opción *Sesgos innatos → sí* al crear un planeta si quieres
comparar. Verificado: sin sesgos, el comportamiento sigue diferenciándose por
evolución (no todos atacan) y los pesos rápidos siguen cambiando (los cerebros
sí aprenden en vida).

## Una nota honesta sobre "significado medido"

En poblaciones pequeñas o bajo mucho estrés (por ejemplo, cerca del colapso),
vas a ver que *todos* los símbolos aparecen correlacionados con "energía baja"
— eso no es un error, es que en ese momento casi todos los agentes están
famélicos casi todo el tiempo, así que cualquier cosa que digan coincide con
esa condición. Las correlaciones más interesantes (un símbolo específico
asociado a peligro, o a la cercanía de otro agente) emergen con más claridad
en poblaciones sanas y con más generaciones acumuladas.
