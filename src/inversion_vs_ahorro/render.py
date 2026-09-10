"""
render.py
Anima la comparación entre dos series de valor y exporta un Short (mp4 9:16).

Usa matplotlib.animation con el writer de ffmpeg (subprocess por debajo),
igual que pipeline/compose_short.py — sin MoviePy de por medio. Nunca deja
un mp4 corrupto o vacío sin avisar: valida entradas antes de renderizar y
el fichero de salida con ffprobe después.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Union

import matplotlib

matplotlib.use("Agg")  # pipeline headless, sin backend gráfico interactivo

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.animation import FFMpegWriter, FuncAnimation

logger = logging.getLogger(__name__)

ANCHO_PX = 1080
ALTO_PX = 1920
DPI = 100
FPS = 30


class RenderError(Exception):
    """Error al generar o validar el vídeo comparativo."""


def _formatear_moneda(valor: float) -> str:
    """Formatea un valor como '1.234 €' (punto de miles, sin decimales)."""
    return f"{valor:,.0f} €".replace(",", ".")


def _validar_entrada(
    datos_a: pd.DataFrame,
    datos_b: pd.DataFrame,
    titulo: str,
    duracion_seg: float,
    columna_valor: str,
) -> None:
    for nombre, datos in (("datos_a", datos_a), ("datos_b", datos_b)):
        if datos is None or datos.empty:
            raise RenderError(f"{nombre} está vacío; no hay nada que animar.")
        if columna_valor not in datos.columns:
            raise RenderError(f"{nombre} no tiene la columna '{columna_valor}'.")

    if not titulo or not titulo.strip():
        raise RenderError("El título del vídeo no puede estar vacío.")
    if duracion_seg <= 0:
        raise RenderError("duracion_seg debe ser positiva.")
    if shutil.which("ffmpeg") is None:
        raise RenderError(
            "No se encontró el binario 'ffmpeg' en el sistema; es necesario para exportar el vídeo."
        )


def _validar_video_generado(output_path: Path, duracion_esperada: float) -> None:
    """Comprueba con ffprobe que el mp4 no está vacío ni corrupto."""
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RenderError(f"ffmpeg no generó un fichero válido en {output_path}.")

    if shutil.which("ffprobe") is None:
        logger.warning("ffprobe no disponible en el sistema; se omite la validación de duración.")
        return

    try:
        salida = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RenderError(f"ffprobe no pudo leer el vídeo generado ({output_path}): {exc}") from exc

    texto_duracion = salida.stdout.strip()
    try:
        duracion_real = float(texto_duracion)
    except ValueError as exc:
        raise RenderError(
            f"ffprobe devolvió una duración ilegible para {output_path}: '{texto_duracion}'"
        ) from exc

    # margen de tolerancia: el encoder redondea al frame más cercano
    if abs(duracion_real - duracion_esperada) > 1.0:
        raise RenderError(
            f"El vídeo generado dura {duracion_real:.2f}s, se esperaban ~{duracion_esperada:.2f}s. "
            "Puede estar corrupto o truncado."
        )


def generar_video(
    datos_a: pd.DataFrame,
    datos_b: pd.DataFrame,
    titulo: str,
    output_path: Union[str, Path],
    duracion_seg: float = 8.0,
    etiqueta_a: str = "Serie A",
    etiqueta_b: str = "Serie B",
    columna_valor: str = "valor_nominal",
) -> Path:
    """
    Anima dos series de valor (p.ej. inversión vs ahorro) y exporta un mp4
    vertical (9:16, 1080x1920) de `duracion_seg` segundos.

    Si ffmpeg falla, o el fichero resultante no supera la validación con
    ffprobe, se lanza RenderError y se borra cualquier fichero parcial:
    nunca se deja un mp4 corrupto o vacío en el output.
    """
    output_path = Path(output_path)
    _validar_entrada(datos_a, datos_b, titulo, duracion_seg, columna_valor)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(ANCHO_PX / DPI, ALTO_PX / DPI), dpi=DPI)
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    n_frames = max(int(duracion_seg * FPS), 1)
    n_puntos_a = len(datos_a)
    n_puntos_b = len(datos_b)

    linea_a, = ax.plot([], [], color="#4fc3f7", linewidth=3, label=etiqueta_a)
    linea_b, = ax.plot([], [], color="#ff8a65", linewidth=3, label=etiqueta_b)

    # Etiquetas con la cifra actual, pegadas a la punta de cada línea.
    texto_valor_a = ax.text(
        0, 0, "", color="#4fc3f7", fontsize=15, fontweight="bold", va="center", ha="left"
    )
    texto_valor_b = ax.text(
        0, 0, "", color="#ff8a65", fontsize=15, fontweight="bold", va="center", ha="left"
    )

    n_max = max(n_puntos_a, n_puntos_b, 1)
    margen_texto = n_max * 0.02  # separación entre la punta de la línea y la cifra
    valor_max = max(datos_a[columna_valor].max(), datos_b[columna_valor].max())
    ax.set_xlim(0, n_max * 1.22)  # hueco a la derecha para que quepa la cifra
    ax.set_ylim(0, valor_max * 1.1 if valor_max > 0 else 1)
    ax.set_title(titulo, color="white", fontsize=18, wrap=True)
    ax.tick_params(colors="white")
    ax.legend(facecolor="#0d0d0d", labelcolor="white", loc="upper left")

    def actualizar(frame: int):
        progreso = (frame + 1) / n_frames
        idx_a = min(int(progreso * n_puntos_a), n_puntos_a)
        idx_b = min(int(progreso * n_puntos_b), n_puntos_b)
        linea_a.set_data(range(idx_a), datos_a[columna_valor].iloc[:idx_a])
        linea_b.set_data(range(idx_b), datos_b[columna_valor].iloc[:idx_b])

        if idx_a > 0:
            valor_a = datos_a[columna_valor].iloc[idx_a - 1]
            texto_valor_a.set_position((idx_a - 1 + margen_texto, valor_a))
            texto_valor_a.set_text(_formatear_moneda(valor_a))
        if idx_b > 0:
            valor_b = datos_b[columna_valor].iloc[idx_b - 1]
            texto_valor_b.set_position((idx_b - 1 + margen_texto, valor_b))
            texto_valor_b.set_text(_formatear_moneda(valor_b))

        return linea_a, linea_b, texto_valor_a, texto_valor_b

    animacion = FuncAnimation(fig, actualizar, frames=n_frames, blit=True)

    try:
        writer = FFMpegWriter(fps=FPS, codec="libx264", bitrate=-1)
        animacion.save(str(output_path), writer=writer, dpi=DPI)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de matplotlib/ffmpeg
        output_path.unlink(missing_ok=True)
        raise RenderError(f"Fallo al exportar el vídeo con ffmpeg: {exc}") from exc
    finally:
        plt.close(fig)

    try:
        _validar_video_generado(output_path, duracion_seg)
    except RenderError:
        output_path.unlink(missing_ok=True)
        raise

    return output_path
