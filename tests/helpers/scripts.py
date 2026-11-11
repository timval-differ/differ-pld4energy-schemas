"""Checks of the page's scripts as text."""

import re

# A call of a dialog the sandboxed frame NOMAD shows the page in ignores:
# print(), confirm(...), alert(...), prompt(...), bare or on the window.
_BLOCKED = re.compile(
    r'(?<![\w$.])(?:(?:window|globalThis|self|top|parent)\.)?'
    r'(?<!function )(?:print|confirm|alert|prompt)\s*\('
)
_BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
_LINE_COMMENT = re.compile(r'(^|\s)//.*$', re.MULTILINE)


def blocked_dialog_calls(script: str) -> list[str]:
    """
    The calls of blocked dialogs in `script`, comments left out. A heuristic on
    the text, not a parser: '//' or '/*' inside a string would hide the code
    after it, and window['print']() is not found. The page's scripts have none.
    """
    code = _LINE_COMMENT.sub(r'\1', _BLOCK_COMMENT.sub('', script))
    return [match.group(0) for match in _BLOCKED.finditer(code)]
