import asyncio
import discord
import logging
import os
import re
from dotenv import load_dotenv

# Load .env variables at the top
load_dotenv()

# Ensure `Translator` symbol exists at module import time so frozen builds
# can reference the class and PyInstaller will detect the dependency when
# googletrans is available in the environment.
try:
    from googletrans import Translator
except Exception:
    Translator = None


# Globals that will be initialized by `init_bot()` or `run_bot()`.
TOKEN = None
EMBED_BOT_NAME = None
DEST_LANG = None
MANUAL_OVERRIDE_LANG = None
client: discord.Client | None = None
translator = None

# Keyword triggers dictionary
KEYWORD_RESPONSES = {
    'beer': 'mmmmm beer 🍺',
    'weed': 'mmmmm weed 🍃',
    'awaga': 'waga baba bobo',
    'one piece': 'THE ONE PIECE IS REAL! 🏴\u200d☠️',
    'it just works': 'my old uncle ToddBot used to say that all the time...',
    'skyrim': 'my old uncle ToddBot used to release that game all the time...',

}


# TODO learn what this does
def init_logging():
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def init_bot():
    """Initialize global bot dependencies (discord client, translator).

    Call this from CI setup or before `run_bot()` to configure the runtime without starting the client.
    """
    global client, translator

    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    intents.messages = True

    logging.debug(f'Using intents: {intents}')

    client = discord.Client(intents=intents)
    try:
        client.event(on_ready)
        logging.info('Registered on_ready handler (event)')
        client.event(on_message)
        logging.info('Registered on_message handler (event)')
        client.event(on_reaction_add)
        logging.info('Registered on_reaction_add handler (event)')
    except Exception as e:
        # If handlers are not yet defined at init time, log the exception for visibility
        logging.exception(f'Error registering listeners: {e}')

    # Initialize translator (googletrans) if available, else use a dummy async-compatible translator
    try:
        from googletrans import Translator as _TranslatorCls
    except Exception:
        _TranslatorCls = None

    if _TranslatorCls:
        translator = _TranslatorCls()
        logging.info('Translator initialized. (googletrans available)')
    else:
        class _DummyTranslator:
            async def detect(self, text):
                return type('D', (), {'lang': 'en'})()

            async def translate(self, text, dest='en'):
                return type('R', (), {'text': text})()

        translator = _DummyTranslator()
        logging.info(
            'Dummy translator initialized (googletrans not available)')


async def on_ready():
    logging.info(f'{client.user} is online')


async def on_message(message):
    if message.author == client.user:  # ignore messages from the bot itself
        return

    if message.webhook_id is not None:
        return

    # TODO: further refine filtering and avoid processing non-relevant messages

    if EMBED_BOT_NAME in message.author.name.lower():
        logging.info(
            f'Message from embed bot "{message.author.name}" detected')
        await handle_message(message, is_manual=False)

    # If this message is a reply, handle it
    try:
        if message.type == discord.MessageType.reply and message.content:
            await handle_reply(message)
    except Exception as e:
        logging.exception(f'Error handling reply trigger: {e}')

    # Triggered word responses
    content_lower = message.content.lower()
    for keyword, response in KEYWORD_RESPONSES.items():
        if keyword in content_lower:
            await message.channel.send(response, silent=True)

    if not message.author.name == 'riggoon':
        return

    if 'say goodbye riggbot' in message.content.lower():
        await message.channel.send('Goodbye! 👋', silent=True)
        await client.close()

    if 'riggbot' in content_lower:
        await message.channel.send('I\'m riggbot! 🤖', silent=True)


async def on_reaction_add(reaction, user):
    # star recognition
    if reaction.message.author == client.user and reaction.emoji == '⭐' and reaction.count == 1:
        await reaction.message.channel.send('omg thank you so much')

    # ignore bot's own reactions and reactions to bot's message
    if user == client.user or reaction.message.author == client.user:
        return

    if reaction.emoji == '🏳️‍⚧️' and reaction.count == 1:
        logging.info('Translation trigger detected by reaction')
        msg = reaction.message
        await handle_message(msg, is_manual=True)
        logging.info('Handled manual translation trigger from reaction')


async def handle_reply(message):
    msg_content = message.content.lower()
    if message.author == client.user:
        return
    ref_msg = None
    # message.reference may contain resolved message or just ids
    if getattr(message.reference, 'resolved', None):
        ref_msg = message.reference.resolved
    elif getattr(message.reference, 'message_id', None):
        ref_msg = await message.channel.fetch_message(message.reference.message_id)

    if not ref_msg:
        logging.warning('No reference message found for reply trigger')
        return

    if 'trans' in msg_content:
        logging.info('Translation trigger detected in reply')
        if ref_msg and not ref_msg.author == client.user:
            await handle_message(ref_msg, is_manual=True)
            logging.info('Handled manual translation trigger from reply')

    if 'riggbot is this true' in msg_content or '<@1293252648803237899> is this true' in msg_content:
        logging.info('Truth check trigger detected in reply')
        if ref_msg and not ref_msg.author == client.user:
            await message.reply('TODO: create truth check logic and responses', silent=True)
            # TODO: implement truth check logic and responses
            logging.info('Handled truth check trigger from reply')


