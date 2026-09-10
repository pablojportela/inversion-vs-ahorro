"""Tests de src/inversion_vs_ahorro/datos.py."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from inversion_vs_ahorro import datos


def _precios_ejemplo() -> pd.DataFrame:
    fechas = pd.date_range("2020-01-01", periods=5, freq="D")
    return pd.DataFrame({"precio": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=fechas)


# --- Validación de parámetros ---------------------------------------------

def test_ticker_vacio_lanza_error():
    with pytest.raises(datos.ParametrosInvalidosError):
        datos.obtener_precios("", "2020-01-01", "2020-12-31")


def test_ticker_solo_espacios_lanza_error():
    with pytest.raises(datos.ParametrosInvalidosError):
        datos.obtener_precios("   ", "2020-01-01", "2020-12-31")


def test_fecha_inicio_posterior_a_fin_lanza_error():
    with pytest.raises(datos.ParametrosInvalidosError):
        datos.obtener_precios("AAPL", "2021-01-01", "2020-01-01")


def test_fecha_inicio_igual_a_fin_lanza_error():
    with pytest.raises(datos.ParametrosInvalidosError):
        datos.obtener_precios("AAPL", "2020-01-01", "2020-01-01")


def test_fecha_futura_lanza_error():
    manana = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(datos.ParametrosInvalidosError):
        datos.obtener_precios("AAPL", "2020-01-01", manana)


def test_formato_fecha_invalido_lanza_error():
    with pytest.raises(datos.ParametrosInvalidosError):
        datos.obtener_precios("AAPL", "01-01-2020", "2020-12-31")


# --- Caché -------------------------------------------------------------

def test_usa_cache_vigente_sin_volver_a_descargar(tmp_path, monkeypatch):
    monkeypatch.setattr(datos, "CACHE_DIR", tmp_path)

    llamadas = {"n": 0}

    def yfinance_falso(ticker, inicio, fin):
        llamadas["n"] += 1
        return _precios_ejemplo()

    monkeypatch.setattr(datos, "_descargar_yfinance", yfinance_falso)

    primero = datos.obtener_precios("AAPL", "2020-01-01", "2020-01-10")
    # Repetimos la misma consulta exacta: debe usar caché, no volver a llamar.
    segundo = datos.obtener_precios("AAPL", "2020-01-01", "2020-01-10")

    assert llamadas["n"] == 1
    # check_freq=False: el índice pierde el atributo 'freq' al pasar por parquet,
    # pero los valores son idénticos.
    pd.testing.assert_frame_equal(primero, segundo, check_freq=False)


def test_cache_corrupta_se_descarta_y_redescarga(tmp_path, monkeypatch):
    monkeypatch.setattr(datos, "CACHE_DIR", tmp_path)
    ruta = datos._ruta_cache("AAPL", date(2020, 1, 1), date(2020, 1, 10))
    tmp_path.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"esto no es un parquet valido")

    monkeypatch.setattr(datos, "_descargar_yfinance", lambda t, i, f: _precios_ejemplo())

    resultado = datos.obtener_precios("AAPL", "2020-01-01", "2020-01-10")
    assert not resultado.empty


# --- Fallback yfinance -> Stooq -----------------------------------------

def test_fallback_a_stooq_si_yfinance_falla(tmp_path, monkeypatch):
    monkeypatch.setattr(datos, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(datos, "MAX_REINTENTOS", 1)
    monkeypatch.setattr(datos, "ESPERA_INICIAL_SEG", 0)

    def yfinance_falla(ticker, inicio, fin):
        raise datos.DescargaFallidaError("simulado: rate limit")

    def stooq_ok(ticker, inicio, fin):
        return _precios_ejemplo()

    monkeypatch.setattr(datos, "_descargar_yfinance", yfinance_falla)
    monkeypatch.setattr(datos, "_descargar_stooq", stooq_ok)

    resultado = datos.obtener_precios("TICKER_INEXISTENTE", "2020-01-01", "2020-01-10")
    assert not resultado.empty
    assert list(resultado.columns) == ["precio"]


def test_excepcion_clara_si_ambas_fuentes_fallan(tmp_path, monkeypatch):
    monkeypatch.setattr(datos, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(datos, "MAX_REINTENTOS", 1)
    monkeypatch.setattr(datos, "ESPERA_INICIAL_SEG", 0)

    def yfinance_falla(ticker, inicio, fin):
        raise datos.DescargaFallidaError("simulado: sin conexión")

    def stooq_falla(ticker, inicio, fin):
        raise datos.DescargaFallidaError("simulado: ticker inexistente en Stooq")

    monkeypatch.setattr(datos, "_descargar_yfinance", yfinance_falla)
    monkeypatch.setattr(datos, "_descargar_stooq", stooq_falla)

    with pytest.raises(datos.DescargaFallidaError):
        datos.obtener_precios("NOEXISTE123", "2020-01-01", "2020-01-10", usar_cache=False)
