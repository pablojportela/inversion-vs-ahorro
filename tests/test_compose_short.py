"""Tests de pipeline/compose_short.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import compose_short  # noqa: E402


def _clip_de_color(ruta: Path, color: str, tamano: str, duracion: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s={tamano}:d={duracion}",
            "-pix_fmt", "yuv420p", str(ruta),
        ],
        check=True,
        timeout=30,
    )


def _pista_de_audio(ruta: Path, duracion: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duracion}",
            str(ruta),
        ],
        check=True,
        timeout=30,
    )


@pytest.fixture
def hook(tmp_path) -> Path:
    ruta = tmp_path / "hook.mp4"
    _clip_de_color(ruta, "blue", "640x360", 1)
    return ruta


@pytest.fixture
def grafica(tmp_path) -> Path:
    ruta = tmp_path / "grafica.mp4"
    _clip_de_color(ruta, "red", "1080x1920", 2)
    return ruta


@pytest.fixture
def bgm(tmp_path) -> Path:
    ruta = tmp_path / "bgm.mp3"
    _pista_de_audio(ruta, 3)
    return ruta


def test_componer_con_hook_y_bgm(tmp_path, hook, grafica, bgm):
    salida = tmp_path / "final.mp4"
    resultado = compose_short.componer_short(hook, grafica, salida, bgm_path=bgm, duracion_seg=2.0)
    assert resultado == salida
    assert salida.exists() and salida.stat().st_size > 0


def test_componer_sin_hook_usa_solo_la_grafica(tmp_path, grafica):
    salida = tmp_path / "final.mp4"
    resultado = compose_short.componer_short(None, grafica, salida)
    assert resultado == salida
    assert salida.exists() and salida.stat().st_size > 0
    # la gráfica de entrada no debe borrarse: no es un temporal nuestro
    assert grafica.exists()


def test_sin_hook_no_borra_la_grafica_de_entrada_si_falla_despues(tmp_path, grafica, monkeypatch):
    salida = tmp_path / "final.mp4"

    def validacion_falsa(ruta, descripcion):
        raise compose_short.ComposeError("fallo simulado tras el paso de audio")

    monkeypatch.setattr(compose_short, "_validar_salida", validacion_falsa)

    with pytest.raises(compose_short.ComposeError):
        compose_short.componer_short(None, grafica, salida)

    assert grafica.exists()  # el input nunca debe desaparecer


def test_fallo_temprano_no_borra_salida_previa_valida(tmp_path, hook, grafica):
    salida = tmp_path / "final.mp4"
    compose_short.componer_short(hook, grafica, salida)
    assert salida.exists()

    with pytest.raises(compose_short.ComposeError):
        compose_short.componer_short(tmp_path / "hook_inexistente.mp4", grafica, salida)

    assert salida.exists()  # la salida de la ejecución anterior sobrevive
