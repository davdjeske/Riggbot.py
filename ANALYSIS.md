# Riggbot — Repository Analysis

_Analysis of `main` @ `d456712` (2026-09-23), written 2026-09-26 as groundwork for the `mh-riggbot` cleanup._

## 1. Summary

Riggbot is a single-file (~490 lines) `discord.py` bot. It was built to translate the embeds posted by a separate link-replacement bot (fxtwitter-style embeds). That bot now does its own translations, so riggbot's main job is mostly redundant. What's left:

- **Translation** (automatic on embed-bot posts, plus manual triggers), backed by `googletrans`, an unofficial Google Translate scraper that is unreliable and sometimes gets blocked.
- **Social / banter features**: keyword responses, LatiBot banter, a "is this true" reply, a star-reaction thank-you, and owner-only "commands".
- **Two slash commands**: `/ping` and `/edit_flag_lang`.

The code works for its intended use, but it has grown by accretion. It relies on module-level globals, identifies users and bots by hardcoded usernames and IDs, and does a lot of loose substring matching. It also has several edge-case bugs in the embed parser and the reaction handling. Tests exist but are partly stale (2 of 26 fail), and CI never runs them.

---

## 2. Repository layout

| Path | Purpose | Notes |
|---|---|---|
| [riggbot.py](riggbot.py) | Entire bot: config, init, event handlers, translation | Only source module |
| [flag_lang_map.json](flag_lang_map.json) | Flag emoji → language code map (84 entries) | Read at startup, **rewritten at runtime** by `/edit_flag_lang` |
| [tests/test_riggbot.py](tests/test_riggbot.py) | pytest suite (env loading, `translate_text`, `process_embed`) | 24 pass / 2 fail |
| [requirements.txt](requirements.txt) | Runtime + build + test deps in one file | `googletrans==4.0.2`, `discord.py>=2.2.0`, `python-dotenv`, `pyinstaller`, `pytest*` |
| [riggbot.spec](riggbot.spec) | PyInstaller one-file build | Does not bundle `flag_lang_map.json` |
| [.github/workflows/build.yml](.github/workflows/build.yml) | Windows zip + PyInstaller artifacts | Manual dispatch only, no tests |
| [start.bat](start.bat) | `PYTHONUTF8=1` + `py ./riggbot.py` | Uses the global interpreter, not a venv |
| [.env.example](.env.example), [README.md](README.md), [pytest.ini](pytest.ini), [.gitignore](.gitignore) | Config/docs | README is out of date (see §7) |

---

## 3. Architecture and control flow

```
run_bot()
 ├─ init_logging()            console + rotating riggbot.log (1 MB × 2)
 ├─ init_bot()
 │   ├─ bot_token()           RIGGBOT_TOKEN from .env (required)
 │   ├─ init_env_vars()       EMBED_BOT_NAME, DEST_LANG, MANUAL_OVERRIDE_LANG, flag_lang_map.json
 │   ├─ Translator()          global googletrans client
 │   ├─ commands.Bot('!')     + slash commands /ping, /edit_flag_lang (closures)
 │   └─ client.event(...)     on_ready, on_message, on_reaction_add
 └─ client.run(TOKEN)

on_ready          → translation_test() → tree.sync()
on_message        → LatiBot banter → embed-bot auto-translate → handle_reply()
                    → keyword responses → owner-only "commands"
on_reaction_add   → ⭐ on bot msg → 🏳️‍⚧️ manual translate → flag emoji src-override translate
handle_reply      → "trans" → translate referenced msg; "riggbot is this true" → random answer

process_message → get_embeds (poll 5×0.5s) → process_embed (regex split) → translate_text
translate_text  → strip md links → translator.detect → translator.translate → format
```

State lives in module globals (`client`, `translator`, `TOKEN`, `EMBED_BOT_NAME`, `DEST_LANG`, `MANUAL_OVERRIDE_LANG`, `flag_lang_map`). These are set by `init_bot()` and changed directly by the tests.

### Feature inventory

