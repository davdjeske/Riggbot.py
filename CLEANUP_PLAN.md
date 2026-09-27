# Riggbot — Cleanup Plan

_Branch: `mh-riggbot` · Updated 2026-09-27 · Builds on [ANALYSIS.md](ANALYSIS.md) and replaces its §10._

This plan turns the analysis into an ordered set of changes. Each change traces back to a requirement from the bot's creator (**C#**) or from the maintainer's review notes (**M#**). All six design decisions are settled; see [§9](#9-decisions).

---

## 1. Requirements

### Creator requirements (non-negotiable)

| ID | Requirement | What it means for this plan |
|---|---|---|
| **C1** | The "riggbot is this true" feature must work exactly as it does now. Restructuring, bug fixes and cleanup are allowed. | Same trigger phrases, same condition (a reply, and the replied-to message isn't riggbot's), same answers `Yes` / `No` / `Israel`, and same silent reply. The phrases and answers move into `config.json`, and **the defaults are exactly today's values**. With default config, the behavior is identical. Tests lock that default behavior **before** any refactoring (Phase 0). |
| **C2** | Don't fix the unintended translation triggers. They are deliberate ("it was funny"). | A reply containing `trans` anywhere (for example "transfer" or "transport") keeps triggering a translation of the replied-to message. It's documented in the README and code and covered by a test, and not "fixed". |
| **C3** | Translation must go through a standard interface so providers can be swapped. googletrans stays as one option. Other providers can be added, and the default can change. | A `TranslationProvider` interface with three providers: DeepL, LibreTranslate and googletrans. Which ones are used, and in what order, is set in config (§4). |

### Maintainer notes

| ID | Note | Where it's handled |
|---|---|---|
| **M1** | Go with option B: translation only on a manual trigger or keyword. Drop auto-translation of the embed bot's posts. | Phase 2 |
| **M2** | Document the `trans` over-triggering rather than fixing it (same as C2). | Phase 0, Phase 4 |
| **M3** | Standard provider interface. Keep googletrans, and add providers that work more consistently. | Phase 2, §4 |
| **M4** | A `/trigger` command to manage keyword → response pairs at runtime, replacing the hardcoded list. | Phase 3, §5 |
| **M5** | A `config.json` for settings that persist between runs. | Phase 1, §6 |
| **M6** | Restructuring, new folders and deleting files are all fine, as long as they don't violate C1–C3. | §3 |
| **M7** | Proper logging: more INFO, real DEBUG, level set from config.json and env vars, readable colored output. | Phase 1, §7 |
| **M8** | The "is this true" phrases and answers can be configurable, as long as the defaults give the same behavior. | §6, Phase 3 |
| **M9** | Each trigger decides for itself whether messages from approved bots can set it off. | §5 |
| **M10** | A `/bots` command manages the approved-bots list. No bots are approved by default. | §5 |
| **M11** | The owner text commands that shut the bot down stay. The `riggbot` → "I'm riggbot!" response becomes an ordinary trigger. | §2, §5 |
| **M12** | Rename `/edit_flag_lang` to `/langFlags`. | §5 |
| **M13** | A reusable pagination helper, first used for `/trigger list`. | §3 |
| **M14** | Log lines formatted as `<timestamp> [level] [component] message`, with specific colors and no `riggbot.` prefix on the component. | §7 |

Everything else from ANALYSIS.md §10 (bug fixes, structure, tooling) stays in scope unless it conflicts with the tables above.

---

## 2. Behavior after cleanup

What each current feature becomes. **Changes behavior** means a user in Discord would notice something different.

| Feature | After cleanup | Changes behavior? |
|---|---|---|
| Auto-translate embed-bot posts | **Removed** (M1). `EMBED_BOT_NAME` is retired; if it's still set, the bot logs a warning. | Yes (intended) |
| 🏳️‍⚧️ reaction → translate | Kept. Also works on messages sent before the bot started (switch to raw reaction events). The same message can't be translated again within a 30 s cooldown. | Only the two fixes |
| Flag reaction → translate with that flag's source language | Kept, same map. Fixes the crash when the map file is missing. | No |
| Reply containing `trans` → translate | **Kept exactly, including over-triggering** (C2). Internal fix only: the replied-to message is fetched only when a trigger matches. | No |
| Translation output format (`ja→en:\n…`, 📄 main post / 💬 quoted post) | Kept. LatiBot's banter copies this format. | No |
| Translation of text already in the destination language (translate into the override language) | Kept | No |
| "riggbot is this true" | **Same behavior** (C1). Phrases and answers come from config, with today's values as the defaults. The bot's mention is built from the running bot's ID instead of a hardcoded one, which is the same ID in production. | No |
| Keyword responses (`beer`, `one piece`, …) | Moved into per-server trigger lists managed with `/trigger` (M4). Every server starts with today's 7 keywords. Matching stays "contains, case-insensitive". | See the next three rows |
| Keyword responses to **other bots' messages** | Today, any bot's message can set off a keyword. After cleanup, a bot's message only counts if that bot is on the server's approved list (`/bots`) **and** the trigger allows approved bots (M9, M10). No bots are approved by default. | Yes (intended). Other bots stop setting off triggers until someone approves them. |
| Keyword responses in **DMs** | Triggers are per server, so there are none in DMs | Yes (minor) |
| `riggbot` → "I'm riggbot!" | Becomes an ordinary trigger (M11), seeded into every server. It now answers **anyone**, not just the two owners. Because it matches on "contains", a "riggbot is this true" reply also gets an "I'm riggbot!" alongside the answer. That already happens for owners today. `/trigger` can switch the trigger to `word` or `exact` matching if that's unwanted. | Yes (intended) |
| LatiBot banter (`dat me!!`, `"iM rIgGbOt!"`) | Kept. LatiBot is identified by user ID from config, falling back to the name match. The reply texts move to config. | No |
| ⭐ on a riggbot message → "omg thank you so much" | Kept, now sent silently like every other reply | Minor |
| Owner shutdown text commands (`say goodbye riggbot`, `riggbot, kys`) | Kept (M11). Owners are identified by user ID from config, not username. An owner-only `/shutdown` is added alongside. | No |
| `/ping` | Kept | No |
| `/edit_flag_lang` | Renamed to **`/langflags`** (M12), with `set`, `remove` and `list` subcommands. Discord requires command names to be lowercase, so `/langFlags` can't be registered as written. `set` does what `/edit_flag_lang` did, and adds input validation. Anyone can use it (D2). | Rename |
| `/bots`, `/trigger` | New | New |
| Startup translation self-test | Kept. Runs once per launch (not on every reconnect) against the configured provider(s). | No |
| Long translations | Split across several messages instead of failing when they pass Discord's 2000-character limit | Fix |

---

## 3. Target structure

```
Riggbot/
├─ main.py                         # thin launcher (python main.py / PyInstaller entry)
├─ riggbot/
│  ├─ __init__.py
│  ├─ __main__.py                  # python -m riggbot
│  ├─ bot.py                       # RiggBot(commands.Bot): setup_hook loads cogs, one-time sync + self-test
│  ├─ paths.py                     # base dir: exe folder when frozen, else project root
│  ├─ config.py                    # Settings dataclasses; defaults < config.json < env vars
│  ├─ log.py                       # logging setup, color formatter, level config
│  ├─ storage.py                   # JsonStore (single file) + GuildStore (one document per server)
│  ├─ checks.py                    # app-command checks: owner_only
│  ├─ messaging.py                 # send_chunked(): split text at Discord's 2000-char limit
│  ├─ embed_text.py                # embed description → (main, quoted) text, fixed parser
│  ├─ ui/
│  │  └─ pagination.py             # Paginator view + page builder (see below)
│  ├─ translation/
│  │  ├─ __init__.py               # provider registry: name → factory
│  │  ├─ base.py                   # TranslationProvider protocol, TranslationResult, errors
│  │  ├─ languages.py              # canonical language codes + normalization
│  │  ├─ service.py                # provider chain, breaker, dest/override logic, output formatting
│  │  ├─ deepl_provider.py
│  │  ├─ libretranslate_provider.py
│  │  └─ googletrans_provider.py
│  ├─ cogs/
│  │  ├─ translate.py              # 🏳️‍⚧️/flag reactions, 'trans' replies
│  │  ├─ langflags.py              # /langflags set|remove|list
│  │  ├─ triggers.py               # trigger matching + /trigger add|remove|list
│  │  ├─ bots.py                   # /bots add|remove|list (approved bots, per server)
│  │  ├─ fun.py                    # is-this-true, LatiBot banter, ⭐, owner shutdown phrases
│  │  └─ admin.py                  # /ping, owner-only /shutdown, /sync, /reload
│  └─ defaults/
│     ├─ flag_lang_map.json        # shipped defaults, copied to data/ on first run
│     └─ triggers.json             # seed triggers for a new server (today's 7 + "riggbot")
├─ data/                           # state the bot writes (gitignored)
│  ├─ flag_lang_map.json           # global
│  └─ guilds/<guild_id>.json       # per server: triggers, approved bots
├─ logs/                           # riggbot.log + rotation (gitignored)
├─ config.example.json             # committed; copied to config.json (gitignored)
├─ .env.example                    # secrets only
├─ requirements.txt                # runtime
├─ requirements-dev.txt            # pytest, pytest-asyncio, pyinstaller
├─ tests/                          # one file per module (see Phase 0/5)
└─ riggbot.spec, start.bat, README.md, ANALYSIS.md, CLEANUP_PLAN.md
```

**Deleted or moved:** the root `riggbot.py` is split into the package. It's removed rather than kept next to a `riggbot/` package of the same name, which would make imports confusing. `flag_lang_map.json` moves to `riggbot/defaults/`, and `tests/test_riggbot.py` is split per module.

**Design notes**

- The bot uses `commands.Bot` with cogs. Each cog gets the `Settings`, the stores and the `TranslationService` through the bot instance, so there are no module globals and tests build a cog with fakes.
- Separate cogs each get their own `on_message` listener. discord.py runs these as separate tasks, so when one message sets off several features, their replies may arrive in a slightly different order than today. That's acceptable. The features never depended on each other.
- `paths.py` resolves `config.json`, `.env`, `data/` and `logs/` relative to the bot's own folder, not the current working directory. That fixes launching from another directory and the PyInstaller exe.
- The `trans` reply keyword stays a constant in `cogs/translate.py`, with a comment pointing to C2. It isn't in config, so nobody "fixes" it by accident.

### Shared building blocks

These components are generic on purpose. Each one is used by more than one feature from the start, and any new command or cog can use them the same way.

| Component | What it does | Used by |
|---|---|---|
| `ui/pagination.py` | `Paginator`: a `discord.ui.View` with ◀ / ▶ buttons and a "page x/y" label. Only the user who ran the command can flip pages; the buttons turn off after a timeout; works with private (ephemeral) replies. `build_pages(lines, max_chars)` packs lines into pages under Discord's limits. | `/trigger list`, `/bots list`, `/langflags list` |
| `storage.GuildStore` | Loads and saves one JSON document per server. Creates a new server's document from a default on first use, caches it in memory, and saves atomically behind a lock. Features read and write their own key (`triggers`, `approved_bots`). | triggers, bots |
| `storage.JsonStore` | The same for a single global file | flag map |
| `messaging.send_chunked` | Sends or replies with text of any length, split at line boundaries under 2000 characters, silent by default, with no mentions allowed unless asked | translations, trigger responses |
| `checks.owner_only` | App-command check against `owner_ids` from config | `/shutdown`, `/sync`, `/reload` |
| `translation` registry | Maps a provider name in config to its class | all translation |

---

## 4. Translation provider interface (C3, M1, M3)

```python
@dataclass(frozen=True)
class TranslationResult:
    text: str
    source_lang: str      # canonical code, detected or given
    target_lang: str      # canonical code
    provider: str

class TranslationProvider(Protocol):
    name: str
    async def translate(self, text: str, target: str, source: str | None = None) -> TranslationResult: ...
    def supports(self, lang: str) -> bool: ...
    async def aclose(self) -> None: ...

class TranslationError(Exception): ...
class UnsupportedLanguageError(TranslationError): ...
class ProviderUnavailableError(TranslationError): ...   # blocked, rate-limited, auth failure, network
```

- **Canonical language codes** are the Google-style codes already used in `flag_lang_map.json` (`en`, `zh-CN`, `zh-TW`, …), compared without regard to case. Each provider translates them to and from its own codes. For example, DeepL uses `EN-US` as a target, `EN` as a source, and `ZH-HANS` for `zh-CN`; LibreTranslate uses `zh-Hans`. This fixes the case-sensitivity bug (ANALYSIS 4.19).
- **One request per translation.** Providers detect the source language as part of `translate(source=None)`, so the separate `detect()` call goes away (ANALYSIS 4.18). If the detected language is already the destination, the service makes a second request into `manual_override_lang`, the same two-step behavior as today.
- **Provider chain.** `translation.providers` in config is an ordered list. The default is `["deepl", "googletrans", "libretranslate"]`. On `UnsupportedLanguageError` or `ProviderUnavailableError`, the service tries the next provider. This covers the flag-map languages DeepL doesn't support (for example `ga`, `sq`, `hy`, `ka`), and gives fallbacks when googletrans is blocked or the DeepL quota runs out.
- **Providers without their settings are skipped.** At startup, a provider missing its key or URL is left out of the chain, with a warning in the log. If no provider is usable, translation is turned off, the translation triggers reply that it's unavailable, and the rest of the bot keeps running.
- **Circuit breaker.** After N consecutive `ProviderUnavailableError`s, a provider is skipped for M minutes (config, defaults 3 and 10). This stops a blocked googletrans from slowing every request.
- **The service owns the user-facing logic.** That means the destination and override rules, the `lang→dest:` header, the 📄/💬 composition, the ` `` `→`"` cleanup, and stripping markdown links. Splitting long output uses `send_chunked`. Providers only translate.

### Providers

| Provider | How it's called | Settings | Notes |
|---|---|---|---|
| **DeepL** (first in the default chain) | Official `deepl` package. It's synchronous, so calls run in `asyncio.to_thread`. | `DEEPL_API_KEY` in `.env` | 500k chars/month free. DeepL asks for a credit card to verify a Free account; whether to do that is the bot owner's decision. Without a key, DeepL is simply skipped. Free keys (ending `:fx`) go to the free endpoint automatically. Returns the detected source language. |
| **googletrans** (kept per C3) | The existing library. One long-lived `Translator`, closed on shutdown. | none | Unofficial and sometimes blocked; the breaker keeps it from slowing things down. The startup self-test uses this same instance (fixes ANALYSIS 4.16). |
| **LibreTranslate** | `httpx` against the REST API (`POST /translate` with `source: "auto"`, which returns the detected language) | `translation.libretranslate.url` in config (default `http://localhost:5000`); optional `LIBRETRANSLATE_API_KEY` in `.env` | Open source, and needs no card if self-hosted: `pip install libretranslate` or Docker on the host PC. The language models take a few GB; `--load-only` limits which languages are downloaded. The public libretranslate.com instance needs a paid key. Lower quality than DeepL or Google, but it isn't blocked or rate-limited when self-hosted. |

Chain order rationale: DeepL gives the best quality. googletrans comes next because its quality is good when it works, and the breaker skips it quickly when it's blocked. LibreTranslate is the dependable last resort. The order is a config setting, so it can change without code changes.

**Adding a provider later** means one new file that implements the protocol, plus one entry in the registry in `translation/__init__.py`.

**Embed text extraction** moves to `embed_text.py`, and its two verified bugs are fixed there: inline `**bold**` splitting a post, and an empty first piece dropping the quoted text. Both get regression tests. The 2.5-second embed polling (`get_embeds`) is removed. It only existed for the auto-translate path; the manual triggers act on messages whose embeds have already loaded.

---

## 5. Triggers, approved bots and flag commands (M4, M9–M12)

All three command groups can be used by anyone (D2). Triggers and approved bots are **per server** (D3), stored in `data/guilds/<guild_id>.json`. The flag map stays global.

### Trigger data

```json
{
  "triggers": [
    { "phrase": "beer",    "response": "mmmmm beer 🍺", "match": "contains", "include_bots": true },
    { "phrase": "riggbot", "response": "I'm riggbot! 🤖", "match": "contains", "include_bots": false }
  ],
  "approved_bots": []
}
```

- A server's document is created the first time it's needed, seeded from `riggbot/defaults/triggers.json`: today's 7 keywords plus the new `riggbot` trigger.
- **Seed defaults for `include_bots`:** the 7 existing keywords get `true`, so approving LatiBot on a server brings back today's behavior for them. The `riggbot` trigger gets `false`. Otherwise riggbot's "I'm riggbot!" sets off LatiBot's `"iM rIgGbOt!"` mock, which contains "riggbot", which sets off "I'm riggbot!" again, in an endless loop.

### How a message is checked against triggers

1. Ignore riggbot's own messages, webhooks and DMs.
2. If the author is a bot, continue only if it's on this server's approved list, and then consider only triggers with `include_bots: true`.
3. For a human author, consider every trigger.
4. Match each trigger case-insensitively using its `match` mode. `contains` is today's substring behavior; `word` matches whole words only; `exact` matches the whole message. Each matching trigger sends its own response, in list order, as today.

### `/trigger`

| Subcommand | Parameters | Behavior |
|---|---|---|
| `/trigger add` | `phrase`, `response`, `match` (optional: `contains` \| `word` \| `exact`, default `contains`), `include_bots` (optional, default `false`) | Adds a trigger to this server, or updates it if the phrase already exists. The reply says which. |
| `/trigger remove` | `phrase` (autocompletes from this server's phrases) | Deletes the trigger |
| `/trigger list` | — | Private, paginated list showing each trigger's match mode and whether it includes bots |

- **Safety:** responses are sent with no mentions allowed, so a trigger can't ping `@everyone`, roles or users. Phrases are limited to 1–100 characters and responses to 1–2000.
- Changes are saved right away and take effect without a restart.

### `/bots`

| Subcommand | Parameters | Behavior |
|---|---|---|
| `/bots add` | `bot` (user picker) | Approves the bot on this server. Refuses users that aren't bots, and refuses riggbot itself. |
| `/bots remove` | `bot` | Removes the approval |
| `/bots list` | — | Private, paginated list of approved bots |

Approval only affects triggers. Other features (the `trans` reply, "is this true", LatiBot banter) work as they do today.

### `/langflags` (renamed from `/edit_flag_lang`)

| Subcommand | Parameters | Behavior |
|---|---|---|
| `/langflags set` | `flag`, `lang_code` | Same as `/edit_flag_lang`. Now checks that `flag` is a single emoji other than 🏳️‍⚧️ (reserved for manual translation), and that `lang_code` is a known canonical code. |
| `/langflags remove` | `flag` | Removes a mapping |
| `/langflags list` | — | Private, paginated list of flag → language |

---

## 6. Configuration (M5, M8)

Settings are merged in this order, lowest priority first: **built-in defaults → `config.json` → environment variables / `.env`**.

- **Secrets stay in `.env` only**: `RIGGBOT_TOKEN`, `DEEPL_API_KEY`, `LIBRETRANSLATE_API_KEY`. They are never read from `config.json`, and they are never logged.
- **The bot never writes `config.json`** (D4). People edit it by hand. It's gitignored, and `config.example.json` is committed as the template.
- **The bot writes only to `data/`**: the flag map and the per-server documents.
- If `config.json` is missing, the bot runs on defaults and env vars and logs a warning. If it's invalid, the bot stops with an error that names the bad key.
- `/reload` (owner only) re-reads `config.json` and `data/` without a restart.

Draft `config.example.json`. The `responses` values shown as `"…"` are today's strings, moved out of the code unchanged.

```json
{
  "owner_ids": [],
  "latibot": { "user_id": null, "name_fallback": "latibot" },
  "responses": {
    "is_this_true": {
      "phrases": ["riggbot is this true"],
      "match_mention": true,
      "answers": ["Yes", "No", "Israel"]
    },
    "star_thanks": "omg thank you so much",
    "latibot_banter": { "dat_me_reply": "…", "mock_reply": "shut up nerd" },
    "shutdown": {
      "phrases": ["say goodbye riggbot", "riggbot, kys"],
      "farewells": ["Goodbye! 👋", "I'm riggbo- oh... okay..."]
    }
  },
  "translation": {
    "providers": ["deepl", "googletrans", "libretranslate"],
    "dest_lang": "en",
    "manual_override_lang": "zh-CN",
    "startup_self_test": true,
    "breaker": { "failures": 3, "cooldown_minutes": 10 },
    "reaction_cooldown_seconds": 30,
    "libretranslate": { "url": "http://localhost:5000" }
  },
  "logging": {
    "level": "INFO",
    "file_level": "DEBUG",
    "library_level": "WARNING",
    "color": "auto",
    "file": "logs/riggbot.log",
    "max_bytes": 1000000,
    "backup_count": 3
  }
}
```

- `match_mention: true` also accepts `@riggbot is this true`, with the mention built from the running bot's ID. That's today's second phrase.
- Env var overrides: `DEST_LANG` and `MANUAL_OVERRIDE_LANG` (kept for compatibility), plus `TRANSLATION_PROVIDERS` (comma-separated), `LIBRETRANSLATE_URL`, `LOG_LEVEL`, `LOG_FILE_LEVEL`, `LOG_COLOR`, and the standard `NO_COLOR`.

---

## 7. Logging (M7, M14)

**Output format.** One line per record:

```
2026-09-27 07:32:00.000 [info] [cogs.translate] Reaction trigger 🏳️‍⚧️ by user=1234… on msg=5678… in #general
2026-09-27 07:32:00.445 [info] [translation] Translated ja→en via deepl (412 chars, 445 ms)
2026-09-27 07:32:01.002 [warning] [translation] googletrans unavailable (HTTP 429); trying libretranslate
2026-09-27 07:32:01.010 [debug] [embed_text] Split description: main='…' quoted='…'
2026-09-27 07:32:05.120 [info] [cogs.triggers] Trigger 'beer' fired for user=… in guild=…
2026-09-27 07:32:09.300 [warning] [discord.gateway] Shard ID None has stopped responding…
```

- **Component** is the logger name without the leading `riggbot.` (`riggbot.cogs.translate` → `cogs.translate`). Library loggers keep their own names (`discord.gateway`). Modules still create loggers with `logging.getLogger(__name__)`; the formatter strips the prefix.
- **Level names** are lowercase: `debug`, `info`, `warning`, `error`, `critical`.
- **Colors** (console only):

| Part | Color |
|---|---|
| Timestamp | gray |
| `[debug]` | cyan |
| `[info]` | blue |
| `[warning]` | yellow |
| `[error]` | red |
| `[critical]` | bold red |
| `[component]` | magenta |
| Message | default terminal color |

- Color is used only when the console supports it (`color: auto`). `always`/`never` force it on or off, and `NO_COLOR` turns it off. On Windows, console escape-code support is switched on at startup with a small `ctypes` call, so no new dependency is needed. The log file uses the same format without color codes.
- **The source of today's messy output is removed:**
  - Log messages that end in `\n` produce blank lines, as does the `=====` banner.
  - Message text with newlines is logged raw, which splits one record over several lines. It will be escaped instead (`repr`-style).
  - `client.run()` attaches discord.py's own log handler in addition to the root one, which likely prints some library lines twice in two formats. It will be called with `log_handler=None`.
- **Levels:**

| Level | Used for |
|---|---|
| debug | Message and embed text, parser output, provider request/response details, trigger-matching decisions, config merge details |
| info | Startup summary (version, config sources, active provider chain, number of servers/triggers/flags, owners set yes/no), ready/reconnect, every trigger that fires (type, user, message, channel), each translation (provider, languages, size, time), every slash command use, and changes to triggers, approved bots or flags |
| warning | Provider skipped or fallen back, breaker opening, missing optional config, deprecated `EMBED_BOT_NAME`, a replied-to message that's been deleted |
| error | Unexpected exceptions, with the stack trace |

- Library loggers (`discord`, `httpx`, `httpcore`, `urllib3`, `deepl`) use `library_level`.
- **Privacy:** message content appears only at debug. The file handler defaults to debug so the content is there when troubleshooting; set `file_level` to `INFO` to keep it out of the file.
- Logs go to `logs/` with rotation, keeping 3 backups instead of 1.

---

## 8. Phases

Each phase is one or more commits on `mh-riggbot`. The bot stays runnable at the end of every phase.

### Phase 0: Safety net
- [x] Fix the 2 stale tests (the `\n` after the language arrow).
- [x] Add **characterization tests**, written against the current code before anything moves:
  - "is this true": both trigger phrases, only in replies, no answer when the replied-to message is riggbot's, the answer comes from exactly `{Yes, No, Israel}`, and the reply is silent (C1). After the move to config, the same tests run against the **default** config.
  - A `trans` substring in a reply (for example "transport") triggers a translation (C2).
  - The translation output format and the override-language behavior.
- [x] These tests move with the code in later phases and must keep passing. They are the proof that C1 and C2 hold.

### Phase 1: Foundation (package, config, logging, storage)
- [ ] Create the `riggbot/` package, `main.py`, `paths.py` and `bot.py`, with a `RiggBot` subclass. Slash-command sync and the self-test run once from `setup_hook` / first ready, not on every `on_ready`.
- [ ] `config.py`: settings dataclasses, merge order, validation, `config.example.json`.
- [ ] `log.py`: the §7 format and colors, levels from config and env, `log_handler=None`.
- [ ] `storage.py`: `JsonStore` and `GuildStore` with atomic save and first-use seeding from `defaults/`.
- [ ] `checks.py`, `messaging.py`.

### Phase 2: Translation rework
- [ ] `translation/` package: interface, language normalization, registry, the three providers, and the service with the provider chain, skipping of unconfigured providers, and the circuit breaker.
- [ ] Remove auto-translation of embed-bot posts and `get_embeds` polling. Retire `EMBED_BOT_NAME` with a warning if it's set.
- [ ] `embed_text.py` with the two parser fixes and regression tests.
- [ ] Long replies go through `send_chunked`. Give the user a distinct message when every provider fails, instead of "couldn't find anything to translate".

### Phase 3: Cogs and commands
- [ ] `ui/pagination.py`: `Paginator` and `build_pages`.
- [ ] `translate` cog: raw reaction events, fetching the message when it isn't cached. Keep the "first reaction only" rule, and add the per-message cooldown (D5). Keep the `'trans' in content` reply trigger as is, and fetch the replied-to message only when a trigger matches. Handle deleted or missing replied-to messages quietly.
- [ ] `langflags` cog: `/langflags set|remove|list`, with validation. The map defaults to `{}` if the file is missing.
- [ ] `triggers` cog: matching (§5) and `/trigger add|remove|list`.
- [ ] `bots` cog: `/bots add|remove|list`.
- [ ] `fun` cog: is-this-true (config-driven, `client.user.id`), LatiBot banter, ⭐ (silent), and the owner shutdown phrases gated on `owner_ids`.
- [ ] `admin` cog: `/ping`, and owner-only `/shutdown`, `/sync` and `/reload`.

### Phase 4: Tooling and docs
- [ ] `requirements.txt` (runtime: `discord.py`, `python-dotenv`, `googletrans`, `deepl`, `httpx`) and `requirements-dev.txt`, with versions pinned to known-good releases.
- [ ] CI: a test job on push and PR using **Python 3.14** (D6). Update the actions to current major versions. Keep the PyInstaller job as manual-dispatch, on a PyInstaller release that supports 3.14.
- [ ] `riggbot.spec`: new entry point `main.py`, and bundle `riggbot/defaults/`.
- [ ] `start.bat`: `cd` to the script's own folder and use `.venv` if it exists.
- [ ] `.gitignore`: add `config.json`, `data/` and `logs/`; remove `riggbot token.txt`.
- [ ] `.env.example` holds secrets only.
- [ ] Rewrite the README:
  - Features, including the deliberate `trans` behavior (C2).
  - Triggers and approved bots.
  - Commands.
  - Config and providers, including LibreTranslate self-hosting.
  - Logging.
  - A development section: project layout, running the tests, how to add a cog or command, and the shared building blocks from §3.

### Phase 5: Test coverage
- [ ] Config merge order and validation, including the default "is this true" values.
- [ ] `GuildStore`/`JsonStore`: seeding, per-server isolation, atomic save.
- [ ] Trigger matching: the three match modes, and approved-bot gating combined with `include_bots`.
- [ ] `/bots` and `/langflags` validation.
- [ ] Pagination: page building and the check that only the command's user can flip pages.
- [ ] Translation service against fake providers: chain fallback, skipping unconfigured providers, breaker, override logic.
- [ ] Each provider's language-code mapping.
- [ ] Cog handlers with fake Discord objects.
- [ ] No test calls a real network service.

---

## 9. Decisions

All settled on 2026-09-27.

| # | Decision | Outcome |
|---|---|---|
| **D1** | Translation providers | **DeepL** first, then googletrans, then **LibreTranslate** as a second fallback. DeepL stays optional: the bot owner decides whether to verify a Free account with a card, and without a key it's skipped. |
| **D2** | Who can use `/trigger`, `/langflags` and `/bots` | **Everyone.** It's a bot for a friends' server. Only `/shutdown`, `/sync` and `/reload` are owner-only. |
| **D3** | Scope of triggers | **Per server.** Approved bots are per server too, because they only affect triggers. The flag map stays global. |
| **D4** | Where state lives | `config.json` is edited by people and never written by the bot. `data/` holds everything the bot writes. |
| **D5** | Reaction re-trigger | Per-message cooldown, 30 s by default, configurable |
| **D6** | Python version | **3.14**, matching both the dev PC and the hosting server. CI tests on 3.14. |

---

## 10. Out of scope

- Changing when "is this true" fires or its default answers (C1).
- Narrowing the `trans` reply trigger (C2).
- Changing the translation output format.
- A database. JSON files are enough at this size.
- Hosting or deployment changes beyond `start.bat` and the PyInstaller build. Setting up a LibreTranslate server is documented but not automated.
