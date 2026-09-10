# CLAUDE.md — contexto de negocio y decisiones

Este fichero recoge el contexto y las decisiones ya tomadas sobre el
proyecto `inversion-vs-ahorro`, para que no se pierdan entre sesiones.

## Qué es esto

Pipeline en Python que genera Shorts de YouTube comparando el crecimiento
de invertir vs ahorrar (u otros escenarios: activo A vs activo B, DCA vs
aportación única, ajustado a inflación o no), usando datos históricos
reales desde el año 2000.

## Contexto de negocio

- **Nicho**: Shorts de finanzas. El RPM real de shorts de finanzas es
  bajísimo ($0.04-0.45), así que el proyecto **no busca rentabilidad
  rápida ahora mismo** — el objetivo es validar el formato antes de
  escalar.
- **Monetización**: YouTube exige 1.000 suscriptores + 10M
  visualizaciones de Shorts válidas en 90 días para poder monetizar —
  no antes. No hay atajos posibles a esto.
- **La gráfica de datos SIEMPRE se genera con matplotlib + ffmpeg** a
  partir de datos reales, **nunca con vídeo generativo** (Google
  Flow/Veo distorsiona cifras — ya probado y descartado para esto).
- **Google Flow** (con suscripción Pro) se usa **solo** para 2-3s de
  hook cinematográfico al principio del vídeo, **sin datos ni texto**,
  que luego se cose a la gráfica con `pipeline/compose_short.py`.
- **Nada de avatar ni voz IA hablando de finanzas**: rompe la política
  de monetización de Shorts de YouTube
  (https://support.google.com/youtube/answer/1311392).

## Decisiones técnicas ya tomadas

- **Stack**: Python 3.11+, pandas, yfinance (fuente principal de
  precios), Stooq (vía `pandas-datareader`) como fuente de respaldo,
  matplotlib para el render, ffmpeg/ffprobe (binarios de sistema, vía
  `subprocess`) para ensamblado y exportación de vídeo, pytest para
  tests.
- **Nada de MoviePy**: todo el ensamblado de vídeo pasa por llamadas
  directas a `ffmpeg`/`ffprobe` vía `subprocess`, tanto en
  `render.py` como en `pipeline/compose_short.py`. Se decidió así para
  mantener el pipeline con una sola dependencia de vídeo (el binario
  de ffmpeg) y control fino sobre los argumentos del encoder.
- **Ningún dato inventado o interpolado en silencio**: si `datos.py` no
  puede obtener precios reales (yfinance falla, Stooq también falla),
  se lanza una excepción clara (`DescargaFallidaError`). Nunca se
  devuelve un DataFrame vacío ni se rellenan huecos con datos
  ficticios sin dejar constancia explícita.
- **Caché de precios**: en `.cache_datos/` (parquet), con caducidad de
  `CACHE_TTL_HORAS` (24h por defecto) para no golpear a yfinance/Stooq
  en cada ejecución. Una caché corrupta se descarta automáticamente y
  se vuelve a descargar, sin propagar el error de lectura.
- **DCA** se interpreta como una aportación en el primer día de
  cotización de cada mes natural presente en los datos (no aportación
  diaria).
- **Ajuste por inflación**: acepta una tasa anual constante (float) o
  una serie por año (`pd.Series` indexada por año). El deflactado se
  compone día a día entre observaciones consecutivas usando la tasa
  del año en que cae cada tramo; si falta la tasa de un año que
  aparece en los datos, se lanza `CalculoError` en vez de asumir 0%.
- **Vídeos nunca corruptos en silencio**: tanto `render.py` como
  `pipeline/compose_short.py` validan el mp4 de salida con `ffprobe`
  (existencia, tamaño > 0, duración coherente) y borran cualquier
  fichero parcial si algo falla.

## Próximos pasos pendientes (no implementados aún)

- Selección real de tickers para cada escenario (inversión vs ahorro,
  activo A vs B) — por ahora los módulos son agnósticos al ticker
  concreto.
- Primeros hooks reales de Google Flow en `assets/hooks/` y música en
  `assets/bgm/` (carpetas vacías por ahora, con `.gitkeep`).

## Script de orquestación

`pipeline/generar_short.py` encadena `datos.py` → `calculo.py` →
`render.py` → `pipeline/compose_short.py` en un único comando:

```bash
python pipeline/generar_short.py \
    --ticker-a SPY --ticker-b CASH \
    --titulo "Invertir 100€/mes vs ahorrar 100€/mes" \
    --output output/short.mp4
```

El hook y la música son opcionales (`--hook`, `--bgm`); sin ellos, el
Short se genera solo con la gráfica. Cualquier fallo en cualquier etapa
se envuelve en `GenerarShortError` indicando en qué etapa ocurrió
(descarga, cálculo, render o ensamblado), y nunca deja un mp4 a medias
en la ruta de salida.

**Ticker especial `CASH`**: representa dinero guardado sin invertir
(0% de rendimiento nominal). No se descarga de ninguna fuente — se
construye una serie de precio constante alineada a las fechas del otro
ticker, y se deja constancia explícita en los logs de que no es un
dato de mercado. Es el escenario por defecto para "invertir vs ahorrar
sin invertir" que pidió el usuario en vez de comparar dos activos reales.

**Tickers reales recomendados** (verificados con historia desde el
año 2000 o cerca): `SPY` (S&P 500, ETF, ajustado por dividendos, desde
1993) para el lado de "invertir"; `SHY` (bonos EEUU 1-3 años, desde
2002) si se quiere un segundo activo real en vez de `CASH`. Ojo:
`URTH` (MSCI World) e `^IRX` (letra del tesoro) se descartaron como
ejemplos porque no tienen historia desde 2000 (URTH) o no son un precio
sino un tipo de interés (^IRX), incompatible con `calculo.py`.
