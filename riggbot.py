import asyncio
import discord
import logging
import os
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


def init_logging():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
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

    # TODO: refine filtering and avoid processing non-relevant messages

    if EMBED_BOT_NAME in message.author.name.lower():
        # multiple attempts to make sure it gets the embed
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
            translated_text = translate_embeds(embeds, is_manual=False)
            if translated_text:
                logging.info('Sending translations')
            if translated_text:
                await message.reply(translated_text)


    # If this message is a reply and contains the content trigger, handle it
    try:
        if message.type == discord.MessageType.reply and message.content:
            await handle_reply(message)
    except Exception as e:
        logging.exception(f'Error handling reply trigger: {e}')

    # triggered word responses
    if 'beer' in message.content.lower():
        await message.channel.send('mmmmm beer 🍺')

    if 'weed' in message.content.lower():
        await message.channel.send('mmmmm weed 🍃')

    if 'awaga' in message.content.lower():
        await message.channel.send('waga baba bobo')

    if 'one piece' in message.content.lower():
        await message.channel.send('THE ONE PIECE IS REAL! 🏴‍☠️')

    if 'it just works' in message.content.lower():
        await message.channel.send('my old uncle ToddBot used to say that all the time...')

    if 'skyrim' in message.content.lower():
        await message.channel.send('my old uncle ToddBot used to release that game all the time...')

    if 'david bot' in message.content.lower() or 'davidbot' in message.content.lower():
        await message.channel.send('thats not my name bitch')

    if not message.author.name == 'riggoon':
        return

    if 'say goodbye riggbot' in message.content.lower():
        await message.channel.send('Goodbye! 👋')
        # gracefully close the client instead of exiting the interpreter
        await client.close()

    if 'python' in message.content.lower():
        await message.channel.send('im made out of snake! 🐍')

    if 'riggbot' in message.content.lower():
        await message.channel.send('im riggbot! 🤖')

    return


async def on_reaction_add(reaction, user):
    try:
        # star recognition
        if reaction.message.author == client.user and reaction.emoji == '⭐' and reaction.count == 1:
            await reaction.message.channel.send('omg thank you so much')

        # ignore bot's own reactions and reactions to bot's message
        if user == client.user or reaction.message.author == client.user:
            return

        if not reaction.emoji == '🏳️‍⚧️':
            return

        if not reaction.count == 1:
            return

        msg = reaction.message
        collected = []
        if msg.embeds:
            emb_trans = translate_embeds(msg.embeds, is_manual=True)
            if emb_trans:
                collected.append(emb_trans)
        elif msg.content:
            detected = translator.detect(msg.content)
            if detected.lang == DEST_LANG:
                logging.info(f'Manual trigger: translating from {DEST_LANG} to {MANUAL_OVERRIDE_LANG}')
                translated = translator.translate(msg.content, dest=MANUAL_OVERRIDE_LANG)
                collected.append(translated.text)
            elif detected.lang != DEST_LANG:
                translated = translator.translate(msg.content, dest=DEST_LANG)
                translation = f"📝 {detected.lang}→{DEST_LANG}: {translated.text}"
                collected.append(translation)
        if collected:
            # reply to the message that was reacted to
            await msg.reply('\n'.join(collected), silent=True)
    except Exception as e:
        logging.exception(f'Error handling reaction trigger: {e}')


async def handle_reply(message):
    msg_content = message.content.lower()
    if 'trans' in msg_content:
        ref_msg = None
        # message.reference may contain resolved message or just ids
        if getattr(message.reference, 'resolved', None):
            ref_msg = message.reference.resolved
        elif getattr(message.reference, 'message_id', None):
            ref_msg = await message.channel.fetch_message(message.reference.message_id)

        if ref_msg:
            translations = []
            if ref_msg.embeds:
                emb_trans = translate_embeds(ref_msg.embeds, is_manual=True)
                if emb_trans:
                    translations.append(emb_trans)
            elif ref_msg.content:
                detected = translator.detect(ref_msg.content)
                if detected.lang == DEST_LANG:
                    logging.info(f'Manual trigger: translating from {DEST_LANG} to {MANUAL_OVERRIDE_LANG}')                        
                    translated = translator.translate(ref_msg.content, dest=MANUAL_OVERRIDE_LANG)
                    translations.append(translated.text)
                elif detected.lang != DEST_LANG:
                    translated = translator.translate(ref_msg.content, dest=DEST_LANG)
                    translation = f"📝 {detected.lang}→{DEST_LANG}: {translated.text}"
                    translations.append(translation)

            if translations:
                await ref_msg.reply('\n'.join(translations), silent=True)
            else:
                await ref_msg.reply('Sorry, I can\'t find anything to translate in that', silent=True)


# translates the description and images in the embed(s)
def translate_embeds(embeds, is_manual) -> str:
    description = embeds[0].to_dict().get("description")
    if description:
        description = description.split('\n\n')[0]
    # splits on '/n/n' due to fxtwitter's formatting convention (separates the view, likes, etc.)

    translation = None
    # Process description if found
    if description and not description.startswith("**[💬]"):
        # starting with '**[💬]' means there was no description (just the views, likes, etc.)
        logging.debug(f'Raw embed description: {description}')
        detected = translator.detect(description)
        if is_manual and detected.lang == DEST_LANG:
            logging.info(f'Manual trigger: translating description from {DEST_LANG} to {MANUAL_OVERRIDE_LANG}')
            translated = translator.translate(description, dest=MANUAL_OVERRIDE_LANG)
            translation = translated.text
            logging.info(f'Description translated from {detected.lang}')
        elif detected.lang != DEST_LANG:
            translated = translator.translate(description, dest=DEST_LANG)
            translation = f"📄 {detected.lang}→{DEST_LANG}: {translated.text}"
            logging.info(f'Description translated from {detected.lang}')

   
    if translation:
        return translation
    else:
        logging.debug('No translation to send')
        return


def run_bot():
    #Initialize and run the bot. For CI, call `init_bot()` and avoid calling `run_bot()`.
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
    MANUAL_OVERRIDE_LANG = os.getenv('MANUAL_OVERRIDE_LANG', 'zh-CN') or 'zh-CN'

    
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
