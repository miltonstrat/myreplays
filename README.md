# myreplays

Aplicativo em linha de comando para salvar sessão e baixar seus replays do site `https://ver.meureplay.online/`.

## Requisitos

- Python 3.10+
- Dependências Python
- Navegador do Playwright instalado

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso

### 1) Fazer login e salvar sessão

> O comando abaixo abre o navegador com interface. Faça login no site e, depois, feche/continue o modo pause para salvar a sessão.

```bash
python app/main.py --base-url https://ver.meureplay.online/ login
```

Isso cria `storage_state.json` com os cookies/sessão autenticada.

### 2) Baixar replays

Os replays são agrupados por hora em páginas como:

`https://ver.meureplay.online/videos?localid=226&day=2026-02-25&time=19:00&interval=01:00`

Passe a URL da listagem em `--list-url`; o script coleta todos os links de replay que aparecem nessa página e baixa.
Os arquivos são organizados automaticamente em subpastas por data (`YYYY_MM_DD`) dentro de `--output-dir`.

```bash
python app/main.py --base-url https://ver.meureplay.online/ download \
  --list-url "https://ver.meureplay.online/videos?localid=226&day=2026-02-25&time=19:00&interval=01:00" \
  --output-dir replays
```

Para baixar de várias horas/dias, rode o comando várias vezes alterando `--list-url` (ou use um script que chame o comando para cada URL).

Parâmetros úteis:

- `--link-selector`: seletor CSS para capturar links (padrão `a[href]`)
- `--filter-regex`: regex para filtrar links de replay
- `--state`: arquivo da sessão salva

Exemplo com filtro customizado:

```bash
python app/main.py --base-url https://ver.meureplay.online/ download \
  --list-url https://ver.meureplay.online/minha-area \
  --filter-regex "(\.dem$|\.mp4$|download-replay)"
```

### 3) Remover audio e cortar para 19s

Processa todos os `.mp4` de `replays` e salva em outra pasta:

```bash
python app/trim_mute_videos.py --input-dir replays --output-dir replays_19s_sem_audio
```

Para sobrescrever os arquivos originais:

```bash
python app/trim_mute_videos.py --input-dir replays --in-place
```

## Observações

- Se nada for encontrado, ajuste `--list-url`, `--link-selector` e `--filter-regex`.
- Alguns replays podem exigir navegar por páginas específicas antes do link final.
- Este script usa `ffmpeg` instalado no sistema.
- O script de corte/remoção de áudio busca arquivos recursivamente por padrão e limpa temporários em `--in-place`.
