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

# Regular expressions (patterns that match text). re.MULTILINE makes ^ and $ match at the start
# and end of every line, not just the start and end of the whole text.

# A line made only of bold [emoji](link) counters, e.g. **[💬](url) 12 [🔁](url) 3**
# It has to START with **[ and consist only of links and numbers, so ordinary **bold** words
# inside a post don't match (that was a bug in the old version).
_STATS_LINE = re.compile(r'^\*\*(?:\s*\[[^\]\n]+\]\([^)\n]+\)[^\S\n]*[\w.,]*)+\s*\*\*[^\S\n]*$', re.MULTILINE)
# The first line of a quoted post: > **[Quoting](url) Name**
_QUOTE_HEADER = re.compile(r'^> *\*\*\[[^\n]*$', re.MULTILINE)
# The "> " at the start of each line inside a quote
_QUOTE_PREFIX = re.compile(r'^> ?', re.MULTILINE)


def split_description(description: str) -> tuple[str, str]:
    """Split an embed description into (main post text, quoted post text)."""
    match = _QUOTE_HEADER.search(description)
    if match:
        # Everything before the quote header is the main post...
        main = description[:match.start()]
        # ...and everything after it is the quoted post, minus the "> " line prefixes.
        quoted = _QUOTE_PREFIX.sub('', description[match.end():])
    else:
        # No quote: the whole description is the main post.
        main, quoted = description, ''
    return _clean(main), _clean(quoted)


def _clean(text: str) -> str:
    """Remove stats lines and surrounding blank space."""
    return _STATS_LINE.sub('', text).strip()
