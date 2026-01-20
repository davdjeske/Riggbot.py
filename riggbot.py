import sys
import time
import re
import easyocr
from googletrans import Translator
from pathlib import Path
import discord
import asyncio


def bot_token() -> str:  # getting bot token
    token_path = Path('riggbot token.txt')
    if not token_path.exists():
        raise FileNotFoundError(
            "Token file not found. Please create 'riggbot token.txt' with your bot token.")

    content = token_path.read_text().strip()
    if not content:
        raise ValueError(
            "Token file is empty. Please add your bot token to 'riggbot token.txt'.")

    # handles key=value format
    key, val = content.split("=", 1)
    if key == 'token' and val.strip():
        print("Token loaded successfully.")
        return val.strip()
    else:
        raise ValueError(
            "Token file format is incorrect. Please use 'token=BOT_TOKEN' format.")


TOKEN = bot_token()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

translator = Translator()
print("Translator initialized.")
reader = easyocr.Reader(['en', 'es', 'fr', 'de',], gpu=False)
reader_ru = easyocr.Reader(['ru', 'en'], gpu=False)
reader_ja = easyocr.Reader(['ja', 'en'], gpu=False)
reader_zh = easyocr.Reader(['ch_sim', 'en'], gpu=False)
specialized_readers = {
    'ru': reader_ru,
    'ja': reader_ja,
    'zh-CN': reader_zh
}
print("EasyOCR readers initialized")
# total of 7 languages supported by easyocr
# English, Spanish, French, German, Russian, Japanese, Chinese (Simplified only)


@client.event
async def on_ready():
    print(f'{client.user} is online')


@client.event
async def on_message(message):
    if message.author == client.user:  # ignore messages from the bot itself
        return

    if 'latibot' in message.author.name.lower():
        print("Searching for embeds...")
        # multiple attempts to make sure it gets the embed
        embeds = None
        max_attempts = 5
        delay = 0.5  # seconds between attempts
        for attempt in range(max_attempts):
            if message.embeds:
                embeds = message.embeds
                print(f'Embed found on attempt {attempt + 1}')
                break
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)

        if embeds:
            translated_text = await translate_embeds(embeds)
            print(f'Sending translations:\n{translated_text}')
            if translated_text:
                await message.reply(translated_text)

    # Process any image attachments on the message
    if message.attachments and 'riggoon' in message.author.name.lower():
        image_urls = []
        for att in message.attachments:
            name = getattr(att, 'filename', '') or ''
            if name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff')):
                image_urls.append(att.url)
        if image_urls:
            try:
                attached_translations = await translate_image_urls(image_urls)
                if attached_translations:
                    await message.reply('\n'.join(attached_translations))
            except Exception as e:
                print(f'Error processing attachments: {e}')

    # triggered word responses
    if 'beer' in message.content.lower():
        await message.channel.send('mmmmm beer 🍺')

    if 'weed' in message.content.lower():
        await message.channel.send('mmmmm weed 🍃')

    if 'awaga' in message.content.lower():
        await message.channel.send('waga baba bobo')

    if 'one piece' in message.content.lower():
        await message.channel.send('THE ONE PIECE IS REAL! 🏴‍☠️')

    if 'david bot' in message.content.lower() or 'davidbot' in message.content.lower():
        await message.channel.send('thats not my name bitch')

    if not message.author.name == 'riggoon':
        return

    if 'say goodbye riggbot' in message.content.lower():
        await message.channel.send('Goodbye! 👋')
        sys.exit()

    if 'python' in message.content.lower():
        await message.channel.send('im made out of snake! 🐍')

    if 'riggbot' in message.content.lower():
        await message.channel.send('im riggbot! 🤖')

    return


# handles translation of embed descriptions and images
async def translate_embeds(embeds) -> str:
    description = embeds[0].to_dict()["description"].split('\n\n')[0]
    # splits on '/n/n' due to fxtwitter's formatting convention (separates the view, likes, etc.)

    translations = []
    # Process description if found
    if description and not description.startswith("**[💬]"):
        # starting with '**[💬]' means there was no description (just the views, likes, etc.)
        print(f'Raw embed description: {description}')
        detected = await translator.detect(description)
        if detected.lang != 'en':
            translated = await translator.translate(description, dest_language='en')
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
            img_trans = await translate_image_urls(images)
            if img_trans:
                translations.extend(img_trans)

    # Send all translations in one message
    if translations:
        final_message = '\n'.join(translations)
        return final_message
    else:
        print('No translations to send')
        return


# run OCR readers on each image URL and return a list of translateds strings (if any).
async def translate_image_urls(image_urls) -> list:
    results = []
    for imgx, image_url in enumerate(image_urls, 1):
        print(f'Processing image {imgx} from provided URLs')
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

            if formatted_text.strip():
                detected = await translator.detect(formatted_text)
                print(
                    f'OCR extracted from image {imgx}: "{formatted_text}" (detected lang: {detected.lang})')

                if detected.lang != 'en':  # double checking for English
                    translated = await translator.translate(formatted_text, dest_language='en')
                    results.append(
                        f"🖼️ Img {imgx} ({detected.lang}→en): {translated.text}")
                    print(f'Img {imgx} translated text: {translated.text}')
            else:
                print(f'No text found in image {imgx}')
        except Exception as e:
            print(f'Error processing image {imgx}: {e}')
    return results


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


client.run(TOKEN)
