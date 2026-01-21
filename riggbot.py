import sys
import time
import re
import os
import logging
from pathlib import Path
import discord
import asyncio

from googletrans import Translator


def bot_token(token_file: str = 'riggbot token.txt') -> str:
    """Get bot token. Order of precedence:
    1. RIGGBOT_TOKEN environment variable
    2. token file (either raw token or 'token=VALUE')

    Raises ValueError/FileNotFoundError on missing/invalid token.
    """
    env = os.getenv('RIGGBOT_TOKEN')
    if env:
        logging.info('Loaded token from RIGGBOT_TOKEN env var')
        return env.strip()

    token_path = Path(token_file)
    if not token_path.exists():
        raise FileNotFoundError(
            "Token file not found. Please create 'riggbot token.txt' with your bot token.")

    content = token_path.read_text().strip()
    if not content:
        raise ValueError(
            "Token file is empty. Please add your bot token to 'riggbot token.txt'.")

    # Accept either 'token=VALUE' or raw token
    if '=' in content:
        key, val = content.split('=', 1)
        if key.strip().lower() == 'token' and val.strip():
            logging.info('Loaded token from token file (key=value)')
            return val.strip()
        else:
            raise ValueError("Token file format is incorrect. Use 'token=BOT_TOKEN' or raw token.")
    else:
        logging.info('Loaded token from token file (raw)')
        return content


# Globals that will be initialized by `init_bot()` or `run_bot()`.
TOKEN = None
client: discord.Client | None = None
translator: Translator | None = None
reader = None
reader_ru = None
reader_ja = None
reader_zh = None
specialized_readers = {}


def init_logging():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')


def init_bot(use_gpu: bool = False, langs: list | None = None):
    """Initialize global bot dependencies (discord client, translator, OCR readers).

    Call this from CI setup or before `run_bot()` to configure the runtime without starting the client.
    """
    global client, translator, reader, reader_ru, reader_ja, reader_zh, specialized_readers

    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    intents.messages = True

    client = discord.Client(intents=intents)

    # Initialize translator (googletrans) if available, else use a dummy async-compatible translator
    try:
        from googletrans import Translator as _TranslatorCls
    except Exception:
        _TranslatorCls = None

    if _TranslatorCls:
        translator = _TranslatorCls()
        logging.info('Translator initialized.')
    else:
        class _DummyTranslator:
            async def detect(self, text):
                return type('D', (), {'lang': 'en'})()

            async def translate(self, text, dest='en'):
                return type('R', (), {'text': text})()

        translator = _DummyTranslator()
        logging.info('Dummy translator initialized (googletrans not available)')

    # Initialize easyocr readers if easyocr is installed; otherwise use dummy readers
    try:
        import easyocr as _easyocr
    except Exception:
        _easyocr = None

    langs = langs or ['en', 'es', 'fr', 'de']
    if _easyocr:
        reader = _easyocr.Reader(langs, gpu=use_gpu)
        reader_ru = _easyocr.Reader(['ru', 'en'], gpu=use_gpu)
        reader_ja = _easyocr.Reader(['ja', 'en'], gpu=use_gpu)
        reader_zh = _easyocr.Reader(['ch_sim', 'en'], gpu=use_gpu)
        specialized_readers = {
            'ru': reader_ru,
            'ja': reader_ja,
            'zh-CN': reader_zh
        }
        logging.info('EasyOCR readers initialized')
    else:
        class _DummyReader:
            def readtext(self, *_args, **_kwargs):
                return []

        reader = reader_ru = reader_ja = reader_zh = _DummyReader()
        specialized_readers = {'ru': reader_ru, 'ja': reader_ja, 'zh-CN': reader_zh}
        logging.info('Dummy OCR readers initialized (easyocr not available)')
# total of 7 languages supported by easyocr
# English, Spanish, French, German, Russian, Japanese, Chinese (Simplified only)


@client.event
async def on_ready():
    logging.info(f'{client.user} is online')


@client.event
async def on_message(message):
    if message.author == client.user:  # ignore messages from the bot itself
        return

    if 'latibot' in message.author.name.lower():        
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
            translated_text = await translate_embeds(embeds, is_manual=False)
            if translated_text:
                logging.info('Sending translations')
            if translated_text:
                await message.reply(translated_text)

    # If this message is a reply and contains the trigger phrase, process the referenced message
    try:
        if message.reference and message.content:
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



@client.event
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
            emb_trans = await translate_embeds(msg.embeds, is_manual=True)
            if emb_trans:
                collected.append(emb_trans)

        if msg.attachments:
            urls = []
            for att in msg.attachments:
                name = getattr(att, 'filename', '') or ''
                if name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff')):
                    urls.append(att.url)
            if urls:
                img_trans = await translate_image_urls(urls, is_manual=True)
                if img_trans:
                    collected.extend(img_trans)

        if collected:
            # reply to the message that was reacted to
            await msg.reply('\n'.join(collected), silent=True)
    except Exception as e:
        logging.exception(f'Error handling reaction trigger: {e}')