| Feature | Trigger | Location | Depends on translation? |
|---|---|---|---|
| Auto-translate embed-bot posts | author name contains `EMBED_BOT_NAME` and message has embeds | [riggbot.py:229-237](riggbot.py#L229-L237) | Yes |
| Manual translate | 🏳️‍⚧️ reaction (first only) | [riggbot.py:283-287](riggbot.py#L283-L287) | Yes |
| Manual translate w/ source override | flag reaction in `flag_lang_map` | [riggbot.py:290-297](riggbot.py#L290-L297) | Yes |
| Manual translate via reply | reply whose content contains `trans` | [riggbot.py:313-316](riggbot.py#L313-L316) | Yes |
| `/edit_flag_lang` | slash command | [riggbot.py:92-101](riggbot.py#L92-L101) | Yes |
| Launch translation self-test | `on_ready` | [riggbot.py:182-192](riggbot.py#L182-L192) | Yes |
| `/ping` | slash command | [riggbot.py:88-90](riggbot.py#L88-L90) | No |
| Keyword responses | substring in any message | [riggbot.py:28-36](riggbot.py#L28-L36), [246-250](riggbot.py#L246-L250) | No |
| LatiBot banter (2 responses) | author name contains `latibot` + exact text | [riggbot.py:217-223](riggbot.py#L217-L223) | No |
| "is this true" | reply containing phrase or hardcoded mention | [riggbot.py:319-324](riggbot.py#L319-L324) | No |
| ⭐ thank-you | first ⭐ on a bot message | [riggbot.py:276-277](riggbot.py#L276-L277) | No |
| Owner shutdown / "I'm riggbot!" | hardcoded usernames `riggoon`, `sarcly` | [riggbot.py:253-263](riggbot.py#L253-L263) | No |

---

## 4. Bugs and correctness issues

Ordered roughly by impact. Items marked **(verified)** were reproduced locally.

### 4.1 Embed parser (`process_embed`)

1. **Bold text inside a post splits it and drops content (verified).** The footer branch of the split regex, `\n*\*\*[^\n]*\*\*\s*`, matches *any* `**bold**` span. It doesn't only match the stats footer. `"this is **very** important"` becomes `['this is ', 'important']`: the bolded word disappears, and the second half is labelled as a 💬 quoted post. [riggbot.py:378-379](riggbot.py#L378-L379)
2. **An empty leading blob throws away everything after it (verified).** The cleanup loop truncates the list at the first empty blob (`text_blobs[:i]`) instead of filtering empty blobs out. A description that starts with the quote header (a quote-tweet with no caption) splits into `['', 'quoted text']`, is truncated to `[]`, and nothing is translated. [riggbot.py:382-384](riggbot.py#L382-L384)
3. Only `embeds[0]` is looked at, and only its `description` field. Multi-embed posts and titles/fields are ignored. [riggbot.py:353](riggbot.py#L353)

### 4.2 Reactions

4. **Reactions on uncached messages are ignored.** `on_reaction_add` only fires for messages in discord.py's message cache: messages sent since startup, capped at 1000. Reacting to anything older silently does nothing. `on_raw_reaction_add` is the reliable event.
5. **Re-triggering via `reaction.count == 1`.** Adding, removing and re-adding a reaction triggers again, as the in-code TODO notes. So does removing everyone's reaction and adding a new one. [riggbot.py:269-274](riggbot.py#L269-L274)
6. **`flag_lang_map` may be `None`.** If `flag_lang_map.json` is missing or invalid, `init_env_vars` logs a warning and continues. After that, every reaction raises `TypeError` at `reaction.emoji in flag_lang_map`, and `/edit_flag_lang` raises on `flag_lang_map[flag] = ...`. [riggbot.py:290](riggbot.py#L290), [riggbot.py:96](riggbot.py#L96)
7. The ⭐ response ignores the `silent=True` convention used everywhere else. [riggbot.py:277](riggbot.py#L277)

### 4.3 Replies and triggers

8. **`'trans' in msg_content` is far too broad.** Any reply containing "transfer", "transport", "transparent", etc. triggers a translation. [riggbot.py:313](riggbot.py#L313)
9. `handle_reply` calls `fetch_message` (an API request) for every reply whose reference isn't resolved, even when there's no trigger phrase. [riggbot.py:306-307](riggbot.py#L306-L307)
10. `message.reference.resolved` can be a `DeletedReferencedMessage`. It is truthy but has no `.embeds` or `.content`, so it raises `AttributeError`. The broad `try/except` in `on_message` catches it, but it logs a full stack trace. `fetch_message` can also raise `NotFound`.
11. The bot's own mention ID is hardcoded (`<@1293252648803237899>`). It should use `client.user.id`, and should also match the `<@!id>` nickname-mention form. [riggbot.py:319](riggbot.py#L319)

### 4.4 Message handling

12. **Keyword responses use raw substring matching** (`'beer' in content`). This matches inside other words ("weed" → "tweed", "beer" → "beers"). Several keywords in one message cause several separate sends. Other bots' messages are not filtered, so LatiBot's output (including its translations) can trigger keyword spam, which is also a potential bot-to-bot loop. [riggbot.py:246-250](riggbot.py#L246-L250)
13. **Discord's 2000-character limit is not handled.** A long post plus a quoted post, translated, can exceed 2000 characters. The `message.reply` then raises `HTTPException`, and the user gets nothing. [riggbot.py:365](riggbot.py#L365)
14. `get_embeds` polls `message.embeds` 5 × 0.5 s. This only works because discord.py updates cached message objects in place when an edit event arrives. It works, but it's a hidden dependency. `on_message_edit` / `on_raw_message_edit` is the idiomatic way to catch late-unfurled embeds. [riggbot.py:327-338](riggbot.py#L327-L338)

### 4.5 Lifecycle

15. **`on_ready` can fire many times** (on every reconnect/resume). Each time, it re-runs the translation self-test and `tree.sync()`. Syncing on every reconnect is rate-limited and unnecessary. The usual pattern is to sync once in `setup_hook` or from an owner-only command. [riggbot.py:198-203](riggbot.py#L198-L203)
16. The global `Translator` (an httpx client) is never closed. `translation_test` creates a second, separate `Translator`, so it doesn't actually test the instance the bot uses. [riggbot.py:75](riggbot.py#L75), [riggbot.py:184](riggbot.py#L184)
17. The `try/except` around `client.event(...)` registration can't fail the way its comment describes. The handlers are module-level functions, already defined by the time `init_bot()` runs. [riggbot.py:103-112](riggbot.py#L103-L112)

### 4.6 Translation logic

18. **Two network calls per text.** `translator.detect()` followed by `translator.translate()` doubles the request count against a service that already rate-limits and blocks. `translate()` already returns `.src`, so a single call can detect and translate together. [riggbot.py:441-449](riggbot.py#L441-L449)
19. `DEST_LANG` is compared to the detected code case-sensitively (`'EN'` ≠ `'en'`), and region variants like `zh-CN` vs `zh-cn` aren't normalized.
20. The "logging sometimes doesn't appear" TODO ([riggbot.py:456-459](riggbot.py#L456-L459)) is worth checking against **a second running instance**. If the exe and a `python riggbot.py` run are online at the same time, whichever handles the event does the translating and writes the log. The other one's console stays quiet.

---

## 5. Security and robustness

| Issue | Where | Risk |
|---|---|---|
| `/edit_flag_lang` has no permission check or input validation. Anyone in any server can rewrite `flag_lang_map.json` on disk with arbitrary keys/values. | [riggbot.py:92-101](riggbot.py#L92-L101) | Medium: data corruption, map pollution |
| Privileged actions (shutdown) are gated by **username string** (`riggoon`, `sarcly`). Usernames can change and be re-claimed. User IDs don't change. | [riggbot.py:253](riggbot.py#L253) | Low–medium |
| The embed bot and LatiBot are identified by **username substring**. Any user or bot whose name contains the substring matches. | [riggbot.py:218](riggbot.py#L218), [222](riggbot.py#L222), [229](riggbot.py#L229) | Low |
| Full message contents are logged at INFO level to `riggbot.log`. | throughout `translate_text` / `process_embed` | Privacy/noise |
| `riggbot.log`, `flag_lang_map.json` and `.env` paths are relative to the **current working directory**, not the script/exe location. | [riggbot.py:53](riggbot.py#L53), [97](riggbot.py#L97), [147](riggbot.py#L147) | Breaks when launched from elsewhere |
| A custom emoji is hardcoded (`<:clueless:1150947090340515880>`) and only renders in the guild that owns it. | [riggbot.py:35](riggbot.py#L35) | Cosmetic |

---

## 6. The translation dependency

`googletrans` 4.0.2 scrapes the public Google Translate web endpoint. It has no API key, SLA or quota guarantees. Google periodically blocks or changes the endpoint, and every request here costs two calls (see 4.18). Now that the link-replacement bot translates on its own, there are three reasonable directions:

| Option | Effort | Notes |
|---|---|---|
| **A. Remove translation entirely** | Low | Deletes roughly 40% of `riggbot.py`, the `googletrans` dependency, `flag_lang_map.json`, `/edit_flag_lang`, three env vars and most of the tests. Riggbot becomes a pure fun/utility bot. |
| **B. Keep manual-only translation on a real API** | Medium | Drop auto-translate of embed-bot posts (now duplicated by LatiBot). Keep the 🏳️‍⚧️/flag/reply triggers behind a small `Translator` interface backed by an official API with a free tier: DeepL API Free (500k chars/mo), Google Cloud Translation (500k chars/mo free), Azure Translator (2M chars/mo free), or self-hosted LibreTranslate. Needs an API key in `.env`. |
| **C. Keep googletrans, harden it** | Low | Single-call translate, backoff/cooldown, a circuit breaker that disables translation after repeated failures, and clearer user-facing errors. Still unreliable. |

**Recommendation:** **B**, or **A** if manual translation isn't used much. Either way, remove the automatic embed-bot translation, because it duplicates what LatiBot now does. Isolating translation behind a single interface also makes the backend easy to swap or delete later.

---

## 7. Code quality and maintainability

- **One module, global state.** Config, Discord wiring, parsing and translation are all in `riggbot.py` with mutable globals. The tests have to poke `riggbot.translator`, `riggbot.DEST_LANG` etc. directly. A small package (`config`, `translation`, `embeds`, and cogs for `fun` / `translate` / `admin`) with a config dataclass would make each piece testable on its own.
- **`commands.Bot` with an unused `!` prefix.** No prefix commands exist. Overriding `on_message` via `client.event` also replaces `Bot`'s default handler, so `process_commands` never runs anyway. Use either `discord.Client` + `app_commands.CommandTree`, or `commands.Bot` with cogs, but pick one on purpose.
- **Hardcoded content scattered through handlers.** Keyword responses, LatiBot banter, "is this true" answers, the ⭐ reply, the shutdown lines, privileged usernames and the bot ID are all inline. Moving them into one config/data file (like `flag_lang_map.json` already is) would make them easy to edit.
- **Owner "commands" parsed from free text** (`'riggbot, kys' in content`). These should be owner-only slash commands (`/shutdown`, and later `/sync`, `/reload`).
- **Inconsistent typing and docstrings.** Some functions are annotated, handlers aren't. Triple-quoted strings are used as block comments in the middle of functions ([riggbot.py:390-394](riggbot.py#L390-L394), [471-477](riggbot.py#L471-L477)).
- **Logging.** There are no module-level loggers (`logging.getLogger(__name__)`), and levels are used unevenly: lots of INFO that should be DEBUG, and ERROR for an expected case ([riggbot.py:411](riggbot.py#L411)). The existing TODO at [riggbot.py:42-43](riggbot.py#L42-L43) already calls this out.
- **Stale TODO**: "implement testing :clueless:" ([riggbot.py:66](riggbot.py#L66)). Tests now exist.

---

## 8. Tests

Ran locally (Python 3.14, fresh venv from `requirements.txt`):

```
2 failed, 24 passed, 45 warnings
FAILED TestTranslateText::test_translates_foreign_text_to_dest_lang         expected 'zh-CN→en: hello', got 'zh-CN→en:\nhello'
FAILED TestTranslateText::test_manual_translates_foreign_text_to_dest_lang  expected 'ja→en: hello',    got 'ja→en:\nhello'
```

The failures are stale assertions. Commit `0468d18` changed the output format to put a newline after the language arrow, and these two tests weren't updated. The warnings are `asyncio.iscoroutinefunction` deprecations from inside discord.py on Python 3.14; they aren't from this code.

Gaps:

- No coverage of `on_message`, `on_reaction_add`, `handle_reply`, `process_message`, `get_embeds`, or `/edit_flag_lang`.
- No tests for the two parser bugs in §4.1.
- Every env test calls the full `init_bot()`, which builds a real `Translator` and `commands.Bot` and reads `flag_lang_map.json` from the CWD. They are really integration tests of init, not unit tests of config parsing.
- Tests mutate module globals and never restore them, so tests can affect each other depending on order.
- `pytest`/`pytest-asyncio` are in the runtime `requirements.txt`.

---

## 9. Build, CI and docs

- **CI never runs on push.** The workflow triggers on `push` to `main`, but both jobs have `if: github.event_name == 'workflow_dispatch'`, so push runs skip every job. There is **no test job**.
- `actions/setup-python@v4` is outdated (v5 is current). CI pins Python 3.11 while local dev is on 3.14.
- The `build` job zips the entire checkout. That's a source archive with no real build step.
- **PyInstaller spec doesn't bundle `flag_lang_map.json`** (`datas=[]`). The exe only works if the JSON and `.env` sit in the CWD it's launched from.
- `requirements.txt` mixes runtime, build (`pyinstaller`) and test deps, and has no upper bounds or lockfile.
- `start.bat` runs `py ./riggbot.py` with the global interpreter, not `.venv`, and its CWD is wherever it was launched from.
- **README is out of date.** It describes the bot only as a translator. It says `EMBED_BOT_NAME` is required (the code treats it as optional), and it doesn't document the reactions, reply triggers, slash commands, `flag_lang_map.json`, the fun features, or how to run the tests.
- `.gitignore` still lists the legacy `riggbot token.txt` and starts with a blank line.

---

## 10. Proposed cleanup plan

Suggested order. Each phase is independently shippable.

**Phase 0: Decide the translation direction** (§6: A, B or C). Most of the later phases depend on it.

> Lets go with B, this aligns more with the creators requirements. Riggbot can do translation on manual trigger or based on keyword. Drop the auto embed bot translation functionality.

**Phase 1: Quick fixes (low risk)**
- Fix the 2 stale tests.
- Guard `flag_lang_map is None` and default it to `{}`.
- Fix the blob filter (filter empty blobs instead of truncating), and anchor the footer regex so inline `**bold**` doesn't split posts.
- Tighten the `trans` reply trigger (whole word / explicit command) and only fetch the referenced message when a trigger matches.
- Use `client.user.id` instead of the hardcoded mention.
- Add `silent=True` to the ⭐ reply, and truncate or split replies over 2000 characters.
- Move `tree.sync()` and the self-test out of `on_ready`.

> The 'trans' unintened triggers is an intentional design choice by the creator. do not fix that, just document.

**Phase 2: Translation rework** (per Phase 0)
- Remove the auto-translate of embed-bot posts.
- Either delete translation entirely, or put it behind a `Translator` interface with a single-call detect+translate on a supported API, plus cooldown/circuit-breaker behavior.

> Yes, lets make a standard interface to slot in whatever translation provider we want. Per the creator's requirements, keep the original googletrans as one of the provider options. But lets add at least one other option that can work more consistently.

**Phase 3: Structure and config**
- Split into a small package with cogs, and switch reactions to `on_raw_reaction_add`.
- Move all hardcoded strings, usernames and IDs into config. Identify users and bots by **ID**.
- Replace text-parsed owner commands with owner-only slash commands, and add a permission check to `/edit_flag_lang` (if it survives).
- Resolve file paths relative to the script/exe, and move logging to module loggers with sensible levels.

**Phase 4: Tooling**
- Split `requirements.txt` into runtime and dev, and pin versions.
- Add a CI test job on push/PR, bump actions, and align the Python version.
- Bundle data files in the PyInstaller spec (or keep them external on purpose, and document that).
- Make `start.bat` use the venv and `cd` to its own directory.
- Rewrite the README to cover features, config, commands, and running tests.

---

> The plan looks good. I have a few more comments i want to make.
> - Lets add the ability to add new trigger phrases via a /trigger command to replace the hardcoded list of responses to certain substrings in messages. This way, we can add new ones without having to update the code and relaunch the bot.
> - It may be benefital to add a config.json to the bot for storing things we want to persist between runs. 
> - you are free to do whatever restruturing and reorganizing that is needed for improvements, so long as the do not violate the creator's requirements. This includes deleting files and creating folders if needed.
> - I want to improve the logging of the bot. Add propper logging with more info level logs and proper debug level logs. Log level should be configurable via config.json and env vars. The current logs also have terrible formatting and are hard to read. It would be nice to cleanup the formatting so log lines are clearly denoted and if they could be colorized for easier reading.
