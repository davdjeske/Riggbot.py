# Riggbot

A Discord bot for a server of friends: translations on request, keyword triggers, and a bit of personality.

## Features

**Translation** (on request only)

- React to a message with 🏳️‍⚧️ to translate it into English (`dest_lang`). Text that's already English is translated into Chinese (`manual_override_lang`) instead.
- React with a country flag (🇯🇵, 🇩🇪, …) to translate the message as that country's language. Manage the flags with `/langflags`.
- Reply to a message with anything containing **"trans"** to translate the replied-to message. This matches *anywhere*, so "transport", "transfer" and "transparent" count too. That's deliberate: it's funny. Please don't "fix" it.
- For link embeds (e.g. fxtwitter), the post (📄) and a quoted post (💬) are translated separately.
- Only the first reaction of a kind triggers a translation, and the same message isn't translated again within 30 seconds.

**Triggers.** When a message contains a trigger phrase, riggbot answers with the trigger's response. Each server has its own list, starting with the classics (`beer`, `one piece`, `riggbot`, …). Manage them with `/trigger`.

**Other bots.** Messages from other bots are ignored by triggers unless the bot is approved on that server with `/bots` *and* the trigger allows approved bots. No bots are approved by default.

**Personality**

- Reply to a message with "riggbot is this true" (or "@riggbot is this true") for a definitive answer.
- LatiBot banter, and a thank-you for the first ⭐ on one of riggbot's messages.
- Owners (see `owner_ids`) can say "say goodbye riggbot" to shut the bot down.

## Commands

| Command | Who | What |
|---|---|---|
| `/trigger add` `phrase` `response` [`match`] [`include_bots`] | everyone | Add or change a trigger. `match`: `contains` (default, anywhere, even inside words), `word` (whole words) or `exact` (whole message). `include_bots`: also answer approved bots. |
| `/trigger remove` `phrase` · `/trigger list` | everyone | |
| `/bots add` `bot` · `/bots remove` `bot` · `/bots list` | everyone | Approved bots for this server |
| `/langflags set` `flag` `lang_code` · `/langflags remove` `flag` · `/langflags list` | everyone | Flag reaction → source language (e.g. 🇯🇵 → `ja`) |
| `/ping` | everyone | Latency check |
| `/shutdown` · `/sync` · `/reload` | owners | Stop the bot · re-register slash commands · re-read `config.json` and `data/` |

## Setup

