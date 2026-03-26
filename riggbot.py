import asyncio
import random
import discord
import logging
import os
import re
from dotenv import load_dotenv
from googletrans import Translator

# Load .env variables
load_dotenv()

# Global vars that are initialized by `init_bot()` or `run_bot()`.
TOKEN = None
EMBED_BOT_NAME = None
DEST_LANG = None
MANUAL_OVERRIDE_LANG = None
client: discord.Client | None = None
translator = None

# Keyword triggers dictionary
KEYWORD_RESPONSES = {
    'beer': 'mmmmm beer \U0001F37A',
    'weed': 'mmmmm weed \U0001F343',
    'awaga': 'waga baba bobo',
    'one piece': 'THE ONE PIECE IS REAL! \U0001F3F4\u200d\u2620\uFE0F',
    'it just works': 'my old uncle ToddBot used to say that all the time...',
    'skyrim': 'my old uncle ToddBot used to release that game all the time...',

}

# region: Bot Initialization and Setup


def init_logging():
    # TODO: learn more about this logging library and improve the logging implementation
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def init_bot():
    """Initialize global bot dependencies and configure the runtime without starting the client for better
        error handling and logging during the init phase, especially for CI and testing purposes.
    """
    # totally unrelated but TODO: implement testing :clueless:

    global client, translator, TOKEN, EMBED_BOT_NAME, DEST_LANG, MANUAL_OVERRIDE_LANG

    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    intents.messages = True
    logging.debug(f'Using intents: {intents}')

    # Initialize Discord client and register event handlers
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

    # Initialize translator (googletrans)
    translator = Translator()
    logging.info('Translator initialized.')

    # Load env vars
    TOKEN = bot_token()

    EMBED_BOT_NAME = (os.getenv('EMBED_BOT_NAME', '') or '').strip().lower()
    if EMBED_BOT_NAME:
        logging.info(
            f'Loaded embed bot name filter from .env: "{EMBED_BOT_NAME}"')
    else:
        logging.warning(
            'No embed bot name filter set in .env, defaulting to "" (disabled)')
    logging.info(
        f'Embed bot name filter: "{EMBED_BOT_NAME if EMBED_BOT_NAME else "(disabled)"}"')

    DEST_LANG = os.getenv('DEST_LANG', 'en') or 'en'
    logging.info(f'Default destination language: {DEST_LANG}')

    MANUAL_OVERRIDE_LANG = os.getenv(
        'MANUAL_OVERRIDE_LANG', 'zh-CN') or 'zh-CN'
    logging.info(f'Manual override language: {MANUAL_OVERRIDE_LANG}')


def bot_token() -> str:  # Load bot token from .env file
    raw = os.getenv('RIGGBOT_TOKEN')
    token = str(raw).strip() if raw is not None else None
    if token:
        logging.info('Loaded token from .env')
        return token

    # Not found or empty
    raise FileNotFoundError(
        "No RIGGBOT_TOKEN found in .env.\n"
        "Create a .env file in the project root with the line:\n"
        "RIGGBOT_TOKEN=your_bot_token_here\n"
        "Only .env format is supported for token ingestion.")


def run_bot():
    # Initialize and run the bot. For CI, call `init_bot()` and avoid calling `run_bot()`.
    init_logging()
    init_bot()
    logging.info('Starting Discord client...')
    client.run(TOKEN)

# endregion


# region: Discord Event Handlers and Reply Handler
async def on_ready():
    logging.info(f'{client.user} is online')


async def on_message(message):
    if message.author == client.user:  # ignore messages from the bot itself
        return

    if message.webhook_id is not None:  # ignore webhook messages
        return

    # TODO: further refine filtering and avoid processing non-relevant messages

    #TODO: latibot non embed message filter
    if EMBED_BOT_NAME in message.author.name.lower():
        logging.info(
            f'Message from embed bot "{message.author.name}" detected')
        await process_message(message, is_manual=False)

    # If this message is a reply, handle it separately
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

    # i dont care that this is hardcoded i know its bad practice
    if message.author.name != 'riggoon':
        return

    if 'say goodbye riggbot' in message.content.lower():
        await message.channel.send('Goodbye! \U0001F44B', silent=True)
        await client.close()

    if 'riggbot' in content_lower:
        await message.channel.send('I\'m riggbot! \U0001F916', silent=True)


async def on_reaction_add(reaction, user):
    ''' TODO: refine this detection to avoid repeated triggers
        for example, if the user reacts and then unreacts and then reacts again, 
        im pretty sure it will trigger twice since its checking for count == 1.
        Need to figure out a good way to fix this, preferably without too much complexity
        Maybe just a cooldown?         
    '''
    # star recognition (before other checks since it need to be a reaction on bot's messages)
    if reaction.message.author == client.user and reaction.emoji == '\u2B50' and reaction.count == 1:
        await reaction.message.channel.send('omg thank you so much')

    # ignore bot's own reactions and reactions to bot's message
    if user == client.user or reaction.message.author == client.user:
        return

    if reaction.emoji == '\U0001F3F3\uFE0F\u200D\u26A7\uFE0F' and reaction.count == 1:
        logging.info('Translation trigger detected by reaction')
        msg = reaction.message
        await process_message(msg, is_manual=True)
        logging.info('Handled manual translation trigger from reaction')


