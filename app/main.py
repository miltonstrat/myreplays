#!/usr/bin/env python3
"""CLI para autenticar e baixar replays do ver.meureplay.online."""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page


DEFAULT_FILTER = r"(replay|download|\.mp4|\.dem|\.zip|\.rar|\.7z)"


def load_playwright():
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "Dependência ausente: instale com `pip install -r requirements.txt`"
        ) from exc
    return async_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="myreplays",
        description=(
            "Faz login manual no site e baixa links de replay encontrados em uma página."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="https://ver.meureplay.online/",
        help="URL base do portal de replays.",
    )
    parser.add_argument(
        "--state",
        default="storage_state.json",
        help="Arquivo JSON para salvar/ler sessão autenticada.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser(
        "login", help="Abre o navegador para você fazer login manualmente."
    )
    login_parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa navegador sem interface (não recomendado no primeiro login).",
    )

    download_parser = subparsers.add_parser(
        "download", help="Baixa os replays encontrados na página.")
    download_parser.add_argument(
        "--list-url",
        default=None,
        help="Página onde os links de replay estão (padrão: --base-url).",
    )
    download_parser.add_argument(
        "--link-selector",
        default="a[href]",
        help="Seletor CSS usado para coletar links.",
    )
    download_parser.add_argument(
        "--filter-regex",
        default=DEFAULT_FILTER,
        help="Regex para filtrar links de replay.",
    )
    download_parser.add_argument(
        "--output-dir",
        default="replays",
        help="Diretório para salvar os arquivos.",
    )
    download_parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45_000,
        help="Timeout de navegação em milissegundos.",
    )

    return parser.parse_args()


async def run_login(base_url: str, state_path: Path, headless: bool) -> None:
    async_playwright = load_playwright()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        print(f"Abrindo {base_url} para login manual...")
        await page.goto(base_url)
        await page.pause()

        await context.storage_state(path=str(state_path))
        print(f"Sessão salva em: {state_path}")
        await browser.close()


async def collect_links(
    page: "Page", base_url: str, link_selector: str, filter_regex: str
) -> list[str]:
    hrefs = await page.eval_on_selector_all(
        link_selector,
        "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
    )

    pattern = re.compile(filter_regex, flags=re.IGNORECASE)
    normalized: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        absolute = urljoin(base_url, href)
        if not pattern.search(absolute):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        normalized.append(absolute)
    return normalized


def filename_from_url(url: str, fallback_name: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or fallback_name


async def download_file(context: "BrowserContext", url: str, output_dir: Path, idx: int) -> Path:
    response = await context.request.get(url)
    response.raise_for_status()

    name = filename_from_url(url, f"replay_{idx}.bin")
    destination = output_dir / name

    body = await response.body()
    destination.write_bytes(body)
    return destination


async def run_download(
    base_url: str,
    state_path: Path,
    list_url: str,
    link_selector: str,
    filter_regex: str,
    output_dir: Path,
    timeout_ms: int,
) -> None:
    if not state_path.exists():
        raise FileNotFoundError(
            f"Sessão não encontrada em '{state_path}'. Rode primeiro: myreplays login"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    async_playwright = load_playwright()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(state_path))
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        print(f"Abrindo página de listagem: {list_url}")
        await page.goto(list_url, wait_until="networkidle")

        links = await collect_links(page, base_url, link_selector, filter_regex)
        if not links:
            print("Nenhum link de replay encontrado com o filtro informado.")
            await browser.close()
            return

        print(f"{len(links)} replay(s) encontrado(s). Iniciando download...")
        for idx, url in enumerate(links, start=1):
            try:
                destination = await download_file(context, url, output_dir, idx)
                print(f"[{idx}/{len(links)}] OK {destination}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{idx}/{len(links)}] ERRO {url} -> {exc}")

        await browser.close()


async def main_async() -> None:
    args = parse_args()
    state_path = Path(args.state)

    if args.command == "login":
        await run_login(args.base_url, state_path, args.headless)
        return

    await run_download(
        base_url=args.base_url,
        state_path=state_path,
        list_url=args.list_url or args.base_url,
        link_selector=args.link_selector,
        filter_regex=args.filter_regex,
        output_dir=Path(args.output_dir),
        timeout_ms=args.timeout_ms,
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
