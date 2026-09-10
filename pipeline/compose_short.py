#!/usr/bin/env python3
"""
compose_short.py
Ensambla el Short final: cose el hook cinematográfico (Google Flow, sin
datos ni texto) con la gráfica animada (generada con render.py a partir de
datos reales) y añade música libre de derechos de fondo.

Usa exclusivamente ffmpeg/ffprobe vía subprocess — nada de MoviePy — para
mantener el mismo enfoque que el resto del pipeline. Valida cada entrada y
cada salida intermedia; nunca deja un mp4 corrupto o vacío sin avisar.

Uso:
    python compose_short.py --hook hook.mp4 --grafica grafica.mp4 \
        --output short_final.mp4 [--bgm musica.mp3] [--duracion 8]

    El hook es opcional: sin --hook, el Short se genera solo con la
    gráfica (útil mientras no haya clip de Flow todavía).
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ANCHO_PX = 1080
ALTO_PX = 1920


class ComposeError(Exception):
    """Error al ensamblar el Short final."""


def _requerir_binario(nombre: str) -> None:
    if shutil.which(nombre) is None:
        raise ComposeError(f"No se encontró el binario '{nombre}' en el sistema (PATH).")


def _requerir_fichero_valido(ruta: Path, descripcion: str) -> None:
    if not ruta.exists():
        raise ComposeError(f"{descripcion} no existe: {ruta}")
    if ruta.stat().st_size == 0:
        raise ComposeError(f"{descripcion} está vacío: {ruta}")


def _ejecutar_ffmpeg(argumentos: list[str], descripcion: str) -> None:
    comando = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *argumentos]
    try:
        subprocess.run(comando, capture_output=True, text=True, timeout=300, check=True)
    except subprocess.CalledProcessError as exc:
        raise ComposeError(
            f"ffmpeg falló al {descripcion}. Código {exc.returncode}. stderr: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ComposeError(f"ffmpeg superó el tiempo límite al {descripcion}.") from exc
    except OSError as exc:
        raise ComposeError(f"No se pudo ejecutar ffmpeg al {descripcion}: {exc}") from exc


def _validar_salida(ruta: Path, descripcion: str) -> None:
    if not ruta.exists() or ruta.stat().st_size == 0:
        raise ComposeError(f"{descripcion}: ffmpeg no produjo un fichero válido en {ruta}.")


def _duracion_segundos(ruta: Path) -> float:
    """Duración de un fichero multimedia vía ffprobe, o ComposeError si falla."""
    try:
        salida = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(ruta),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ComposeError(f"ffprobe no pudo leer '{ruta}': {exc}") from exc

    try:
        return float(salida.stdout.strip())
    except ValueError as exc:
        raise ComposeError(f"ffprobe devolvió una duración ilegible para '{ruta}'.") from exc


def componer_short(
    hook_path: Path | None,
    grafica_path: Path,
    output_path: Path,
    bgm_path: Path | None = None,
    duracion_seg: float | None = None,
) -> Path:
    """
    Concatena `hook_path` (2-3s sin datos, cinemático) con `grafica_path`
    (mp4 generado por render.generar_video a partir de datos reales) y
    añade `bgm_path` como música de fondo si se indica.

    `hook_path` es opcional: si no se indica (todavía no hay clip de Flow),
    el Short se genera solo con la gráfica, con música y recorte de
    duración si se piden.

    El resultado se normaliza a 1080x1920 (9:16). Si algo falla (binario
    ausente, fichero de entrada vacío/inexistente, error de ffmpeg, salida
    corrupta), se lanza ComposeError con un mensaje claro y no queda ningún
    mp4 corrupto en `output_path`.
    """
    _requerir_binario("ffmpeg")
    _requerir_binario("ffprobe")

    if hook_path is not None:
        _requerir_fichero_valido(hook_path, "El vídeo de hook")
    _requerir_fichero_valido(grafica_path, "El vídeo de la gráfica")
    if bgm_path is not None:
        _requerir_fichero_valido(bgm_path, "La música de fondo")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_fue_escrito = False

    if hook_path is not None:
        concatenado_path = output_path.with_suffix(".concat.tmp.mp4")
        concatenado_es_temporal = True
    else:
        # Sin hook, la propia gráfica es la entrada del siguiente paso: no
        # se crea ningún fichero temporal que limpiar al terminar.
        concatenado_path = grafica_path
        concatenado_es_temporal = False

    try:
        if hook_path is not None:
            # 1) Normalizar ambos clips a 1080x1920 y concatenarlos (hook + gráfica).
            filtro_concat = (
                f"[0:v]scale={ANCHO_PX}:{ALTO_PX}:force_original_aspect_ratio=decrease,"
                f"pad={ANCHO_PX}:{ALTO_PX}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];"
                f"[1:v]scale={ANCHO_PX}:{ALTO_PX}:force_original_aspect_ratio=decrease,"
                f"pad={ANCHO_PX}:{ALTO_PX}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
                f"[v0][v1]concat=n=2:v=1:a=0[v]"
            )
            _ejecutar_ffmpeg(
                [
                    "-i", str(hook_path),
                    "-i", str(grafica_path),
                    "-filter_complex", filtro_concat,
                    "-map", "[v]",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    str(concatenado_path),
                ],
                "concatenar hook y gráfica",
            )
            _validar_salida(concatenado_path, "Concatenación hook + gráfica")

        # 2) Añadir música de fondo (si se indica) y recortar a duracion_seg (si se indica).
        argumentos_finales = ["-i", str(concatenado_path)]
        if bgm_path is not None:
            argumentos_finales += ["-i", str(bgm_path), "-shortest", "-map", "0:v", "-map", "1:a"]
        if duracion_seg is not None:
            if duracion_seg <= 0:
                raise ComposeError("duracion_seg debe ser positiva.")
            argumentos_finales += ["-t", str(duracion_seg)]
        argumentos_finales += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if bgm_path is not None:
            argumentos_finales += ["-c:a", "aac"]
        argumentos_finales += [str(output_path)]

        output_fue_escrito = True
        _ejecutar_ffmpeg(argumentos_finales, "añadir audio y finalizar el vídeo")
        _validar_salida(output_path, "Vídeo final")

        # 3) Verificación final: el vídeo debe tener una duración coherente y no nula.
        duracion_final = _duracion_segundos(output_path)
        if duracion_final <= 0:
            raise ComposeError(f"El vídeo final '{output_path}' tiene duración nula o negativa.")

        logger.info("Short generado en %s (%.2fs).", output_path, duracion_final)
        return output_path

    except ComposeError:
        # Solo se borra la salida final si esta ejecución llegó a escribirla:
        # un fallo anterior (p. ej. en la concatenación) no debe destruir un
        # vídeo final válido de una ejecución previa en la misma ruta.
        if output_fue_escrito:
            output_path.unlink(missing_ok=True)
        raise
    finally:
        # Sin hook, concatenado_path ES grafica_path (una entrada, no un
        # temporal nuestro): borrarlo aquí destruiría el fichero de entrada.
        if concatenado_es_temporal:
            concatenado_path.unlink(missing_ok=True)


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensambla el Short final a partir de hook + gráfica.")
    parser.add_argument("--hook", type=Path, default=None, help="Clip cinemático de Flow (2-3s, sin datos, opcional).")
    parser.add_argument("--grafica", required=True, type=Path, help="Vídeo de la gráfica animada (render.py).")
    parser.add_argument("--output", required=True, type=Path, help="Ruta del mp4 final.")
    parser.add_argument("--bgm", type=Path, default=None, help="Música de fondo libre de derechos (opcional).")
    parser.add_argument("--duracion", type=float, default=None, help="Duración final en segundos (opcional).")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parsear_argumentos()
    try:
        ruta_final = componer_short(
            hook_path=args.hook,
            grafica_path=args.grafica,
            output_path=args.output,
            bgm_path=args.bgm,
            duracion_seg=args.duracion,
        )
    except ComposeError as exc:
        logger.error("No se pudo generar el Short: %s", exc)
        raise SystemExit(1) from exc
    logger.info("Short final listo en: %s", ruta_final)


if __name__ == "__main__":
    main()