1. **Discord application:** in the [Developer Portal](https://discord.com/developers/applications), under *Bot*, turn on the **Message Content** intent. Invite the bot with the `bot` and `applications.commands` scopes, and permission to read and send messages and read message history.
2. **Python 3.14** and dependencies:
   ```powershell
   py -3.14 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. **Secrets:** copy `.env.example` to `.env` and set `RIGGBOT_TOKEN` (and `DEEPL_API_KEY` if you have one).
4. **Settings:** copy `config.example.json` to `config.json` and set at least `owner_ids` (your Discord user ID: *Settings → Advanced → Developer Mode*, then right-click yourself → *Copy User ID*). Setting `latibot.user_id` is recommended too.
5. **Run:** `start.bat`, or `.venv\Scripts\python.exe main.py` (same as `python -m riggbot`).

**In VS Code:** run the task *Set up environment* (Terminal → Run Task…) to create `.venv` and install everything. Then use Ctrl+Shift+B (*Run riggbot*), or F5 with the *Riggbot* launch config to run it under the debugger. There are also tasks and launch configs for debug-level logs, the tests, and building the exe.

Everything the bot reads and writes lives next to it: `.env`, `config.json`, `data/` (triggers, approved bots, flags) and `logs/`.

## Configuration

Settings are merged in this order, later wins: **built-in defaults → `config.json` → environment variables / `.env`**. The bot never writes `config.json`. If a setting is wrong, the bot refuses to start and names the bad key. `config.example.json` lists every setting with its default.

| Section | Settings |
|---|---|
| `owner_ids` | Discord user IDs allowed to use owner commands and the goodbye phrases |
| `latibot` | `user_id` of LatiBot; `name_fallback` (username substring) is used when no ID is set |
| `responses` | `is_this_true` (`phrases`, where `{mention}` means an @riggbot mention, and `answers`), `star_thanks`, `latibot_banter`, `shutdown` (`phrases`, `farewells`) |
| `translation` | `providers` (order to try), `dest_lang`, `manual_override_lang`, `startup_self_test`, `breaker`, `reaction_cooldown_seconds`, `libretranslate.url` |
| `logging` | `level` (console), `file_level`, `library_level`, `color` (`auto`/`always`/`never`), `file`, `max_bytes`, `backup_count`, `discord_channel_id`, `discord_level` (see [Logging](#logging)) |

Environment overrides: `DEST_LANG`, `MANUAL_OVERRIDE_LANG`, `TRANSLATION_PROVIDERS` (comma-separated), `LIBRETRANSLATE_URL`, `LOG_LEVEL`, `LOG_FILE_LEVEL`, `LOG_COLOR`, `NO_COLOR`, `LOG_DISCORD_CHANNEL_ID` (`off` turns it off), `LOG_DISCORD_LEVEL`. Secrets (`RIGGBOT_TOKEN`, `DEEPL_API_KEY`, `LIBRETRANSLATE_API_KEY`) are only read from the environment / `.env`.

### Translation providers

Providers are tried in the order of `translation.providers` (default `deepl`, `googletrans`, `libretranslate`). If one fails or doesn't support a language, the next one is tried. A provider that fails 3 times in a row is paused for 10 minutes (`breaker`). Providers without their settings are skipped, with a warning at startup.

- **DeepL**: best quality. Needs a DeepL API key in `DEEPL_API_KEY`; the free plan allows 500,000 characters a month (DeepL asks for a card to verify the account). Supports about 30 languages.
- **googletrans**: free and needs no setup, but it's an unofficial scraper that Google sometimes blocks.
- **LibreTranslate**: open source; free if you host it yourself: `pip install libretranslate`, then `libretranslate` (all language models take a few GB; `--load-only en,ja,de,...` limits them). Point `translation.libretranslate.url` at it (default `http://localhost:5000`). The public libretranslate.com server needs a paid key in `LIBRETRANSLATE_API_KEY`.

At startup, each provider is tested once and the result is logged.

## Logging

One line per event, colored in the console:

```
2026-09-27 07:32:00.445 [info] [translation.service] Translated ja→en via deepl (412 chars, 445 ms)
```

Logs are written to `logs/riggbot.log` (rotated at 1 MB, 3 backups). Message text is only logged at `debug` level. The file gets debug by default; set `logging.file_level` to `INFO` to keep message text out of it.

**Log channel.** The bot can also post its logs to one Discord channel:

1. Enable Developer Mode (*Settings → Advanced*), then right-click the channel → *Copy Channel ID*.
2. In `config.json`, under `logging`, set `"discord_channel_id": 123456789012345678`. Optionally set `"discord_level"`: the lowest level to post. `"INFO"` (the default) posts info, warning, error and critical, but skips debug.
3. Restart, or run `/reload`.

Only one channel, in one server, can be set. The bot needs permission to view and send messages there. Lines are collected and posted every few seconds as a colored code block. If they come in faster than Discord allows, the oldest are dropped and the next post says how many. If the channel can't be found or used, a warning is logged and posting stops until the next `/reload`. Setting `discord_level` to `"DEBUG"` posts message text too, so pick a private channel.

## Development

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```

Tests don't touch the network or Discord. `tests/test_behavior_lock.py` pins behavior that must not change: "is this true" and the loose "trans" trigger.

**Layout**

```
main.py                 launcher (also the PyInstaller entry point)
riggbot/
  bot.py                RiggBot: startup, shared services, slash-command error handling
  config.py             settings dataclasses and loading
  log.py                log format and setup
  log_channel.py        posts logs to a Discord channel
  storage.py            JsonStore (one file) and GuildStore (one document per server)
  messaging.py          send long messages, resolve replies, fetch reacted-to messages
  checks.py             owner_only() for slash commands
  cooldown.py           per-key cooldowns
  embed_text.py         split link-embed text into post and quoted post
  ui/pagination.py      Paginator: ◀ ▶ pages for long lists
  translation/          provider interface, providers, TranslationService
  cogs/                 features: admin, bots, fun, langflags, translate, triggers
  defaults/             shipped defaults (flag map, starting triggers)
tests/
```

**Adding a feature.** Create a cog in `riggbot/cogs/` with an `async def setup(bot)` function, and add it to `EXTENSIONS` in `bot.py`. Cogs get shared services from the bot:

- `self.bot.settings`: current settings. Read it each time rather than keeping a copy, because `/reload` replaces it.
- `self.bot.guild_store.section(guild_id, 'my_feature', list)`: this server's data for your feature. Change it, then `await self.bot.guild_store.save(guild_id)`.
- `self.bot.translation.translate_text(...)`: translation.

Helpers ready to use:

- `Paginator.respond(interaction, build_pages(lines))` for lists.
- `messaging.reply()` for text that may be long.
- `@owner_only()` for owner commands.
- `Cooldown` to rate-limit something.
- `app_commands.guild_only()` for per-server commands.

New settings go into a dataclass in `config.py` plus `config.example.json`; loading and validation are automatic. `tests/conftest.py` has fake bots, messages and interactions for testing cogs.

**Adding a translation provider.** Implement the `TranslationProvider` protocol in `riggbot/translation/base.py` (see the existing providers), then register a factory in `PROVIDERS` in `riggbot/translation/__init__.py`.

## Building a standalone exe

```powershell
.venv\Scripts\pyinstaller.exe riggbot.spec --noconfirm
```

This produces `dist/riggbot.exe`. Put `.env` and `config.json` next to it. The CI workflow can also build it: run the workflow manually from the Actions tab and download the `riggbot-windows` artifact.
