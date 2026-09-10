"""Tests de pipeline/generar_short.py (orquestación, con las etapas mockeadas)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import generar_short  # noqa: E402
from inversion_vs_ahorro import calculo, datos, render  # noqa: E402
import compose_short  # noqa: E402


def _precios_falsos(ticker, fecha_inicio, fecha_fin):
    fechas = pd.date_range("2020-01-01", periods=5, freq="D")
    return pd.DataFrame({"precio": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=fechas)


@pytest.fixture(autouse=True)
def mocks_de_etapas(monkeypatch, tmp_path):
    monkeypatch.setattr(datos, "obtener_precios", _precios_falsos)

    llamadas = {"render": [], "compose": []}

    def render_falso(datos_a, datos_b, titulo, output_path, **kwargs):
        Path(output_path).write_bytes(b"grafica falsa")
        llamadas["render"].append((titulo, output_path, kwargs))
        return Path(output_path)

    def compose_falso(hook_path, grafica_path, output_path, bgm_path=None, duracion_seg=None):
        assert Path(grafica_path).exists()  # la gráfica debe existir cuando se ensambla
        Path(output_path).write_bytes(b"short final falso")
        llamadas["compose"].append((hook_path, grafica_path, output_path, bgm_path, duracion_seg))
        return Path(output_path)

    monkeypatch.setattr(render, "generar_video", render_falso)
    monkeypatch.setattr(compose_short, "componer_short", compose_falso)
    monkeypatch.setattr(generar_short, "render", render)
    monkeypatch.setattr(generar_short, "compose_short", compose_short)

    return llamadas


def test_genera_short_de_principio_a_fin(tmp_path, mocks_de_etapas):
    salida = tmp_path / "short.mp4"
    resultado = generar_short.generar_short(
        ticker_a="AAA", ticker_b="BBB", titulo="Test", output_path=salida
    )
    assert resultado == salida
    assert salida.exists()
    assert salida.read_bytes() == b"short final falso"
    # el fichero temporal de la gráfica no debe sobrevivir
    assert not (salida.with_name(f"{salida.stem}.grafica.tmp.mp4")).exists()


def test_usa_valor_real_cuando_se_ajusta_inflacion(tmp_path, mocks_de_etapas):
    salida = tmp_path / "short.mp4"
    generar_short.generar_short(
        ticker_a="AAA", ticker_b="BBB", titulo="Test", output_path=salida,
        ajustar_inflacion=True, ipc_anual=0.03,
    )
    _, _, kwargs = mocks_de_etapas["render"][0]
    assert kwargs["columna_valor"] == "valor_real"


def test_error_en_descarga_se_envuelve_con_contexto(tmp_path, monkeypatch):
    def descarga_falla(ticker, fecha_inicio, fecha_fin):
        raise datos.DescargaFallidaError("simulado")

    monkeypatch.setattr(datos, "obtener_precios", descarga_falla)
    salida = tmp_path / "short.mp4"

    with pytest.raises(generar_short.GenerarShortError, match="descargar los precios"):
        generar_short.generar_short(ticker_a="AAA", ticker_b="BBB", titulo="Test", output_path=salida)


def test_error_en_calculo_se_envuelve_con_contexto(tmp_path, monkeypatch, mocks_de_etapas):
    def calculo_falla(*args, **kwargs):
        raise calculo.CalculoError("simulado")

    monkeypatch.setattr(calculo, "simular_crecimiento", calculo_falla)
    salida = tmp_path / "short.mp4"

    with pytest.raises(generar_short.GenerarShortError, match="simular el crecimiento"):
        generar_short.generar_short(ticker_a="AAA", ticker_b="BBB", titulo="Test", output_path=salida)


def test_error_en_ensamblado_limpia_el_temporal_de_la_grafica(tmp_path, mocks_de_etapas):
    def compose_falla(*args, **kwargs):
        raise compose_short.ComposeError("simulado")

    mocks_de_etapas  # ya parcheado render; sobreescribimos solo compose
    import pytest as _pytest  # evitar import no usado si se reordena

    salida = tmp_path / "short.mp4"
    temporal = salida.with_name(f"{salida.stem}.grafica.tmp.mp4")

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(compose_short, "componer_short", compose_falla)
        mp.setattr(generar_short, "compose_short", compose_short)
        with pytest.raises(generar_short.GenerarShortError, match="ensamblar el Short final"):
            generar_short.generar_short(ticker_a="AAA", ticker_b="BBB", titulo="Test", output_path=salida)

    assert not temporal.exists()