async def handle_message(message, is_manual: bool):
    logging.info(f'Handling message translation (manual={is_manual})')
    translations = []
    # multiple attempts to make sure it gets the embed on a recent message
    embeds = None
    max_attempts = 5
    delay = 0.5  # seconds between attempts
    for attempt in range(max_attempts):
        if message.embeds:
            embeds = message.embeds
            logging.debug(f'Embed found on attempt {attempt + 1}')
            break
        if attempt < max_attempts - 1:
            await asyncio.sleep(delay)
    if embeds:
        emb_trans = await translate_embed(embeds[0], is_manual)
        if emb_trans:
            translations.append(emb_trans)
        logging.info('Message embed translated')
    elif message.content:
        con_trans = await translate_text(message.content, is_manual)
        if con_trans:
            translations.append(con_trans)
            logging.info('Message content translated')

    if translations:
        await message.reply('\n'.join(translations), silent=True)
    elif is_manual:
        await message.reply('Sorry, I couldn\'t find anything to translate in that', silent=True)


async def translate_embed(embed, is_manual: bool) -> str | None:
    description = embed.to_dict().get("description")
    if description:
        # regex split to get text around 'quoted' seperater and post's metadata (views, likes, etc.)
        text_blobs = re.split(r"\W*\*\*\[.*\*\*\W*", description)
        logging.info(f'Raw Description Text Blobs: {text_blobs}')

        if ''.join(text_blobs).strip() == '':
            logging.info(
                'Description text blobs are empty after stripping, skipping translation')
            return None

        text_blobs[0] = "📄 " + await translate_text(text_blobs[0], is_manual)
        if len(text_blobs) > 1:
            text_blobs[1] = "💬 " + await translate_text(text_blobs[1], is_manual)
        if len(text_blobs) > 2:
            logging.error(f'Unexpected Text Blob(s): {text_blobs[2:]}')
            logging.debug(f'Removing unexpected text blobs')
            text_blobs = text_blobs[:2]
        translation = '\n'.join(text_blobs)
        return translation


async def translate_text(content: str, is_manual: bool) -> str | None:
    """Translate text content and return translation.

    Args:
        content: The text content to translate
        is_manual: Whether this is a manual translation trigger

    Returns:
        Translated string or None if no translation needed
    """
    try:
        logging.info(f'Translating text (manual={is_manual}): {content}')
        translation = None
        detected = await asyncio.to_thread(translator.detect, content)
        if detected.lang != DEST_LANG:
            # need to translate
            logging.info(
                f'Translating from {detected.lang} to {DEST_LANG}')
            translated = await asyncio.to_thread(translator.translate, content, dest=DEST_LANG)
            translation = f"{detected.lang}→{DEST_LANG}: {translated.text}"
        elif is_manual and detected.lang == DEST_LANG:
            # if manual and already in dest lang, translate to override lang
            logging.info(
                f'Override: translating from {DEST_LANG} to {MANUAL_OVERRIDE_LANG}')
            translated = await asyncio.to_thread(translator.translate, content, dest=MANUAL_OVERRIDE_LANG)
            translation = translated.text
        return translation
    except Exception as e:
        logging.error(f'Translation error: {e}')
    return None


def run_bot():
    # Initialize and run the bot. For CI, call `init_bot()` and avoid calling `run_bot()`.
    init_logging()
    init_bot()
    # set module-level globals so event handlers can access them
    global TOKEN, EMBED_BOT_NAME, DEST_LANG, MANUAL_OVERRIDE_LANG

    TOKEN = bot_token()
    if not TOKEN:
        raise ValueError('No token provided to run the bot')

    EMBED_BOT_NAME = os.getenv('EMBED_BOT_NAME', '') or ''
    EMBED_BOT_NAME = EMBED_BOT_NAME.lower()
    DEST_LANG = os.getenv('DEST_LANG', 'en') or 'en'
    MANUAL_OVERRIDE_LANG = os.getenv(
        'MANUAL_OVERRIDE_LANG', 'zh-CN') or 'zh-CN'

    logging.info(f'Embed bot name filter: "{EMBED_BOT_NAME}"')
    logging.info(f'Default destination language: {DEST_LANG}')
    logging.info(f'Manual override language: {MANUAL_OVERRIDE_LANG}')

    logging.info('Starting Discord client...')
    client.run(TOKEN)

# Load bot token from .env file (own function for better error handling)


def bot_token() -> str:
    # load variables from a local .env into the environment
    token = os.getenv('RIGGBOT_TOKEN')

    if token and str(token).strip():
        logging.info('Loaded token from .env')
        return str(token).strip()

    # Nothing found — provide a helpful error message
    raise FileNotFoundError(
        "No RIGGBOT_TOKEN found in .env.\n"
        "Create a .env file in the project root with the line:\n"
        "RIGGBOT_TOKEN=your_bot_token_here\n"
        "Only .env format is supported for token ingestion.")


if __name__ == '__main__':
    run_bot()
