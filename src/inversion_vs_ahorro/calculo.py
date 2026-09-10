"""
calculo.py
Simula el crecimiento de una inversión a partir de un histórico de precios.

Soporta aportación única o DCA (Dollar-Cost Averaging mensual), y un ajuste
opcional por inflación para comparar el crecimiento en términos reales.
"""
from __future__ import annotations

from typing import Literal, Union

import pandas as pd

ModoInversion = Literal["unico", "dca"]


class CalculoError(Exception):
    """Error en la simulación de crecimiento de una inversión."""


def _validar_entrada(precios: pd.DataFrame, modo: str, aportacion: float) -> None:
    if precios is None or precios.empty:
        raise CalculoError("El DataFrame de precios está vacío; no se puede simular nada.")
    if "precio" not in precios.columns:
        raise CalculoError("El DataFrame de precios debe tener una columna 'precio'.")
    if modo not in ("unico", "dca"):
        raise CalculoError(f"Modo '{modo}' no reconocido. Usa 'unico' o 'dca'.")
    if aportacion <= 0:
        raise CalculoError("La aportación debe ser un importe positivo.")
    if precios["precio"].isna().any():
        # un NaN no se detecta con "<= 0" (las comparaciones con NaN dan False)
        # y se propagaría en silencio por todo el cálculo si no se corta aquí
        raise CalculoError("Hay precios NaN en los datos; revisa la fuente antes de simular.")
    if (precios["precio"] <= 0).any():
        # evita división por cero al calcular unidades compradas
        raise CalculoError("Hay precios menores o iguales a cero en los datos; revisa la fuente.")


def _factor_inflacion_acumulado(
    fechas: pd.DatetimeIndex, ipc_anual: Union[float, pd.Series]
) -> pd.Series:
    """
    Factor acumulado de inflación desde la primera fecha de la serie
    (factor(t0) == 1.0), para deflactar valores nominales a valores reales.
    """
    if isinstance(ipc_anual, (int, float)):
        anios_transcurridos = (fechas - fechas[0]).days / 365.25
        factor = (1.0 + float(ipc_anual)) ** anios_transcurridos
        return pd.Series(factor, index=fechas)

    if isinstance(ipc_anual, pd.Series):
        # ipc_anual: índice = año (int), valor = tasa anual de ese año.
        # El factor se acumula día a día entre observaciones consecutivas,
        # usando siempre la tasa del año en el que cae cada tramo.
        factores = [1.0]
        for anterior, actual in zip(fechas[:-1], fechas[1:]):
            anio = actual.year
            tasa = ipc_anual.get(anio)
            if tasa is None:
                raise CalculoError(f"No hay IPC anual definido para el año {anio}.")
            dias = (actual - anterior).days
            factores.append(factores[-1] * (1.0 + float(tasa)) ** (dias / 365.25))
        return pd.Series(factores, index=fechas)

    raise CalculoError("ipc_anual debe ser un float o un pd.Series indexado por año.")


def simular_crecimiento(
    precios: pd.DataFrame,
    modo: ModoInversion,
    aportacion: float,
    ajustar_inflacion: bool = False,
    ipc_anual: Union[float, pd.Series] = 0.0,
) -> pd.DataFrame:
    """
    Simula el crecimiento de una inversión a partir de una serie de precios.

    - modo="unico": se invierte `aportacion` completa en la primera fecha
      disponible.
    - modo="dca": se invierte `aportacion` en el primer día de cotización
      de cada mes natural presente en `precios`.

    Si ajustar_inflacion=True, se añaden las columnas `valor_real` y
    `aportado_acumulado_real`, deflactadas con `ipc_anual` (float = tasa
    anual constante, o pd.Series indexada por año con la tasa de cada año).

    Los huecos de calendario (fines de semana, festivos) no requieren
    tratamiento especial: se opera sobre las fechas ya presentes en
    `precios`, que son las de sesión bursátil real.
    """
    _validar_entrada(precios, modo, aportacion)

    precios = precios.sort_index()
    fechas = precios.index
    serie_precio = precios["precio"]

    aportaciones = pd.Series(0.0, index=fechas)

    if modo == "unico":
        aportaciones.iloc[0] = aportacion
    else:  # dca
        fechas_por_periodo = pd.Series(fechas, index=fechas).groupby([fechas.year, fechas.month])
        primer_dia_por_mes = fechas_por_periodo.min()
        aportaciones.loc[primer_dia_por_mes.values] = aportacion

    unidades_compradas = aportaciones / serie_precio  # precio > 0 garantizado por _validar_entrada
    unidades_acumuladas = unidades_compradas.cumsum()

    resultado = pd.DataFrame(index=fechas)
    resultado["precio"] = serie_precio
    resultado["aportado_acumulado"] = aportaciones.cumsum()
    resultado["valor_nominal"] = unidades_acumuladas * serie_precio

    if ajustar_inflacion:
        factor = _factor_inflacion_acumulado(fechas, ipc_anual)
        resultado["valor_real"] = resultado["valor_nominal"] / factor
        resultado["aportado_acumulado_real"] = resultado["aportado_acumulado"] / factor

    return resultado
