"""
datos.py
Descarga y cachea precios históricos de activos financieros.

Fuente principal: yfinance. Fallback: Stooq (vía su endpoint CSV público).
Nunca se generan datos ficticios: si ambas fuentes fallan, se lanza
una excepción clara en lugar de devolver un DataFrame vacío o interpolado.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache_datos"
CACHE_TTL_HORAS = 24  # tras este tiempo, se vuelve a intentar la descarga
MAX_REINTENTOS = 3
ESPERA_INICIAL_SEG = 1.0


class DatosError(Exception):
    """Error base para el módulo de datos."""


class ParametrosInvalidosError(DatosError):
    """Los parámetros de entrada no son válidos (ticker vacío, fechas mal formadas...)."""


class DescargaFallidaError(DatosError):
    """Ni yfinance ni Stooq han podido servir los datos solicitados."""


def _validar_parametros(ticker: str, fecha_inicio: str, fecha_fin: str | None) -> tuple[date, date]:
    if not ticker or not ticker.strip():
        raise ParametrosInvalidosError("El ticker no puede estar vacío.")

    try:
        inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ParametrosInvalidosError(
            f"fecha_inicio '{fecha_inicio}' no tiene formato YYYY-MM-DD."
        ) from exc

    hoy = date.today()
    if fecha_fin is None:
        fin = hoy
    else:
        try:
            fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ParametrosInvalidosError(
                f"fecha_fin '{fecha_fin}' no tiene formato YYYY-MM-DD."
            ) from exc

    if inicio >= fin:
        raise ParametrosInvalidosError(
            f"fecha_inicio ({inicio}) debe ser anterior a fecha_fin ({fin})."
        )
    if fin > hoy:
        raise ParametrosInvalidosError(f"fecha_fin ({fin}) no puede ser una fecha futura.")
    if inicio > hoy:
        raise ParametrosInvalidosError(f"fecha_inicio ({inicio}) no puede ser una fecha futura.")

    return inicio, fin


def _ruta_cache(ticker: str, inicio: date, fin: date) -> Path:
    nombre = f"{ticker.upper()}_{inicio.isoformat()}_{fin.isoformat()}.parquet"
    return CACHE_DIR / nombre


def _cache_vigente(ruta: Path) -> bool:
    if not ruta.exists():
        return False
    edad_segundos = time.time() - ruta.stat().st_mtime
    return edad_segundos < CACHE_TTL_HORAS * 3600


def _leer_cache(ruta: Path) -> pd.DataFrame | None:
    """Lee la caché; si está corrupta, la descarta en vez de propagar el error."""
    try:
        df = pd.read_parquet(ruta)
    except Exception:
        logger.warning("Caché corrupta en %s: se descarta y se vuelve a descargar.", ruta)
        try:
            ruta.unlink()
        except OSError:
            pass
        return None
    if df.empty or "precio" not in df.columns:
        return None
    return df


def _descargar_yfinance(ticker: str, inicio: date, fin: date) -> pd.DataFrame:
    import yfinance as yf

    ultimo_error: Exception | None = None
    espera = ESPERA_INICIAL_SEG
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            # end es exclusivo en yfinance: sumamos un día para incluir fecha_fin
            datos = yf.download(
                ticker,
                start=inicio.isoformat(),
                end=(fin + timedelta(days=1)).isoformat(),
                auto_adjust=True,  # precio ajustado por dividendos y splits
                progress=False,
                threads=False,
            )
            if datos is None or datos.empty:
                raise DescargaFallidaError(f"yfinance no devolvió datos para '{ticker}'.")
            precios = datos["Close"]
            if isinstance(precios, pd.DataFrame):
                precios = precios.iloc[:, 0]
            resultado = precios.rename("precio").to_frame()
            resultado.index.name = "fecha"
            return resultado
        except Exception as exc:  # noqa: BLE001 - cualquier fallo de red o de la librería
            ultimo_error = exc
            logger.warning(
                "Intento %d/%d de descarga con yfinance para '%s' falló: %s",
                intento, MAX_REINTENTOS, ticker, exc,
            )
            if intento < MAX_REINTENTOS:
                time.sleep(espera)
                espera *= 2

    raise DescargaFallidaError(
        f"yfinance falló tras {MAX_REINTENTOS} intentos para '{ticker}': {ultimo_error}"
    ) from ultimo_error


def _descargar_stooq(ticker: str, inicio: date, fin: date) -> pd.DataFrame:
    """
    Descarga el histórico diario directamente del endpoint CSV público de
    Stooq (https://stooq.com/q/d/l/). No se usa pandas_datareader porque
    las versiones recientes ya no incluyen el lector de Stooq.
    """
    import io

    import requests

    url = (
        "https://stooq.com/q/d/l/"
        f"?s={ticker.lower()}&d1={inicio.strftime('%Y%m%d')}&d2={fin.strftime('%Y%m%d')}&i=d"
    )
    try:
        respuesta = requests.get(url, timeout=15)
        respuesta.raise_for_status()
    except requests.RequestException as exc:
        raise DescargaFallidaError(f"Stooq falló para '{ticker}': {exc}") from exc

    texto = respuesta.text.strip()
    # Stooq devuelve un cuerpo de error en texto plano (p.ej. "Brak danych")
    # en lugar de un CSV cuando el ticker no existe o no hay datos.
    if not texto or "Date,Open" not in texto.splitlines()[0]:
        raise DescargaFallidaError(f"Stooq no devolvió un CSV válido para '{ticker}': '{texto[:100]}'.")

    try:
        datos = pd.read_csv(io.StringIO(texto), parse_dates=["Date"], index_col="Date")
    except Exception as exc:  # noqa: BLE001 - CSV corrupto o con formato inesperado
        raise DescargaFallidaError(f"No se pudo interpretar el CSV de Stooq para '{ticker}': {exc}") from exc

    if datos.empty or "Close" not in datos.columns:
        raise DescargaFallidaError(f"Stooq no devolvió datos para '{ticker}'.")

    datos = datos.sort_index()
    resultado = datos["Close"].rename("precio").to_frame()
    resultado.index.name = "fecha"
    return resultado


def obtener_precios(
    ticker: str,
    fecha_inicio: str = "2000-01-01",
    fecha_fin: str | None = None,
    usar_cache: bool = True,
) -> pd.DataFrame:
    """
    Devuelve el histórico de precios ajustados (dividendos y splits) de
    `ticker` entre fecha_inicio y fecha_fin (ambas 'YYYY-MM-DD').

    Fuente principal: yfinance. Si falla (rate limit, sin conexión, ticker
    inexistente), reintenta con backoff exponencial y después recurre a
    Stooq. Si ninguna de las dos fuentes sirve datos, lanza
    DescargaFallidaError: nunca se devuelve un DataFrame vacío ni con datos
    interpolados en silencio.

    El resultado se cachea en disco (parquet) para no repetir descargas
    mientras la caché no haya caducado (CACHE_TTL_HORAS).
    """
    ticker = ticker.strip().upper()
    inicio, fin = _validar_parametros(ticker, fecha_inicio, fecha_fin)

    ruta = _ruta_cache(ticker, inicio, fin)
    if usar_cache and _cache_vigente(ruta):
        cacheado = _leer_cache(ruta)
        if cacheado is not None:
            logger.info("Usando caché vigente para %s (%s).", ticker, ruta)
            return cacheado

    try:
        resultado = _descargar_yfinance(ticker, inicio, fin)
        fuente = "yfinance"
    except DescargaFallidaError as error_yf:
        logger.warning("Fallback a Stooq para '%s' tras fallo de yfinance.", ticker)
        try:
            resultado = _descargar_stooq(ticker, inicio, fin)
            fuente = "stooq"
        except DescargaFallidaError as error_stooq:
            raise DescargaFallidaError(
                f"No se pudieron obtener precios para '{ticker}' entre {inicio} y {fin}. "
                f"yfinance: {error_yf}. Stooq: {error_stooq}."
            ) from error_stooq

    logger.info("Datos de %s obtenidos vía %s (%d filas).", ticker, fuente, len(resultado))

    if usar_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        resultado.to_parquet(ruta)

    return resultado
