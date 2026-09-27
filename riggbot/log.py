"""Logging setup.

Every record is one line:

    2026-09-27 07:32:00.000 [info] [translation] Translated ja→en via deepl (412 chars, 445 ms)

The component is the logger name without the leading "riggbot." so modules should simply use
`logging.getLogger(__name__)`. Console output is colored when the terminal supports it; the
log file gets the same format without colors.

Levels, from most to least detailed: debug, info, warning, error, critical. A handler set to
"info" shows info and everything above it, but hides debug.
"""
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Sequence

from .config import LoggingSettings

# Loggers from libraries, which are kept at `library_level` so they don't drown out the bot's own logs.
LIBRARY_LOGGERS = ('discord', 'httpx', 'httpcore', 'urllib3', 'deepl', 'hpack', 'asyncio')

# ANSI escape codes: invisible character sequences that tell a terminal to change text color.
_RESET = '\x1b[0m'
_GRAY = '\x1b[90m'
_MAGENTA = '\x1b[35m'
LEVEL_COLORS = {
    logging.DEBUG: '\x1b[36m',        # cyan
    logging.INFO: '\x1b[34m',         # blue
    logging.WARNING: '\x1b[33m',      # yellow
    logging.ERROR: '\x1b[31m',        # red
    logging.CRITICAL: '\x1b[1;31m',   # bold red
}


class RiggFormatter(logging.Formatter):
    """Turns a log record into riggbot's one-line format, optionally with colors."""

    def __init__(self, color: bool = False, timestamp_color: str = _GRAY):
        super().__init__()
        self.color = color
        # Discord's ansi code blocks don't know "bright" colors like 90, so the Discord log
        # channel passes its own gray here.
        self.timestamp_color = timestamp_color

    def format(self, record: logging.LogRecord) -> str:
        # e.g. "2026-09-27 07:32:00.123" (local time, with milliseconds)
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created)) + f'.{int(record.msecs):03d}'
        level = f'[{record.levelname.lower()}]'
        component = f'[{component_name(record.name)}]'
        # One record per line: escape newlines that sneak into messages (e.g. message text).
        message = record.getMessage().replace('\r', '\\r').replace('\n', '\\n')

        if self.color:
            level_color = LEVEL_COLORS.get(record.levelno, '')
            line = (f'{self.timestamp_color}{timestamp}{_RESET} {level_color}{level}{_RESET} '
                    f'{_MAGENTA}{component}{_RESET} {message}')
        else:
            line = f'{timestamp} {level} {component} {message}'

        # Errors logged with a stack trace get it on the following lines.
        if record.exc_info:
            line += '\n' + self.formatException(record.exc_info)
        if record.stack_info:
            line += '\n' + self.formatStack(record.stack_info)
        return line


def component_name(logger_name: str) -> str:
    """The [component] shown in a log line: 'riggbot.cogs.fun' -> 'cogs.fun'."""
    if logger_name == 'riggbot':
        return 'core'
    return logger_name.removeprefix('riggbot.')


def setup_logging(settings: LoggingSettings, base_dir: Path,
                  extra_handlers: Sequence[logging.Handler] = ()) -> None:
    """(Re)configure the root logger. Safe to call again, e.g. after /reload.

    `extra_handlers` are handlers created elsewhere that should also get log records, such as
    the Discord log channel (see log_channel.py). They're added as they are, not closed here.
    """
    root = logging.getLogger()
    # Remove the handlers a previous call added (they're marked with _riggbot), so calling this
    # again doesn't print every line twice.
    for handler in [h for h in root.handlers if getattr(h, '_riggbot', False)]:
        root.removeHandler(handler)
        if handler not in extra_handlers:
            handler.close()

    # Turn level names like "INFO" into logging's numeric levels.
    console_level = logging.getLevelName(settings.level)
    file_level = logging.getLevelName(settings.file_level)

    # Handler 1: the console / terminal.
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(RiggFormatter(color=_use_color(settings.color, console.stream)))
    console._riggbot = True
    handlers = [console]

    # Handler 2: the log file. It "rotates": when it reaches max_bytes it's renamed to
    # riggbot.log.1 (older ones to .2, .3, ...) and a fresh file is started.
    log_path = base_dir / settings.file
    file_error = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_path, maxBytes=settings.max_bytes,
                                           backupCount=settings.backup_count, encoding='utf-8')
        file_handler.setLevel(file_level)
        file_handler.setFormatter(RiggFormatter(color=False))
        file_handler._riggbot = True
        handlers.append(file_handler)
    except OSError as e:
        # e.g. no permission to write there. Keep running with console logging only.
        file_error = e

    # Any extra handlers (e.g. the Discord log channel).
    for handler in extra_handlers:
        handler._riggbot = True
        handlers.append(handler)

    for handler in handlers:
        root.addHandler(handler)
    # The root logger must let through everything that at least one handler wants to show.
    root.setLevel(min(h.level for h in handlers))

    # Quieten chatty libraries.
    library_level = logging.getLevelName(settings.library_level)
    for name in LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(library_level)

    # Reported last, so the warning goes through the handlers that were just set up.
    if file_error:
        logging.getLogger(__name__).warning('Could not open log file %s (%s); logging to console only',
                                            log_path, file_error)


def _use_color(mode: str, stream) -> bool:
    """Decide whether console output gets colors (config `logging.color`: auto/always/never)."""
    if mode == 'never':
        return False
    if mode == 'always':
        _enable_windows_ansi()
        return True
    # "auto": no colors if the user asked for none (NO_COLOR is a common convention)...
    if os.getenv('NO_COLOR'):
        return False
    # ...or if output isn't going to a real terminal (e.g. redirected into a file).
    if not (hasattr(stream, 'isatty') and stream.isatty()):
        return False
    return _enable_windows_ansi()


def _enable_windows_ansi() -> bool:
    """Turn on ANSI escape-code support in the Windows console. Returns whether colors will work."""
    if os.name != 'nt':
        return True     # Linux/macOS terminals support colors already
    try:
        # Ask Windows (through its C API) to interpret color codes in the console.
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-12)   # STD_ERROR_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False
