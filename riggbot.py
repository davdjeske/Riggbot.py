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
import time
import asyncio
import discord
from pathlib import Path
from googletrans import Translator
import easyocr
import re


def bot_token() -> str:
    token_path = Path('riggbot token.txt')
    if not token_path.exists():
        raise FileNotFoundError(
            "Token file not found. Please create 'riggbot token.txt' with your bot token.")

    content = token_path.read_text().strip()
    if not content:
        raise ValueError(
            "Token file is empty. Please add your bot token to 'riggbot token.txt'.")

    # handle simple KEY=VALUE formats (e.g. "token=ABC")
    if "=" in content and not content.startswith("-----"):
        key, val = content.split("=", 1)
        if val.strip():
            print("Token loaded successfully.")
            return val.strip()
    print("Token loaded successfully.")

    return content


TOKEN = bot_token()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

translator = Translator()
print("Translator initialized.")
reader = easyocr.Reader(['en', 'es', 'fr', 'de',], gpu=False)
reader_cyrillic = easyocr.Reader(["ru"], gpu=False)
reader_ja = easyocr.Reader(['ja'], gpu=False)
reader_ch_sim = easyocr.Reader(['ch_sim'], gpu=False)
print("EasyOCR readers initialized")
# total of 7 languages supported by easyocr
# English, Spanish, French, German, Russian, Japanese, Chinese (Simplified only)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    print(f'Message from {message.author}: {message.content}')

    if 'latibot' in message.author.name.lower():
        description = None
        max_attempts = 5
        delay = 0.5  # seconds between attempts

        for attempt in range(max_attempts):
            if message.embeds:
                description = message.embeds[0].to_dict()["description"].split('\n\n')[0]
                print(f'Embed found on attempt {attempt + 1}: {description}')
                break

            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)

        translations = []
        
        # Process description if found
        if description and not description.startswith("**[💬]"):
            print(f'Embed description: {description}')
            detected = await translator.detect(description)
            if detected.lang != 'en':
                translated = await translator.translate(description, dest_language='en')
                translations.append(f"🌐 {detected.lang}→en: {translated.text}")
                print(f'Description translated from {detected.lang}')

        # Process all images in embed
        # if message.embeds:
        #     embed_data = message.embeds[0].to_dict()
        #     images = []
        #     # Collect all image URLs from embed
        #     if 'image' in embed_data and embed_data['image']:
        #         images.append(embed_data['image']['url'])
        #     if 'thumbnail' in embed_data and embed_data['thumbnail']:
        #         images.append(embed_data['thumbnail']['url'])
        #     # Process each image
        #     for idx, image_url in enumerate(images, 1):
        #         print(f'Processing image {idx}: {image_url}')
        #         try:
        #             # Try with general reader first
        #             extracted_text = reader.readtext(image_url)
        #             text = "\n".join([item[1] for item in extracted_text])
        #             # Try specialized readers if no text found
        #             if not text.strip():
        #                 for specialized_reader in [reader_ja, reader_cyrillic, reader_ch_sim]:
        #                     extracted_text_special = specialized_reader.readtext(image_url)
        #                     text_special = "\n".join([item[1] for item in extracted_text_special])
        #                     if text_special.strip():
        #                         text = text_special
        #                         break
        #             if text.strip():
        #                 formatted_text = format_ocr_text(text)
        #                 detected = await translator.detect(formatted_text)
        #                 print(f'OCR extracted from image {idx}: "{formatted_text}" (detected lang: {detected.lang})')
        #                 if detected.lang != 'en':
        #                     print(f'Image {idx} will be translated from {detected.lang} to en.')
        #                     translated = await translator.translate(formatted_text, dest_language='en')
        #                     translations.append(f"🖼️ Img {idx} ({detected.lang}→en): {translated.text}")
        #                     print(f'Img {idx} translated text: {translated.text}')
        #                 # else: do not append English results
        #             else:
        #                 print(f'No text found in image {idx}')
        #         except Exception as e:
        #             print(f'Error processing image {idx}: {e}')
        
        # Send all translations in one message
        if translations:
            final_message = '\n'.join(translations)
            print(f'Sending translations:\n{final_message}')
            await message.reply(final_message)
        else:
            print('No translations to send')
            return

    if 'beer' in message.content.lower():
        await message.channel.reply('mmmmm beer 🍺')
        
    if not message.author.name == 'riggoon':
        return

    if 'python' in message.content.lower():
        await message.channel.reply('im made out of snake! 🐍')

    return


client.run(TOKEN)
