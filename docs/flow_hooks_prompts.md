# Prompts para hooks cinemáticos (Google Flow)

Este documento recoge prompts de ejemplo para generar, con Google Flow
(suscripción Pro), los 2-3 segundos de hook cinematográfico que se cosen
al principio de cada Short, antes de la gráfica de datos reales.

## Reglas no negociables

- **Nunca** incluir cifras, porcentajes, ejes ni texto superpuesto en el
  clip de Flow: los datos reales solo se muestran en la gráfica generada
  con matplotlib a partir de `datos.py` + `calculo.py`. Flow distorsiona
  cifras y no puede usarse como fuente visual de datos.
- **Nunca** generar un avatar o voz IA hablando de finanzas: rompe la
  política de monetización de Shorts de YouTube
  (https://support.google.com/youtube/answer/1311392). El hook es mudo o,
  como mucho, ambiental (sin diálogo, sin narración).
- Duración objetivo: 2-3 segundos. Se recorta en `compose_short.py` si el
  export de Flow es más largo.
- Formato de exportación: vertical, apto para recortar/rellenar a
  1080x1920 (9:16) sin perder el encuadre principal.
- Guardar los exports en `assets/hooks/` con un nombre descriptivo, p. ej.
  `hook_reloj_arena_2024-01.mp4`.

## Prompts de ejemplo

### Ahorro vs inversión (concepto: tiempo/paciencia)
```
Un reloj de arena dorado sobre una mesa de mármol oscuro, la arena cayendo
lentamente, luz cálida y cinematográfica de lado, fondo desenfocado,
cámara fija, sin texto, sin personas, 2 segundos, look de anuncio premium.
```

### Crecimiento compuesto (concepto: semilla/árbol)
```
Time-lapse fotorrealista de una semilla germinando y creciendo hasta un
brote pequeño, tierra oscura y húmeda, luz de amanecer entrando desde un
lateral, cámara macro fija, sin texto, sin logotipos, 2-3 segundos.
```

### Comparativa de dos caminos (concepto: bifurcación)
```
Plano aéreo cinematográfico de un camino que se bifurca en un paisaje
minimalista (desierto o campo nevado), luz dorada de atardecer, cámara
dron descendiendo lentamente, sin texto, sin personas, 2-3 segundos.
```

### Activo A vs activo B (concepto: balanza)
```
Una balanza antigua de bronce en equilibrio, fondo negro de estudio, luz
puntual dramática tipo claroscuro, partículas de polvo flotando en el
haz de luz, cámara fija, sin texto, 2 segundos.
```

## Checklist antes de aceptar un export de Flow

- [ ] No aparecen números, gráficas ni texto en ningún fotograma.
- [ ] No hay ninguna figura humana hablando o gesticulando como si narrara.
- [ ] Duración entre 2 y 3 segundos (o recortable a ese rango sin perder
      el encuadre principal).
- [ ] Resolución y encuadre compatibles con 9:16 tras `scale`+`pad` en
      `compose_short.py`.
- [ ] Guardado en `assets/hooks/` con nombre descriptivo y sin espacios.
