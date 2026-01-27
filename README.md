# Riggbot

Small Discord bot that translates messages and embed descriptions using Google Translate.

## Quick start

1. Copy `.env.example` to `.env` and set your bot token and options.

2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Run locally (dev):

```powershell
python riggbot.py
```

## Environment variables

- `RIGGBOT_TOKEN` (required) — your Discord bot token.
- `EMBED_BOT_NAME` (required) — lowercase substring to identify the embed-producing bot.
- `DEST_LANG` (optional, default `en`) — target language code for automatic translations.
- `MANUAL_OVERRIDE_LANG` (optional, default `zh-CN`) — target language used when a manual translation is requested and the source language equals `DEST_LANG`.

## Building a standalone exe

This project includes a `riggbot.spec` to build with PyInstaller. Example:

```powershell
.venv\Scripts\pyinstaller.exe riggbot.spec
```

## Notes & troubleshooting

- Do not commit `.env` (it is gitignored). Keep your token secret.
- If the bundled exe fails to initialize `c10.dll` (PyTorch), ensure the Visual C++ Redistributable is installed, or include the CRT DLLs in the PyInstaller spec (see `riggbot.spec`).
- Optional features (OCR via `easyocr`) may require additional heavy deps such as `torch` — see `requirements.txt` comments.

