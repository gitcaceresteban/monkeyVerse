"""monkeyVerse v3 — an observable living planet.

Builds on v2 (a living planet: terrain, weather, disasters, species, learning
brains) with a focus on OBSERVABILITY: every agent can be selected, followed and
inspected; interactions are logged as explicit, filterable events; agents share
a discrete 10-symbol channel whose meaning is never hardcoded — only tracked
statistically, so the observer can see whether meaning emerged; and the clock
runs at a fixed real-time pace (ticks per second) instead of an unbounded
"speed" dial, so what you watch is what is actually happening.

Nothing social is programmed. Interaction *labels* (cooperation, flight,
territory...) are applied by the observer's chronicle after the fact, to
mechanical events the agents already produced on their own — they are analytics,
not behaviours handed to the agents.
"""

__version__ = "3.0.0"
