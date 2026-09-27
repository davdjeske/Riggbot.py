"""Logging setup.

Every record is one line:

    2026-09-27 07:32:00.000 [info] [translation] Translated ja→en via deepl (412 chars, 445 ms)

The component is the logger name without the leading "riggbot." so modules should simply use
`logging.getLogger(__name__)`. Console output is colored when the terminal supports it; the
log file gets the same format without colors.
"""
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LoggingSettings

# Loggers from libraries, which are kept at `library_level` so they don't drown out the bot's own logs.
LIBRARY_LOGGERS = ('discord', 'httpx', 'httpcore', 'urllib3', 'deepl', 'hpack', 'asyncio')

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
    def __init__(self, color: bool = False):
        super().__init__()
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created)) + f'.{int(record.msecs):03d}'
        level = f'[{record.levelname.lower()}]'
        component = f'[{component_name(record.name)}]'
        # One record per line: escape newlines that sneak into messages (e.g. message text).
        message = record.getMessage().replace('\r', '\\r').replace('\n', '\\n')

        if self.color:
            level_color = LEVEL_COLORS.get(record.levelno, '')
            line = (f'{_GRAY}{timestamp}{_RESET} {level_color}{level}{_RESET} '
                    f'{_MAGENTA}{component}{_RESET} {message}')
        else:
            line = f'{timestamp} {level} {component} {message}'

        if record.exc_info:
            line += '\n' + self.formatException(record.exc_info)
        if record.stack_info:
            line += '\n' + self.formatStack(record.stack_info)
        return line


def component_name(logger_name: str) -> str:
    if logger_name == 'riggbot':
        return 'core'
    return logger_name.removeprefix('riggbot.')


def setup_logging(settings: LoggingSettings, base_dir: Path) -> None:
    """(Re)configure the root logger. Safe to call again, e.g. after /reload."""
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, '_riggbot', False)]:
        root.removeHandler(handler)
        handler.close()

    console_level = logging.getLevelName(settings.level)
    file_level = logging.getLevelName(settings.file_level)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(RiggFormatter(color=_use_color(settings.color, console.stream)))
    console._riggbot = True
    handlers = [console]

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
        file_error = e

    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(min(h.level for h in handlers))

    library_level = logging.getLevelName(settings.library_level)
    for name in LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(library_level)

    if file_error:
        logging.getLogger(__name__).warning('Could not open log file %s (%s); logging to console only',
                                            log_path, file_error)


def _use_color(mode: str, stream) -> bool:
    if mode == 'never':
        return False
    if mode == 'always':
        _enable_windows_ansi()
        return True
    if os.getenv('NO_COLOR'):
        return False
    if not (hasattr(stream, 'isatty') and stream.isatty()):
        return False
    return _enable_windows_ansi()


def _enable_windows_ansi() -> bool:
    """Turn on ANSI escape-code support in the Windows console. Returns whether colors will work."""
    if os.name != 'nt':
        return True
    try:
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
