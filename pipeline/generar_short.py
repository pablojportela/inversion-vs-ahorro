#!/usr/bin/env python3
"""
generar_short.py
Orquesta el pipeline completo de principio a fin: descarga los precios de
dos tickers (datos.py), simula el crecimiento de cada uno (calculo.py),
renderiza la gráfica comparativa animada (render.py) y, opcionalmente,
la cose con un hook cinemático y música de fondo (compose_short.py).

Uso mínimo (invertir 100€/mes en el S&P 500 vs ahorrar 100€/mes sin
invertir, solo gráfica, sin hook ni música). Por defecto sale un Short de
~30s (27s de gráfica), el punto dulce de retención/repetición para este
formato en el algoritmo de Shorts:
    python pipeline/generar_short.py \
        --ticker-a SPY --etiqueta-a "Invertir en el S&P 500" \
        --ticker-b CASH --etiqueta-b "Ahorrar sin invertir" \
        --modo dca --aportacion 100 \
        --titulo "Invertir 100€/mes vs ahorrar 100€/mes" \
        --output output/short.mp4

`CASH` es un ticker especial (no se descarga de ninguna fuente): modela
dinero guardado sin invertir, con 0% de rendimiento nominal.

Uso completo (dos tickers reales, con hook y música, sobreescribiendo la
duración por defecto con una versión más corta y punchy de 20s):
    python pipeline/generar_short.py \
        --ticker-a SPY --etiqueta-a "Invertir (S&P 500)" \
        --ticker-b SHY --etiqueta-b "Ahorrar (bonos EEUU 1-3 años)" \
        --modo dca --aportacion 100 --fecha-inicio 2002-01-01 \
        --ajustar-inflacion --ipc-anual 0.03 \
        --titulo "Invertir vs ahorrar (2002-2024)" \
        --hook assets/hooks/hook_ejemplo.mp4 \
        --bgm assets/bgm/musica_ejemplo.mp3 \
        --duracion-grafica 17 --duracion-final 20 \
        --output output/short_final.mp4
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# pipeline/ no forma parte del paquete instalable: añadimos src/ al path
# para poder importar inversion_vs_ahorro sin necesidad de `pip install -e .`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from inversion_vs_ahorro import calculo, datos, render  # noqa: E402
from inversion_vs_ahorro.calculo import CalculoError  # noqa: E402
from inversion_vs_ahorro.datos import DatosError  # noqa: E402
from inversion_vs_ahorro.render import RenderError  # noqa: E402

import compose_short  # noqa: E402 - módulo hermano en pipeline/
from compose_short import ComposeError  # noqa: E402

logger = logging.getLogger(__name__)

# Duración por defecto pensada para el algoritmo de Shorts: YouTube permite
# hasta 3 minutos, pero para este formato (hook + cifra creciendo) el punto
# dulce de tasa de finalización/repetición está en 20-34s. 27s de gráfica +
# ~3s de hook = 30s totales, corto para verse entero y rejugable.
DURACION_GRAFICA_POR_DEFECTO = 27.0
DURACION_FINAL_POR_DEFECTO = 30.0

# Ticker especial (no es un ticker real, no se descarga de ninguna fuente):
# representa dinero ahorrado sin invertir, con 0% de rendimiento nominal.
# Se deja constancia explícita en los logs de que no son datos de mercado.
TICKER_AHORRO_SIN_RENDIMIENTO = "CASH"


class GenerarShortError(Exception):
    """Error de orquestación: envuelve el fallo real de la etapa que falló."""


def _es_ahorro_sin_rendimiento(ticker: str) -> bool:
    return ticker.strip().upper() == TICKER_AHORRO_SIN_RENDIMIENTO


def _precios_ahorro_sin_rendimiento(fechas: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Serie de "precio" constante (1.0) alineada a `fechas`: no es un dato de
    mercado, es la asunción explícita de "dinero guardado sin invertir, sin
    rendimiento". Con precio constante, simular_crecimiento da como
    resultado exactamente el total aportado hasta la fecha (0% de interés).
    """
    logger.info(
        "Ticker '%s': no se descargan datos reales, se usa una asunción de "
        "0%% de rendimiento nominal (dinero guardado sin invertir).",
        TICKER_AHORRO_SIN_RENDIMIENTO,
    )
    return pd.DataFrame({"precio": 1.0}, index=fechas)


