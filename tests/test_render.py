"""Tests de src/inversion_vs_ahorro/render.py."""
from __future__ import annotations

import pandas as pd
import pytest

from inversion_vs_ahorro import render


def _datos_ejemplo(n: int = 20) -> pd.DataFrame:
    fechas = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"valor_nominal": [100.0 + i for i in range(n)]}, index=fechas)


# --- Validación de entrada -----------------------------------------------

def test_datos_a_vacio_lanza_error(tmp_path):
    with pytest.raises(render.RenderError):
        render.generar_video(pd.DataFrame(), _datos_ejemplo(), "Título", tmp_path / "out.mp4")


def test_datos_b_vacio_lanza_error(tmp_path):
    with pytest.raises(render.RenderError):
        render.generar_video(_datos_ejemplo(), pd.DataFrame(), "Título", tmp_path / "out.mp4")


def test_falta_columna_valor_lanza_error(tmp_path):
    df_sin_columna = pd.DataFrame({"otra": [1, 2, 3]}, index=pd.date_range("2020-01-01", periods=3))
    with pytest.raises(render.RenderError):
        render.generar_video(df_sin_columna, _datos_ejemplo(), "Título", tmp_path / "out.mp4")


def test_titulo_vacio_lanza_error(tmp_path):
    with pytest.raises(render.RenderError):
        render.generar_video(_datos_ejemplo(), _datos_ejemplo(), "  ", tmp_path / "out.mp4")


def test_duracion_no_positiva_lanza_error(tmp_path):
    with pytest.raises(render.RenderError):
        render.generar_video(
            _datos_ejemplo(), _datos_ejemplo(), "Título", tmp_path / "out.mp4", duracion_seg=0
        )


def test_ffmpeg_ausente_lanza_error(tmp_path, monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda binario: None)
    with pytest.raises(render.RenderError):
        render.generar_video(_datos_ejemplo(), _datos_ejemplo(), "Título", tmp_path / "out.mp4")


# --- Generación real (requiere ffmpeg instalado) --------------------------

def test_genera_mp4_valido_de_corta_duracion(tmp_path):
    salida = tmp_path / "corto.mp4"
    resultado = render.generar_video(
        _datos_ejemplo(),
        _datos_ejemplo(),
        "Inversión vs ahorro",
        salida,
        duracion_seg=1.0,
    )
    assert resultado == salida
    assert salida.exists()
    assert salida.stat().st_size > 0


def test_no_deja_mp4_corrupto_si_ffprobe_detecta_duracion_incoherente(tmp_path, monkeypatch):
    salida = tmp_path / "roto.mp4"

    def validacion_falsa(ruta, duracion_esperada):
        raise render.RenderError("duración incoherente simulada")

    monkeypatch.setattr(render, "_validar_video_generado", validacion_falsa)

    with pytest.raises(render.RenderError):
        render.generar_video(
            _datos_ejemplo(), _datos_ejemplo(), "Título", salida, duracion_seg=1.0
        )

    assert not salida.exists()