async def handle_reply(message):
    msg_content = message.content.lower()
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
        if ref_msg.author != client.user:
            await process_message(ref_msg, is_manual=True)
            logging.info('Handled manual translation trigger from reply')

    # experimental (a.k.a. i havent actually tested this much at all)
    if 'riggbot is this true' in msg_content or '<@1293252648803237899> is this true' in msg_content:
        logging.info('Analyzing if true')
        if ref_msg.author != client.user:
            await message.reply(random.choice(['Yes', 'No']), silent=True)
            # TODO: add more replies here
            logging.info('Delivered the truth')

# endregion


# region: Message Processing and Translation Logic
async def process_message(message, is_manual: bool):
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
        emb_trans = await process_embed(embeds[0], is_manual)
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


async def process_embed(embed, is_manual: bool) -> str | None:
    description = embed.to_dict().get("description")
    logging.info(f'Raw embed description: {description}')
    if description:
        # regex split to get text around 'quoted' separator and post's metadata (views, likes, etc.)
        text_blobs = re.split(r"\s*\*\*\[.*\*\*\s*", description)
        # TODO: add handling for 'attached' tweets (these are rare, and i need a better example with text
        # to test with, but basically need to handle a slightly different format but its similar to quoted tweets)
        
        # remove empty blobs that may occur due to regex split
        for i, blob in enumerate(text_blobs):
            if blob.strip() == '':
                text_blobs = text_blobs[:i:]

        if len(text_blobs) == 0:
            logging.info('Text blobs empty, skipping translation')
            return None

        """ There should only be at most 2 blobs (main and quoted), if there is a case
            where there are more than 2 that is NOT an error, this should be changed to 
            a loop but until then I think this is easier to read and understand. So, for 
            now, any extra blobs that may occur will be logged and ignored.
        """

        logging.info(f'Raw Description Text Blobs: {text_blobs}')
        translation = ''

        temp_translation = await translate_text(text_blobs[0], is_manual)
        if temp_translation:
            translation = "\U0001F4C4 " + temp_translation
            logging.info('Main description text translated')

        if len(text_blobs) > 1:
            temp_translation = await translate_text(text_blobs[1], is_manual)
            if temp_translation:
                translation += "\n\n\U0001F4AC " + temp_translation
                logging.info('Quoted text found and translated')

        if len(text_blobs) > 2:  # aforementioned handling of unexpected extra blobs
            logging.error(f'Unexpected Text Blob(s): {text_blobs[2:]}')

        if translation.strip():
            return translation
        else:
            return None


async def translate_text(text: str, is_manual: bool) -> str | None:
    """Core translation function that detects the language of the input text and 
        translates it to the destination language if needed.

    Args:
        text: The text content to translate
        is_manual: Whether this is a manual translation trigger

    Returns:
        Translated string or None if no translation needed
    """

    try:
        logging.info(f'Translating text (manual={is_manual}): {text}')
        translation = None

        # Extract markdown links before translation to preserve them TODO: maybe come up with a more robust placeholder
        md_links = re.findall(r'\[.*?\]\(.*?\)', text)
        for i, link in enumerate(md_links):
            text = text.replace(link, f'{{LINK_{i}}}', 1)

        detected = await asyncio.to_thread(translator.detect, text)

        if detected.lang != DEST_LANG:
            # need to translate
            logging.info(
                f'Translating from {detected.lang} to {DEST_LANG}')
            translated = await asyncio.to_thread(translator.translate, text, dest=DEST_LANG)
            translation = f"{detected.lang}→{DEST_LANG}: {translated.text}"

        elif is_manual:
            # if manual and already in dest lang, translate to override lang
            logging.info(
                f'Override: translating from {DEST_LANG} to {MANUAL_OVERRIDE_LANG}')
            translated = await asyncio.to_thread(translator.translate, text, dest=MANUAL_OVERRIDE_LANG)
            translation = translated.text

        # Restore extracted markdown links
        if translation:
            for i, link in enumerate(md_links):
                translation = translation.replace(f'{{LINK_{i}}}', link)
            # googletrans sometimes uses backticks; swap them out since they break discord markdown formatting
            # hopefully this doesn't cause any issues with legitimate backticks :clueless:
            translation = translation.replace('`', '\'')

        logging.info(f'Translation result: {translation}')
        return translation
    except Exception as e:
        logging.error(f'Translation error: {e}')
    return None

# endregion

if __name__ == '__main__':
    run_bot()