async def handle_reply(message):
    msg_content = message.content.lower()
    if 'trans' in msg_content and 'riggbot' in msg_content:
        ref_msg = None
        # message.reference may contain resolved message or just ids
        if getattr(message.reference, 'resolved', None):
            ref_msg = message.reference.resolved
        elif getattr(message.reference, 'message_id', None):
            ref_msg = await message.channel.fetch_message(message.reference.message_id)

            if ref_msg:
                translated = []
            if ref_msg.embeds:
                emb_trans = await translate_embeds(ref_msg.embeds, is_manual=True)
                if emb_trans:
                    translated.append(emb_trans)
            if ref_msg.attachments:
                urls = []
                for attachment in ref_msg.attachments:
                    name = getattr(attachment, 'filename', '') or ''
                    if name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff')):
                        urls.append(attachment.url)
                if urls:
                    img_trans = await translate_image_urls(urls, is_manual=True)
                    if img_trans:
                        translated.extend(img_trans)

            if translated:
                await ref_msg.reply('\n'.join(translated), silent=True)
            else:
                await ref_msg.reply('Sorry, I can\'t find anything to translate in that', silent=True)

# handles translation of embed descriptions and images
async def translate_embeds(embeds, is_manual) -> str:
    description = embeds[0].to_dict().get("description", "")
    if description:
        description = description.split('\n\n')[0]
    # splits on '/n/n' due to fxtwitter's formatting convention (separates the view, likes, etc.)

    translations = []
    # Process description if found
    if description and not description.startswith("**[💬]"):
        # starting with '**[💬]' means there was no description (just the views, likes, etc.)
        logging.debug(f'Raw embed description: {description}')
        detected = await translator.detect(description)
        if is_manual and detected.lang == 'en':
            print('Manual trigger: translating description from English to Chinese')
            translated = await translator.translate(description, dest='zh-CN')
            translations.append(translated.text)
            logging.info(f'Description translated from {detected.lang}')
        elif detected.lang != 'en': 
            translated = await translator.translate(description, dest='en')
            translations.append(f"📄 {detected.lang}→en: {translated.text}")
            print(f'Description translated from {detected.lang}')

    # Processing any images in the embed
    if embeds:
        embed_data = embeds[0].to_dict()
        images = []
        # Collect all image URLs from embed
        if 'image' in embed_data and embed_data['image']:
            images.append(embed_data['image']['url'])
        # Process each image
        if images:
            img_trans = await translate_image_urls(images, is_manual)
            if img_trans:
                translations.extend(img_trans)

    # Send all translations in one message
    if translations:
        final_message = '\n'.join(translations)
        return final_message
    else:
        logging.debug('No translations to send')
        return


# run OCR readers on each image URL and return a list of translated strings (if any).
async def translate_image_urls(image_urls, is_manual) -> list:
    translations = []
    for imgx, image_url in enumerate(image_urls, 1):
        logging.debug(f'Processing image {imgx} from provided URLs')
        try:
            extracted_text = reader.readtext(image_url)
            formatted_text = format_ocr_text(
                "\n".join([item[1] for item in extracted_text]))
            detected = await translator.detect(formatted_text)
            if not formatted_text.strip() or (
                    detected.lang != 'en' and detected.lang != 'es' and detected.lang != 'fr' and detected.lang != 'de'):
                # if no text found or detected language is not in primary reader languages, try specialized readers
                for spec_reader in specialized_readers.values():
                    extracted_text = spec_reader.readtext(image_url)
                    formatted_text = format_ocr_text(
                        "\n".join([item[1] for item in extracted_text]))
                    detected = await translator.detect(formatted_text)
                    if formatted_text.strip() and detected.lang in specialized_readers.keys():
                        break

            if not formatted_text.strip():
                logging.debug(f'No text found in image {imgx}')
                continue

            # detect language once
            detected = await translator.detect(formatted_text)
            logging.debug(f'OCR extracted from image {imgx}: "{formatted_text}" (detected lang: {detected.lang})')

            if is_manual and detected.lang == 'en':
                logging.info(f'Manual trigger: translating image {imgx} text from English to Chinese')
                translated = await translator.translate(formatted_text, dest='zh-CN')
                translations.append(translated.text)
                logging.info(f'Img {imgx} translated text: {translated.text}')
            elif detected.lang != 'en':
                translated = await translator.translate(formatted_text, dest='en')
                translations.append(f"🖼️ Img {imgx} ({detected.lang}→en): {translated.text}\nOCR Detected: {formatted_text}")
                logging.info(f'Img {imgx} translated text: {translated.text}')
            else:
                logging.debug(f'Image {imgx} text is already English; skipping translation.')
        except Exception as e:
            logging.exception(f'Error processing image {imgx}: {e}')
    return translations


# formatting OCR output text (this is AI generated and needs to be reviewed more)
def format_ocr_text(text):
    # Split into lines, strip whitespace, remove empty lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Remove duplicate lines while preserving order
    seen = set()
    unique_lines = []
    for line in lines:
        if line not in seen:
            unique_lines.append(line)
            seen.add(line)
    # Join lines into a single string, separated by spaces
    formatted = ' '.join(unique_lines)
    return formatted


def run_bot(token: str | None = None, token_file: str = 'riggbot token.txt', use_gpu: bool = False):
    """Initialize and run the bot. For CI, call `init_bot()` and avoid calling `run_bot()`.

    If `token` is None, this looks for the `RIGGBOT_TOKEN` env var, then `token_file`.
    """
    global TOKEN
    init_logging()
    init_bot(use_gpu=use_gpu)
    TOKEN = token or bot_token(token_file)
    if not TOKEN:
        raise ValueError('No token provided to run the bot')

    logging.info('Starting Discord client...')
    client.run(TOKEN)


if __name__ == '__main__':
    # Run using env var or token file when executed directly.
    run_bot()
