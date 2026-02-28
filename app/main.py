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



DEFAULT_FILTER = r"(replay|download|video|videoPage|stream|play|\.mp4|\.dem|\.zip|\.rar|\.7z|/api/)"

# Regex para achar URLs em texto/JSON
URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>)\]]+", re.IGNORECASE)
DATE_IN_FILENAME = re.compile(r"(\d{4}_\d{2}_\d{2})")


def _extract_urls_from_value(val: object) -> list[str]:
    """Extrai URLs de uma estrutura JSON (listas, dicts, strings)."""
    out: list[str] = []
    if isinstance(val, str):
        for m in URL_IN_TEXT.findall(val):
            out.append(m.rstrip(".,;:]"))
    elif isinstance(val, dict):
        for v in val.values():
            out.extend(_extract_urls_from_value(v))
    elif isinstance(val, (list, tuple)):
        for v in val:
            out.extend(_extract_urls_from_value(v))
    return out


def _extract_video_page_urls_from_json(val: object, base_url: str) -> list[str]:
    """Extrai IDs de JSON e monta URLs videoPage?id=... (listagem do Meu Replay)."""
    base = base_url.rstrip("/")
    out: list[str] = []
    if isinstance(val, dict):
        vid = val.get("id")
        if vid is not None and isinstance(vid, (int, str)) and str(vid).isdigit():
            out.append(f"{base}/videoPage?id={vid}")
        for v in val.values():
            out.extend(_extract_video_page_urls_from_json(v, base_url))
    elif isinstance(val, (list, tuple)):
        for v in val:
            out.extend(_extract_video_page_urls_from_json(v, base_url))
    return out


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
    download_parser.add_argument(
        "--debug-links",
        action="store_true",
        help="Lista todos os links encontrados na página (sem filtrar) e sai. Use para ajustar --link-selector e --filter-regex.",
    )
    download_parser.add_argument(
        "--wait-after-load-ms",
        type=int,
        default=4000,
        help="Milissegundos de espera após carregar a página, para o SPA renderizar (padrão: 4000).",
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


def _normalize_urls(base_url: str, hrefs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for href in hrefs:
        if not href or not href.strip():
            continue
        absolute = urljoin(base_url, href.strip())
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


async def collect_all_hrefs(page: "Page", base_url: str, link_selector: str) -> list[str]:
    """Coleta todos os hrefs do seletor, sem filtro (para debug)."""
    hrefs = await page.eval_on_selector_all(
        link_selector,
        "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
    )
    return _normalize_urls(base_url, list(hrefs))


async def _collect_candidate_urls_from_target(
    target: "Page", base_url: str, link_selector: str
) -> list[str]:
    """Coleta URLs de um Page ou Frame (a[href] + data-href/data-url/data-src)."""
    hrefs = await target.eval_on_selector_all(
        link_selector,
        "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
    )
    candidates = _normalize_urls(base_url, list(hrefs))
    try:
        data_urls = await target.eval_on_selector_all(
            "[data-href], [data-url], [data-src]",
            """elements => elements.map(el =>
                el.getAttribute('data-href') || el.getAttribute('data-url') || el.getAttribute('data-src')
            ).filter(Boolean)""",
        )
        more = _normalize_urls(base_url, list(data_urls))
        seen = set(candidates)
        for u in more:
            if u not in seen:
                seen.add(u)
                candidates.append(u)
    except Exception:
        pass
    return candidates


async def collect_candidate_urls(
    page: "Page", base_url: str, link_selector: str
) -> list[str]:
    """Coleta URLs da página e de todos os iframes, com espera para SPA renderizar."""
    all_urls: list[str] = []
    seen: set[str] = set()
    for frame in page.frames:
        try:
            for u in await _collect_candidate_urls_from_target(frame, base_url, link_selector):
                if u not in seen:
                    seen.add(u)
                    all_urls.append(u)
        except Exception:
            pass
    return all_urls


async def collect_links(
    page: "Page", base_url: str, link_selector: str, filter_regex: str
) -> list[str]:
    hrefs = await collect_candidate_urls(page, base_url, link_selector)
    pattern = re.compile(filter_regex, flags=re.IGNORECASE)
    normalized: list[str] = []
    seen: set[str] = set()
    for url in hrefs:
        if not pattern.search(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        normalized.append(url)
    return normalized


def filename_from_url(url: str, fallback_name: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or fallback_name


def destination_from_name(output_dir: Path, file_name: str) -> Path:
    """Organiza arquivos em subpastas por data (YYYY_MM_DD), quando presente no nome."""
    match = DATE_IN_FILENAME.search(file_name)
    if not match:
        return output_dir / file_name
    date_dir = output_dir / match.group(1)
    return date_dir / file_name


# Padrão para considerar URL como mídia/download (não página HTML)
MEDIA_URL_PATTERN = re.compile(
    r"\.(mp4|webm|mkv|dem|zip|rar|7z)(\?|$)|/stream/|/download|/video/.*\.mp4",
    re.IGNORECASE,
)


async def download_file(context: "BrowserContext", url: str, output_dir: Path, idx: int) -> Path:
    response = await context.request.get(url)
    if not response.ok:
        status = getattr(response, "status", "unknown")
        raise RuntimeError(f"HTTP {status} ao baixar {url}")

    name = filename_from_url(url, f"replay_{idx}.bin")
    destination = destination_from_name(output_dir, name)
    destination.parent.mkdir(parents=True, exist_ok=True)

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
    debug_links: bool = False,
    wait_after_load_ms: int = 4000,
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

        # Capturar URLs da rede (páginas Flutter/SPA não expõem links no DOM)
        network_urls: list[str] = []
        media_captured: list[str] = []  # URLs de mídia ao abrir uma videoPage
        url_filter = re.compile(filter_regex, flags=re.IGNORECASE)
        api_keywords = ("video", "videos", "api", "replay", "list", "stream")

        async def on_response(response: object) -> None:
            try:
                u = getattr(response, "url", None)
                if not u:
                    return
                if u and url_filter.search(u):
                    network_urls.append(u)
                if MEDIA_URL_PATTERN.search(u):
                    media_captured.append(u)
                ct = (getattr(response, "headers", None) or {}).get("content-type") or ""
                if "json" in ct.lower():
                    req = getattr(response, "request", None)
                    req_url = getattr(req, "url", "") if req else ""
                    if any(k in req_url for k in api_keywords):
                        body = await response.json()
                        for found in _extract_urls_from_value(body):
                            if url_filter.search(found) and found not in network_urls:
                                network_urls.append(found)
                        # Montar links videoPage?id=... a partir de IDs no JSON
                        for video_url in _extract_video_page_urls_from_json(body, base_url):
                            if video_url not in network_urls:
                                network_urls.append(video_url)
            except Exception:
                pass

        page.on("response", on_response)

        print(f"Abrindo página de listagem: {list_url}")
        await page.goto(list_url, wait_until="networkidle")
        # Dar tempo ao SPA para renderizar e à rede para receber respostas (Flutter/SPA)
        if wait_after_load_ms > 0:
            await asyncio.sleep(wait_after_load_ms / 1000.0)

        if debug_links:
            candidates = await collect_candidate_urls(page, base_url, link_selector)
            if network_urls:
                print(f"URLs capturadas da rede (respostas que batem no filtro): {len(network_urls)}\n")
                for i, url in enumerate(network_urls, 1):
                    print(f"  {i}. {url}")
                print()
            pattern = re.compile(filter_regex, flags=re.IGNORECASE)
            filtered = [u for u in candidates if pattern.search(u)]
            print(f"URLs consideradas (a[href] + data-href/data-url/data-src): {len(candidates)}\n")
            for i, url in enumerate(candidates, 1):
                print(f"  {i}. {url}")
            print(f"\nApós filtro '{filter_regex}': {len(filtered)} link(s)")
            for i, url in enumerate(filtered, 1):
                print(f"  {i}. {url}")
            if not candidates:
                # Tentar atributos comuns de vídeo/player
                extra = await page.eval_on_selector_all(
                    "[data-href], [data-src], [data-url], [data-video], source[src], video[src]",
                    """elements => elements.map(el =>
                      el.getAttribute('data-href') || el.getAttribute('data-src') ||
                      el.getAttribute('data-url') || el.getAttribute('data-video') ||
                      el.getAttribute('src')
                    ).filter(Boolean)""",
                )
                if extra:
                    seen = set()
                    normalized = []
                    for href in extra:
                        absolute = urljoin(base_url, href)
                        if absolute not in seen:
                            seen.add(absolute)
                            normalized.append(absolute)
                    print(f"Links em data-* / source / video (sem seletor): {len(normalized)}\n")
                    for i, url in enumerate(normalized, 1):
                        print(f"  {i}. {url}")
                    print("\nUse --link-selector \"[data-src]\" (ou o atributo que aparecer) e --filter-regex \".\" para pegar todos.")
                else:
                    # Inspecionar atributos de botões/links que possam ter URL
                    try:
                        sample = await page.eval_on_selector_all(
                            "a, button, [role='button'], [data-id], [data-url], [data-key]",
                            """elements => elements.slice(0, 25).map(el => ({
                                tag: el.tagName,
                                attrs: Array.from(el.attributes).map(a => a.name + '=' + (a.value || '').substring(0, 60))
                            }))""",
                        )
                        if sample:
                            print("Amostra de elementos na página (tag + atributos):")
                            for i, s in enumerate(sample, 1):
                                print(f"  {i}. <{s.get('tag','')}> {s.get('attrs', [])}")
                    except Exception:
                        pass
                    print("\nDica: use F12 no navegador nessa URL e inspecione o botão de download para ver em qual atributo está o link.")
            await browser.close()
            return

        dom_links = await collect_links(page, base_url, link_selector, filter_regex)
        # Unir links do DOM com URLs capturadas da rede (Flutter/SPA)
        seen = set(dom_links)
        for u in network_urls:
            if u not in seen:
                seen.add(u)
                dom_links.append(u)
        links = dom_links
        if not links:
            print("Nenhum link de replay encontrado (DOM e rede). Tente --debug-links.")
            await browser.close()
            return

        print(f"{len(links)} replay(s) encontrado(s). Iniciando download...")
        for idx, url in enumerate(links, start=1):
            try:
                if "videoPage?id=" not in url and not MEDIA_URL_PATTERN.search(url):
                    print(f"[{idx}/{len(links)}] IGNORADO {url} (não parece mídia/download)")
                    continue
                if "videoPage?id=" in url:
                    # Página do vídeo: abrir e capturar URL real de mídia na rede
                    media_captured.clear()
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await asyncio.sleep(5.0)
                    direct_url = media_captured[0] if media_captured else None
                    if not direct_url:
                        print(f"[{idx}/{len(links)}] ERRO {url} -> nenhuma URL de mídia capturada")
                        continue
                    destination = await download_file(context, direct_url, output_dir, idx)
                else:
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
        debug_links=getattr(args, "debug_links", False),
        wait_after_load_ms=getattr(args, "wait_after_load_ms", 4000),
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
