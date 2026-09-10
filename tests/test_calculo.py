"""Tests de src/inversion_vs_ahorro/calculo.py."""
from __future__ import annotations

import pandas as pd
import pytest

from inversion_vs_ahorro import calculo


def _precios_crecimiento_constante(tasa_anual: float, dias: int = 365 * 3) -> pd.DataFrame:
    """Serie de precios que crece a una tasa anual constante (interés compuesto diario)."""
    fechas = pd.date_range("2020-01-01", periods=dias, freq="D")
    tasa_diaria = (1 + tasa_anual) ** (1 / 365.25)
    precios = [100.0 * (tasa_diaria ** i) for i in range(dias)]
    return pd.DataFrame({"precio": precios}, index=fechas)


# --- Validación de entrada -----------------------------------------------

def test_precios_vacios_lanza_error():
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(pd.DataFrame(), "unico", 1000.0)


def test_falta_columna_precio_lanza_error():
    df = pd.DataFrame({"otra_cosa": [1, 2, 3]}, index=pd.date_range("2020-01-01", periods=3))
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(df, "unico", 1000.0)


def test_modo_invalido_lanza_error():
    df = _precios_crecimiento_constante(0.05, dias=10)
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(df, "modo_raro", 1000.0)


def test_aportacion_no_positiva_lanza_error():
    df = _precios_crecimiento_constante(0.05, dias=10)
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(df, "unico", 0.0)
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(df, "unico", -100.0)


def test_precio_cero_o_negativo_lanza_error_division_por_cero():
    fechas = pd.date_range("2020-01-01", periods=3)
    df = pd.DataFrame({"precio": [100.0, 0.0, 105.0]}, index=fechas)
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(df, "unico", 1000.0)


def test_precio_nan_lanza_error_en_vez_de_propagarse_en_silencio():
    fechas = pd.date_range("2020-01-01", periods=3)
    df = pd.DataFrame({"precio": [100.0, float("nan"), 105.0]}, index=fechas)
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(df, "unico", 1000.0)


# --- Modo único ------------------------------------------------------------

def test_modo_unico_compra_todo_en_primera_fecha():
    df = _precios_crecimiento_constante(0.10, dias=365)
    resultado = calculo.simular_crecimiento(df, "unico", 1000.0)

    assert resultado["aportado_acumulado"].iloc[0] == 1000.0
    assert resultado["aportado_acumulado"].iloc[-1] == 1000.0  # no hay más aportaciones
    # el valor crece porque el precio crece
    assert resultado["valor_nominal"].iloc[-1] > resultado["valor_nominal"].iloc[0]


def test_modo_unico_valor_final_coincide_con_calculo_manual():
    df = _precios_crecimiento_constante(0.0, dias=10)  # precio constante = 100
    resultado = calculo.simular_crecimiento(df, "unico", 1000.0)
    # con precio constante, el valor nominal no cambia
    assert resultado["valor_nominal"].iloc[-1] == pytest.approx(1000.0, rel=1e-6)


# --- Modo DCA ----------------------------------------------------------

def test_modo_dca_aporta_una_vez_por_mes():
    df = _precios_crecimiento_constante(0.0, dias=365 * 2)  # precio constante = 100
    resultado = calculo.simular_crecimiento(df, "dca", 100.0)

    n_meses = len(pd.Series(df.index).dt.to_period("M").unique())
    assert resultado["aportado_acumulado"].iloc[-1] == pytest.approx(100.0 * n_meses, rel=1e-6)


# --- Ajuste por inflación ------------------------------------------------

def test_inflacion_igual_a_crecimiento_nominal_da_crecimiento_real_cero():
    tasa = 0.06
    df = _precios_crecimiento_constante(tasa, dias=365 * 2)
    resultado = calculo.simular_crecimiento(
        df, "unico", 1000.0, ajustar_inflacion=True, ipc_anual=tasa
    )
    valor_real_inicial = resultado["valor_real"].iloc[0]
    valor_real_final = resultado["valor_real"].iloc[-1]

    crecimiento_real = (valor_real_final / valor_real_inicial) - 1
    assert crecimiento_real == pytest.approx(0.0, abs=1e-6)


def test_inflacion_menor_que_crecimiento_nominal_da_crecimiento_real_positivo():
    df = _precios_crecimiento_constante(0.10, dias=365 * 2)
    resultado = calculo.simular_crecimiento(
        df, "unico", 1000.0, ajustar_inflacion=True, ipc_anual=0.02
    )
    assert resultado["valor_real"].iloc[-1] > resultado["valor_real"].iloc[0]


def test_ipc_como_serie_por_anio():
    df = _precios_crecimiento_constante(0.05, dias=400)
    ipc_por_anio = pd.Series({2020: 0.05, 2021: 0.05})
    resultado = calculo.simular_crecimiento(
        df, "unico", 1000.0, ajustar_inflacion=True, ipc_anual=ipc_por_anio
    )
    assert "valor_real" in resultado.columns
    assert not resultado["valor_real"].isna().any()


def test_ipc_serie_sin_anio_definido_lanza_error():
    df = _precios_crecimiento_constante(0.05, dias=400)
    ipc_incompleto = pd.Series({2020: 0.05})  # falta 2021, que sí aparece en el rango
    with pytest.raises(calculo.CalculoError):
        calculo.simular_crecimiento(
            df, "unico", 1000.0, ajustar_inflacion=True, ipc_anual=ipc_incompleto
        )


# --- Huecos de calendario -------------------------------------------------

def test_huecos_de_calendario_no_rompen_el_calculo():
    fechas = pd.to_datetime(
        ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]  # salta el fin de semana
    )
    df = pd.DataFrame({"precio": [100.0, 101.0, 103.0, 104.0]}, index=fechas)
    resultado = calculo.simular_crecimiento(df, "unico", 1000.0)
    assert len(resultado) == 4
    assert not resultado["valor_nominal"].isna().any()
