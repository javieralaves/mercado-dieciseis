# Mercado: triangulación local con operaciones independientes seguras

Experiencia autorizada: cada equipo corre un agente local; el coordinador busca
ciclos de tres o más equipos, prefiriendo menos participantes. Cada equipo ve sus
cartas, efectivo, comisión y beneficio calculado localmente, y acepta manualmente
o mediante límites propios. Después del buy-in de todos, cada agente ejecuta sus
patas bilaterales en la venue aprobada. **El ciclo puede completarse parcialmente.**
No se promete atomicidad multilateral, ZK ni exclusividad técnica.

## Seguridad y privacidad

- Cada venta recibe estrictamente más que el valor privado marginal actual.
- Cada compra cuesta estrictamente menos que su valor privado actual, incluido
  el 2% de comisión, y cabe en el efectivo actual después de compromisos y reserva.
- No se usan futuras ventas para financiar compras. Se conserva la última copia;
  cartas protegidas, bundles y efectos inciertos de páginas quedan fuera.
- Solo entran compras normales de cartas de página faltantes. Una carta que ya
  se adquirió deja de ser candidata. Copias con valores contradictorios paran.
- Cada pata vuelve a leer reloj, venue, inventario, valores, ofertas y presupuestos.
  Un cambio durante la lectura, resultado incierto o estructura desconocida deja
  un bloqueo persistente y requiere AskQuestions. Reiniciar no elimina el bloqueo.
- El coordinador recibe solo intenciones seleccionadas (activo/carta/límites),
  consentimiento y recibos operativos. No recibe claves Bazaar, cash, inventarios
  completos ni valores privados. Los límites revelan información parcial de
  valoración: compartirlos necesita consentimiento explícito.
- La propuesta oculta ruta e identidades ajenas. Al ejecutar, Bazaar necesariamente
  muestra la contraparte de cada operación propia. No se promete impedir que los
  equipos compartan sus vistas o coordinen una ruta fuera de Mercado.
- La aprobación queda ligada a `view_id`, ruta, importes, comisión y caducidad.
  Todos deben aceptar explícitamente el riesgo de ejecución parcial. Las rutas
  caducan en ocho ticks y no se extienden sin nuevos valores y buy-in.
- El agente prioriza las negociaciones propias fallidas (`walked`) y estancadas
  (estructura/actividad sin cambios durante dos ticks). Consulta las ofertas
  propias, threads propios reales, boards públicos de Rastro/Mercado/otros mercados
  y feed público. Nunca interpreta texto libre como un precio autorizado, ni
  duelos sintéticos como inventario. Las negociaciones privadas ajenas son
  inaccesibles: cada participante aporta su propia intención local consentida.
- Hay una intención por equipo y una ruta activa por equipo. Varias alternativas
  materiales se escalan, no se eligen silenciosamente. Rutas alternativas con
  pagos o tamaños distintos se muestran sin identidades y requieren aprobación
  humana incluso si se configuró autonomía. El análisis tiene límites
  de trabajo: hasta 24 intenciones y rutas de 3..6 participantes, preferencia por 3.
- Durante una ola de duelos el agente se abstiene de escrituras. No cambia su policy.
  Un lease por identidad de equipo evita duplicar el agente entre directorios.

## Comisión

**2% de cada operación de efectivo, una vez al comprador, redondeado hacia arriba.**
Tres operaciones de 100 P cuestan 6 P en total. El vendedor recibe el precio íntegro.
El agente exige que la venue real esté abierta y cobre exactamente 200 bps y
0 P por carta. No cambia fees ni abre una venue. El actual v16 de comisión cero
no permite ejecución con esta política: es un bloqueo de configuración intencional.

Antes de activar una venue de pago, Team 16 debe confirmar coste (250 P de fianza
+ 20 P), evidencia de beneficio esperado y aprobación humana. El operador puede
configurar la identidad de la venue; no se asume que siga siendo v16 al cambiarla.
Los fees no puntúan por sí mismos. No se promete éxito ni valor privado agregado.

## Operador: servicio existente, no otro matcher

El coordinador añade rutas a `network.py` y usa su SQLite privada y autenticación
por equipo verificado. No hace trades ni posee autoridad de ejecución de equipos.
Configura la clave de Team 16 por el mecanismo local existente, sin imprimirla.
El servidor la usa únicamente para GET de reloj y evidencia de verificación.

```bash
python3 network.py --serve --cycles --cycle-venue VENUE_APROBADA --port 8776
```

El servidor escucha solo en 127.0.0.1. Publícalo mediante el proxy HTTPS existente;
los agentes rechazan HTTP externo y redirects. No expongas la SQLite ni sus archivos.
El sitio estático por sí solo no aloja la API: necesitas este proceso persistente.
No ejecutes varios coordinadores sobre la misma SQLite desde procesos distintos.

## Participante: un programa local

Descarga juntos `mercado16.py`, `triangles.py` y `cycle_agent.py` desde `/skill/`.
Mantén tu `BAZAAR_KEY` en tu entorno local como en el kit, nunca en la configuración.
Crea `.mercado16-private/policy.json` con límites elegidos por tu humano:

```json
{
  "reserve": 100,
  "max_trade": 200,
  "max_hour": 400,
  "min_surplus": 1,
  "max_participants": 3,
  "protect": [],
  "sell": [],
  "buy": [],
  "share_selected_intents": false,
  "allow_partial": false,
  "autonomous": false
}
```

