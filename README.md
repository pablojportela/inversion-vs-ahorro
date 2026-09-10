# inversión vs ahorro

Pipeline en Python para generar Shorts de YouTube que comparan el
crecimiento de invertir vs ahorrar (u otros escenarios: activo A vs
activo B, DCA vs aportación única, ajustado a inflación o no), usando
datos históricos reales desde 2000.

Sin IA generativa para los datos, sin avatar ni voz IA hablando de
finanzas. Ver `CLAUDE.md` para el contexto de negocio completo y las
decisiones ya tomadas.

## Estructura

```
src/inversion_vs_ahorro/
    datos.py     # descarga y cachea precios históricos (yfinance + fallback Stooq)
    calculo.py   # simula crecimiento: aportación única / DCA, ajuste inflación
    render.py    # anima la gráfica y exporta a mp4 9:16 (matplotlib + ffmpeg)
pipeline/
    compose_short.py  # ensambla el Short final: hook (Flow) + gráfica + música
assets/
    hooks/       # exports de Google Flow (2-3s cinemáticos, sin datos ni texto)
    bgm/         # música libre de derechos
docs/
    flow_hooks_prompts.md  # prompts de ejemplo para los hooks de Flow
tests/
```

## Requisitos

- Python 3.11+
- ffmpeg y ffprobe instalados en el sistema y accesibles en el PATH
  (`apt-get install ffmpeg` en Debian/Ubuntu)

```bash
pip install -r requirements.txt
```

## Uso rápido: generar un Short de principio a fin

`pipeline/generar_short.py` encadena todo el proceso (descarga de datos,
cálculo, render y ensamblado) en un único comando:

```bash
python pipeline/generar_short.py \
    --ticker-a SPY --etiqueta-a "Invertir en el S&P 500" \
    --ticker-b CASH --etiqueta-b "Ahorrar sin invertir" \
    --modo dca --aportacion 100 \
    --titulo "Invertir 100€/mes vs ahorrar 100€/mes" \
    --hook assets/hooks/hook_ejemplo.mp4 \
    --bgm assets/bgm/musica_ejemplo.mp3 \
    --output output/short_final.mp4
```

`--hook` y `--bgm` son opcionales: sin ellos, el Short se genera solo
con la gráfica animada (útil mientras no tengas todavía un clip de Flow).

`CASH` es un ticker especial (no se descarga de ninguna fuente, no es un
dato de mercado): modela dinero guardado sin invertir, con 0% de
rendimiento nominal, para el escenario "invertir vs ahorrar sin invertir".
Para comparar dos activos reales, usa dos tickers normales, p.ej.
`--ticker-a SPY --ticker-b SHY`.

## Uso por piezas (para más control)

```python
from inversion_vs_ahorro import datos, calculo, render

precios_msci = datos.obtener_precios("URTH", "2000-01-01")
precios_ahorro = datos.obtener_precios("^IRX", "2000-01-01")  # ejemplo

sim_inversion = calculo.simular_crecimiento(precios_msci, "dca", aportacion=100.0)
sim_ahorro = calculo.simular_crecimiento(precios_ahorro, "dca", aportacion=100.0)

render.generar_video(
    sim_inversion, sim_ahorro,
    titulo="Invertir vs ahorrar (2000-2024)",
    output_path="output/grafica.mp4",
    duracion_seg=8,
)
```

Después, `pipeline/compose_short.py` cose esa gráfica con un hook
cinemático (`assets/hooks/`) y música de fondo (`assets/bgm/`):

```bash
python pipeline/compose_short.py \
    --hook assets/hooks/hook_ejemplo.mp4 \
    --grafica output/grafica.mp4 \
    --bgm assets/bgm/musica_ejemplo.mp3 \
    --output output/short_final.mp4
```

## Tests

```bash
pytest
```
