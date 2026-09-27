"""Pull the translatable text out of a link-embed description (fxtwitter-style).

A description looks like:

    post text, possibly with **bold** words

    **[💬](https://…) 12  [🔁](https://…) 3  [❤️](https://…) 45**     <- stats line

    > **[Quoting](https://…) Someone (@someone)**                       <- quote header
    >
    > quoted post text

split_description() returns (post text, quoted post text), either of which may be empty.
"""
import re

# A line made only of bold [emoji](link) counters, e.g. **[💬](url) 12 [🔁](url) 3**
_STATS_LINE = re.compile(r'^\*\*(?:\s*\[[^\]\n]+\]\([^)\n]+\)[^\S\n]*[\w.,]*)+\s*\*\*[^\S\n]*$', re.MULTILINE)
# The first line of a quoted post: > **[Quoting](url) Name**
_QUOTE_HEADER = re.compile(r'^> *\*\*\[[^\n]*$', re.MULTILINE)
_QUOTE_PREFIX = re.compile(r'^> ?', re.MULTILINE)


def split_description(description: str) -> tuple[str, str]:
    match = _QUOTE_HEADER.search(description)
    if match:
        main = description[:match.start()]
        quoted = _QUOTE_PREFIX.sub('', description[match.end():])
    else:
        main, quoted = description, ''
    return _clean(main), _clean(quoted)


def _clean(text: str) -> str:
    return _STATS_LINE.sub('', text).strip()