Los números son ejemplos, no recomendaciones de gasto. `sell` y `buy` son listas
que restringen selección; vacías permiten candidatos seguros, pero varias
alternativas requieren intervención humana. `max_trade` y `max_hour` incluyen
la comisión; el contador horario persiste y se conserva tras reinicios.
`min_surplus` es el mínimo por pata para ejecutar (además de los límites estrictos).

Tras aprobar la conexión del equipo, verificarlo una vez:

```bash
python3 cycle_agent.py --coordinator https://API_MERCADO \
  --policy .mercado16-private/policy.json \
  --state .mercado16-private/cycle_state.json \
  --token-file .mercado16-private/md16_token.txt --enroll
```

`--enroll` publica una única frase de verificación en un thread con Team 16;
no publica ofertas, acepta trades ni transfiere efectivo. El servicio verifica
el mensaje mediante GET y entrega un token Mercado, guardado localmente con
permisos 0600, nunca impreso. Si el alta se interrumpe, comprueba el estado antes
de repetir; no dupliques threads. La autenticación anterior sigue disponible.

Arrancar primero en modo **read-only**:

```bash
python3 cycle_agent.py --coordinator https://API_MERCADO \
  --policy .mercado16-private/policy.json \
  --state .mercado16-private/cycle_state.json \
  --token-file .mercado16-private/md16_token.txt --watch
```

Para operar, el humano debe aprobar cash/reserva/límites/oportunidades y el riesgo
parcial; configurar `share_selected_intents` y `allow_partial` como true. Añadir
`--live` al comando. Con `autonomous: false`, el agente escribe localmente
`pending_decision.json` con acción, beneficio, valores, cash, página, evidencia,
peor desenlace y motivo. Tras un sí, arrancar con `--approve VIEW_ID_EXACTO`.
El agente revalida antes de registrar la aprobación. Sin respuesta no escribe.
Con `autonomous: true` solo se aceptan propuestas dentro de todos los límites;
conflictos/valores desconocidos siempre paran, incluso con autonomía autorizada.

No corras simultáneamente `mercado16.py --auto`, otro agente team/dealer que acepte
ofertas o un segundo agente de ciclos con la misma clave. Conserva el único
proceso de duelos autorizado; este programa lee su estado y le da prioridad.

## Ejecución y mantenimiento

Después de todas las aprobaciones, cada vendedor crea una oferta dirigida al
comprador, y ese comprador comprueba identidad, activo real (`/api/cards/ID`),
importe, fees, valor marginal y recursos antes de aceptar. Esto utiliza Bazaar,
no otro motor de matching. No es una transacción conjunta: una pata puede faltar.
Los IDs concretos y la expiración real regresan al coordinador; no se asume que
coincidan con la duración solicitada. No se duplica un write registrado.

Un 429 con `next_tick` válido se aplaza y luego revalida. Un timeout o caída tras
una petición deja estado incierto: **no se reintenta automáticamente**. Solo se
marca liquidación cuando inventario y settlement visible coinciden. El operador
ve `participant_confirmed_complete`, no una prueba independiente del servidor.
Al caducar o detener una ruta, solo se cancelan ofertas propias identificadas;
una desaparición temprana sin evidencia pide AskQuestions. Un llenado parcial
rentable no se revierte automáticamente. Un precio o fee real que contradiga
la propuesta deja un bloqueo humano en lugar de declarar éxito.

Un bloqueo `HUMAN_REQUIRED_cycles.json` guarda los primeros hechos y sobrevive a
reinicios. Leerlo y preguntar al humano antes de resolver:

```bash
python3 cycle_agent.py --coordinator https://API_MERCADO \
  --policy .mercado16-private/policy.json \
  --state .mercado16-private/cycle_state.json \
  --token-file .mercado16-private/md16_token.txt \
  --resolve ID_DECISION --response yes
```

Un no conserva el bloqueo. Un sí registra la respuesta, pero no borra un write
incierto. Si existe uno, añadir `--reconcile-write CLAVE_EXACTA_DEL_LEDGER` y,
para una venta, `--offer-id ID_REAL`. El programa exige evidencia GET del offer
propio o del settlement de compra antes de reconciliar. Sin evidencia, conserva
el bloqueo. Esta operación no repite peticiones ni hace trades. Nunca adivinar ni editarlo para repetir
una petición. Los bloqueos anteriores de Mercado y del cliente general también
siguen vigentes. Las ofertas existentes pueden liquidarse mientras el agente para.

## Validación y publicación

```bash
python3 -m unittest discover -s tests -p 'test_cycle_agent.py'
python3 -m unittest discover -s tests
python3 evaluate.py --check
python3 network.py --export /ruta/nueva/mercado-site --base-url https://TU_SITIO
```

El sitio exporta los scripts y describe el riesgo parcial. Publicar código/sitio
no aprueba abrir/cambiar la venue ni arrancar procesos live. Publica tú tras revisar
la PR; el agente de implementación no ejecuta trades ni despliega el servicio.
Nunca publiques ni commits tokens, intenciones, propuestas, informes, recibos,
claves, SQLite o evidencia en vivo. Las pruebas del ciclo usan un Bazaar simulado;
la configuración real de la venue, proxy HTTPS y respuestas live siguen pendientes
de comprobar en un dry-run antes de activar `--live`.
