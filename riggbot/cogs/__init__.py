"""Bot features ("cogs"). Each module has a cog class and an `async def setup(bot)` function,
and is listed in EXTENSIONS in riggbot/bot.py so it's loaded at startup.

- admin      /ping, and owner-only /shutdown, /sync, /reload
- bots       /bots: approved bots per server
- fun        "is this true", LatiBot banter, ⭐ thanks, owner goodbye phrases
- langflags  /langflags: flag reaction -> language
- translate  translation on 🏳️‍⚧️/flag reactions and "trans" replies
- triggers   keyword triggers and /trigger
"""
