# 🌍 monkeyVerse v2 — un planeta vivo

Versión ampliada del laboratorio de vida artificial, pensada para **evolución
abierta a muy largo plazo** (meses o años, 24/7, en una Raspberry Pi). Convive
con la v1 en este mismo repositorio: la v1 sigue intacta (`main.py`, `monkeyverse/`,
`web/`), y la v2 vive aparte (`main2.py`, `monkeyverse2/`, `web2/`).

La filosofía es la misma y más radical: **no se programa ninguna conducta**. No
existe código para cooperación, competencia, familia, lenguaje, liderazgo,
economía, comercio, cultura, guerra, ciudades ni política. Solo se dan las
condiciones mínimas para existir; todo lo demás debe emerger de la interacción,
el aprendizaje y la evolución.

## Qué añade v2 frente a v1

| Sistema | Descripción |
|---|---|
| **Planeta con geografía** | Mapa de elevación fractal con **océanos y montañas** infranqueables, costas fértiles, pendientes que encarecen el movimiento. El terreno **erosiona** y puede reformarse. |
| **Clima y desastres** | Ciclo **día/noche** (la percepción se reduce de noche), **estaciones**, **lluvia/sequía** (paseo aleatorio del clima), **deriva climática** lenta, e **incendios que se propagan**, **inundaciones** y **terremotos**. |
| **Múltiples especies** | Las especies **no se definen**: se descubren. Cuando un linaje deriva genéticamente lo suficiente, **nace una especie nueva**; las especies también se **extinguen**. Árbol de la vida ramificado. |
| **Niveles tróficos** | Un gen de **dieta** (herbívoro↔carnívoro) hace emerger **depredación**, **carroñeo** (los cadáveres dejan carne) y competencia. La energía se conserva (la depredación no crea energía), lo que produce dinámicas **depredador-presa**. |
| **Aprendizaje en vida** | Además de evolucionar, cada cerebro **aprende durante su vida** por plasticidad modulada por recompensa (prueba y error), con **olvido** (los pesos rápidos decaen). |
| **Memoria episódica y social** | Recuerdan **lugares** de comida/peligro (limitado, con olvido y ruido → recuerdos distorsionados) y **a quién los atacó** (rencores → base para alianzas/rivalidades emergentes). |
| **Señales multimodales** | **Sonidos** transitorios, **feromonas** persistentes en el suelo y **color** visible. Sin significado inicial: pueden convertirse en comunicación. |
| **Economía incipiente** | Los individuos **almacenan** excedente de energía; atacar permite **robar** las reservas. Sustrato para intercambio/competencia emergentes. |
| **Crónica automática** | El sistema detecta y registra **hitos históricos**: primer nacimiento, primera muerte, primera depredación, primer carroñeo, primeras señales sostenidas, primera migración, primera comunidad, primera especiación, primera extinción, primeros desastres… |
| **Máquina del tiempo** | Guarda **fotogramas** periódicos del planeta; con un deslizador puedes **navegar el pasado** y ver cómo era el mundo en cualquier momento registrado. |
| **Modo dios** | El observador puede **sembrar** comida, provocar **lluvia/sequía/incendio/inundación/terremoto**, **elevar o hundir** terreno, lanzar un **meteoro**, **introducir una especie nueva** y **bifurcar el universo** (clonar un mundo en marcha para comparar líneas temporales), pero **nunca** controla la mente de los individuos. |

## Poner en marcha (Raspberry Pi)

```bash
git clone <URL-de-tu-repositorio> monkeyVerse
cd monkeyVerse
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./run2.sh            # arranca la v2 en http://<ip>:8000
```

Para 24/7 con systemd (arranca solo con la Pi y reanuda los planetas):

```bash
sudo cp deploy/monkeyverse2.service /etc/systemd/system/
# edita User= y las rutas si tu usuario no es 'pi'
sudo systemctl enable --now monkeyverse2
```

La v1 y la v2 usan el mismo `requirements.txt`. Puedes correr una u otra (o
ambas en puertos distintos con `PORT=...`).

## Cómo se usa

1. **Crea un planeta** con "＋ Nuevo planeta". El menú define geografía, clima,
   recursos, señales, aprendizaje y evolución. Cada campo tiene su descripción.
2. **Contempla** el mundo: mar, montañas, vegetación, incendios, día y noche.
   Los puntos son individuos; puedes colorearlos por **especie** o por **dieta**.
3. **Panel derecho:** *Estado* (estadísticas + niveles tróficos + rasgos genéticos),
   *Especies* (especies vivas con su color y población), *Crónica* (la historia
   detectada automáticamente) e *Historia* (gráficos temporales).
4. **Modo dios:** barra inferior con intervenciones ambientales. Algunas piden
   un clic en el mapa (sembrar, fuego, sismo, elevar, hundir, meteoro).
5. **Máquina del tiempo:** el deslizador inferior recorre el pasado del planeta.
   Pulsa "▶ En vivo" para volver al presente.
6. **Universos paralelos:** "🌱 bifurcar universo" clona el mundo actual para
   estudiar cómo divergen dos líneas temporales desde el mismo punto.

## Persistencia

Cada planeta tiene su base SQLite en `data2/<id>.db`: genealogía (con especie),
series temporales, eventos, **hitos históricos**, **fotogramas** para la máquina
del tiempo y **snapshots** para reanudar. Al reiniciar, todos los planetas
activos se **reanudan automáticamente** desde su último snapshot.

## Notas de diseño y rendimiento

- **Evolución abierta.** El entorno nunca es estático (clima, desastres, deriva),
  hay múltiples especies, aprendizaje individual y mutación acumulativa: todo
  orientado a que **sigan apareciendo novedades** incluso tras millones de ciclos.
- **Extinción vs. persistencia.** Si la población baja de `Población mínima`
  aparece vida nueva (migración/abiogénesis) para que el planeta no se apague;
  ponlo en `0` si quieres permitir la extinción total.
- **Coste en la Pi.** v2 es más pesada que v1 (mundo mayor, cerebros y percepción
  más ricos). Los valores por defecto (mundo 160×112, tope 550) apuntan a una Pi
  4/5. Si va lenta, baja `Población máxima`, el tamaño del mundo o la velocidad
  (pasos/seg), o corre menos planetas en paralelo.
- **Qué NO está programado.** Cooperación, lenguaje, cultura, comercio,
  territorios, jerarquías: nada de eso existe en el código. Si aparece, emergió.
  La v2 aporta el *sustrato* (señales, memoria social, almacenamiento, especies,
  presión ambiental) para que sea posible; descubrir si emerge es el experimento.