def generar_short(
    ticker_a: str,
    ticker_b: str,
    titulo: str,
    output_path: Path,
    etiqueta_a: str | None = None,
    etiqueta_b: str | None = None,
    modo: str = "dca",
    aportacion: float = 100.0,
    fecha_inicio: str = "2000-01-01",
    fecha_fin: str | None = None,
    ajustar_inflacion: bool = False,
    ipc_anual: float = 0.0,
    hook_path: Path | None = None,
    bgm_path: Path | None = None,
    duracion_grafica: float = DURACION_GRAFICA_POR_DEFECTO,
    duracion_final: float | None = DURACION_FINAL_POR_DEFECTO,
) -> Path:
    """
    Encadena datos.py -> calculo.py -> render.py -> compose_short.py para
    generar un Short completo a partir de dos tickers.

    `ticker_a` o `ticker_b` puede ser "CASH": no se descarga nada, se
    modela como dinero guardado sin invertir (0% de rendimiento nominal),
    para el escenario "invertir vs ahorrar sin invertir".

    Cualquier fallo en cualquier etapa (descarga, cálculo, render o
    ensamblado) se propaga envuelto en GenerarShortError con un mensaje
    que dice claramente en qué etapa ocurrió; nunca se deja un mp4 a
    medias en `output_path`.
    """
    if _es_ahorro_sin_rendimiento(ticker_a) and _es_ahorro_sin_rendimiento(ticker_b):
        raise GenerarShortError(
            f"Ambos tickers son '{TICKER_AHORRO_SIN_RENDIMIENTO}': no habría nada real que comparar."
        )

    etiqueta_a = etiqueta_a or (
        "Ahorrar sin invertir" if _es_ahorro_sin_rendimiento(ticker_a) else ticker_a
    )
    etiqueta_b = etiqueta_b or (
        "Ahorrar sin invertir" if _es_ahorro_sin_rendimiento(ticker_b) else ticker_b
    )
    output_path = Path(output_path)
    grafica_tmp_path = output_path.with_name(f"{output_path.stem}.grafica.tmp.mp4")

    try:
        logger.info("Descargando precios de %s y %s...", ticker_a, ticker_b)
        if _es_ahorro_sin_rendimiento(ticker_a):
            precios_b = datos.obtener_precios(ticker_b, fecha_inicio, fecha_fin)
            precios_a = _precios_ahorro_sin_rendimiento(precios_b.index)
        elif _es_ahorro_sin_rendimiento(ticker_b):
            precios_a = datos.obtener_precios(ticker_a, fecha_inicio, fecha_fin)
            precios_b = _precios_ahorro_sin_rendimiento(precios_a.index)
        else:
            precios_a = datos.obtener_precios(ticker_a, fecha_inicio, fecha_fin)
            precios_b = datos.obtener_precios(ticker_b, fecha_inicio, fecha_fin)
    except DatosError as exc:
        raise GenerarShortError(f"Fallo al descargar los precios: {exc}") from exc

    try:
        logger.info("Simulando crecimiento (modo=%s, aportación=%.2f)...", modo, aportacion)
        sim_a = calculo.simular_crecimiento(
            precios_a, modo, aportacion, ajustar_inflacion, ipc_anual
        )
        sim_b = calculo.simular_crecimiento(
            precios_b, modo, aportacion, ajustar_inflacion, ipc_anual
        )
    except CalculoError as exc:
        raise GenerarShortError(f"Fallo al simular el crecimiento: {exc}") from exc

    columna_valor = "valor_real" if ajustar_inflacion else "valor_nominal"

    try:
        logger.info("Renderizando la gráfica animada...")
        render.generar_video(
            sim_a,
            sim_b,
            titulo,
            grafica_tmp_path,
            duracion_seg=duracion_grafica,
            etiqueta_a=etiqueta_a,
            etiqueta_b=etiqueta_b,
            columna_valor=columna_valor,
        )
    except RenderError as exc:
        raise GenerarShortError(f"Fallo al renderizar la gráfica: {exc}") from exc

    try:
        logger.info("Ensamblando el Short final...")
        compose_short.componer_short(
            hook_path=hook_path,
            grafica_path=grafica_tmp_path,
            output_path=output_path,
            bgm_path=bgm_path,
            duracion_seg=duracion_final,
        )
    except ComposeError as exc:
        raise GenerarShortError(f"Fallo al ensamblar el Short final: {exc}") from exc
    finally:
        grafica_tmp_path.unlink(missing_ok=True)

    logger.info("Short generado en: %s", output_path)
    return output_path


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un Short completo (datos reales -> gráfica -> vídeo final) de principio a fin."
    )
    parser.add_argument(
        "--ticker-a", required=True,
        help="Ticker del primer escenario (p.ej. invertir), o 'CASH' para modelar ahorro sin invertir.",
    )
    parser.add_argument(
        "--ticker-b", required=True,
        help="Ticker del segundo escenario (p.ej. ahorrar), o 'CASH' para modelar ahorro sin invertir.",
    )
    parser.add_argument("--etiqueta-a", default=None, help="Nombre a mostrar para el ticker A (por defecto, el ticker).")
    parser.add_argument("--etiqueta-b", default=None, help="Nombre a mostrar para el ticker B (por defecto, el ticker).")
    parser.add_argument("--modo", choices=["unico", "dca"], default="dca", help="Aportación única o DCA mensual.")
    parser.add_argument("--aportacion", type=float, default=100.0, help="Importe aportado (una vez o cada mes).")
    parser.add_argument("--fecha-inicio", default="2000-01-01", help="Fecha de inicio (YYYY-MM-DD).")
    parser.add_argument("--fecha-fin", default=None, help="Fecha de fin (YYYY-MM-DD); por defecto, hoy.")
    parser.add_argument("--ajustar-inflacion", action="store_true", help="Mostrar crecimiento en términos reales.")
    parser.add_argument("--ipc-anual", type=float, default=0.0, help="Tasa de inflación anual constante (p.ej. 0.03 = 3%%).")
    parser.add_argument("--titulo", required=True, help="Título mostrado en la gráfica.")
    parser.add_argument("--hook", type=Path, default=None, help="Clip cinemático de Flow (opcional).")
    parser.add_argument("--bgm", type=Path, default=None, help="Música de fondo libre de derechos (opcional).")
    parser.add_argument(
        "--duracion-grafica", type=float, default=DURACION_GRAFICA_POR_DEFECTO,
        help="Duración de la animación de la gráfica, en segundos (por defecto, 27s: hook ~3s + gráfica = 30s totales, el punto dulce de retención para Shorts).",
    )
    parser.add_argument(
        "--duracion-final", type=float, default=DURACION_FINAL_POR_DEFECTO,
        help="Duración del Short final, en segundos (por defecto, 30s, el máximo recomendado para retención en Shorts de este formato).",
    )
    parser.add_argument("--output", type=Path, required=True, help="Ruta del mp4 final.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parsear_argumentos()
    try:
        generar_short(
            ticker_a=args.ticker_a,
            ticker_b=args.ticker_b,
            titulo=args.titulo,
            output_path=args.output,
            etiqueta_a=args.etiqueta_a,
            etiqueta_b=args.etiqueta_b,
            modo=args.modo,
            aportacion=args.aportacion,
            fecha_inicio=args.fecha_inicio,
            fecha_fin=args.fecha_fin,
            ajustar_inflacion=args.ajustar_inflacion,
            ipc_anual=args.ipc_anual,
            hook_path=args.hook,
            bgm_path=args.bgm,
            duracion_grafica=args.duracion_grafica,
            duracion_final=args.duracion_final,
        )
    except GenerarShortError as exc:
        logger.error("No se pudo generar el Short: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
