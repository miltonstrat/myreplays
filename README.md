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
python app/main.py login --base-url https://ver.meureplay.online/
```

Isso cria `storage_state.json` com os cookies/sessão autenticada.

### 2) Baixar replays

```bash
python app/main.py download \
  --base-url https://ver.meureplay.online/ \
  --list-url https://ver.meureplay.online/ \
  --output-dir replays
```

Parâmetros úteis:

- `--link-selector`: seletor CSS para capturar links (padrão `a[href]`)
- `--filter-regex`: regex para filtrar links de replay
- `--state`: arquivo da sessão salva

Exemplo com filtro customizado:

```bash
python app/main.py download \
  --list-url https://ver.meureplay.online/minha-area \
  --filter-regex "(\.dem$|\.mp4$|download-replay)"
```

## Observações

- Se nada for encontrado, ajuste `--list-url`, `--link-selector` e `--filter-regex`.
- Alguns replays podem exigir navegar por páginas específicas antes do link final.
