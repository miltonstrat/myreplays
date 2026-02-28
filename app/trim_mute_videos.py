#!/usr/bin/env python3
"""Processa videos em lote: remove audio e limita a 19 segundos."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="trim_mute_videos",
        description="Remove audio e corta videos para no maximo 19 segundos.",
    )
    parser.add_argument(
        "--input-dir",
        default="replays",
        help="Pasta com os videos de entrada (padrao: replays).",
    )
    parser.add_argument(
        "--output-dir",
        default="replays_19s_sem_audio",
        help="Pasta de saida quando nao usar --in-place.",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=19.0,
        help="Duracao maxima final em segundos (padrao: 19).",
    )
    parser.add_argument(
        "--pattern",
        default="*.mp4",
        help="Padrao de arquivo para processar (padrao: *.mp4).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Procura videos recursivamente dentro da pasta de entrada (padrao: ligado).",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_false",
        dest="recursive",
        help="Desliga busca recursiva.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Sobrescreve os videos originais.",
    )
    return parser.parse_args()


def run_ffmpeg(src: Path, dst: Path, max_seconds: float) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-t",
        str(max_seconds),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = proc.stderr.strip().splitlines()
        tail = "\n".join(stderr[-6:]) if stderr else "erro desconhecido"
        raise RuntimeError(f"ffmpeg falhou para '{src.name}':\n{tail}")


def main() -> None:
    args = parse_args()

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg nao encontrado. Instale e tente novamente.")

    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Pasta de entrada invalida: {input_dir}")

    if args.recursive:
        files = sorted(input_dir.rglob(args.pattern))
    else:
        files = sorted(input_dir.glob(args.pattern))
    files = [f for f in files if f.is_file()]

    if not files:
        print("Nenhum arquivo encontrado para processar.")
        return

    output_dir = Path(args.output_dir)
    if not args.in_place:
        output_dir.mkdir(parents=True, exist_ok=True)

    total = len(files)
    print(f"Encontrado(s) {total} arquivo(s). Processando...")

    ok = 0
    for idx, src in enumerate(files, start=1):
        tmp: Path | None = None
        try:
            if args.in_place:
                tmp = src.with_suffix(".tmp.muted_trimmed.mp4")
                run_ffmpeg(src, tmp, args.max_seconds)
                tmp.replace(src)
                dst = src
            else:
                rel = src.relative_to(input_dir)
                dst = output_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                run_ffmpeg(src, dst, args.max_seconds)
            ok += 1
            print(f"[{idx}/{total}] OK {dst}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{idx}/{total}] ERRO {src} -> {exc}")
        finally:
            # Garantir limpeza de temporario em caso de erro no --in-place.
            if tmp and tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    print(f"Concluido: {ok}/{total} processado(s) com sucesso.")
    if ok != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
