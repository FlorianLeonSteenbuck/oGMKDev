"""Python tokens for the highlighting, from the standard library's tokenize module.

The kinds are ``keyword``, ``identifier``, ``string`` (also the parts of an f-string), ``comment``,
``number`` and ``operator``; whitespace and the layout tokens are left out. Where the text is not
complete Python (an unterminated string, an unclosed bracket), the tokens read up to that point are
returned, so that an editor can colour a file while it is being written.
"""

from __future__ import annotations

import io
import keyword
import tokenize as _tokenize
from dataclasses import dataclass
from typing import Dict, List

_KINDS: Dict[int, str] = {
    _tokenize.STRING: "string",
    _tokenize.COMMENT: "comment",
    _tokenize.NUMBER: "number",
    _tokenize.OP: "operator",
}
for _name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):  # Python 3.12 and later
    if hasattr(_tokenize, _name):
        _KINDS[getattr(_tokenize, _name)] = "string"


@dataclass(frozen=True)
class Token:
    kind: str
    start: int
    end: int


def tokenize(source: str) -> List[Token]:
    """The coloured tokens of ``source``, in order, with character offsets."""
    line_starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            line_starts.append(index + 1)

    def offset(row: int, column: int) -> int:
        if row - 1 >= len(line_starts):
            return len(source)
        return line_starts[row - 1] + column

    tokens: List[Token] = []
    try:
        for item in _tokenize.generate_tokens(io.StringIO(source).readline):
            if item.type == _tokenize.NAME:
                kind = "keyword" if keyword.iskeyword(item.string) else "identifier"
            else:
                kind = _KINDS.get(item.type)
            if kind is not None:
                tokens.append(Token(kind, offset(*item.start), offset(*item.end)))
    except (_tokenize.TokenError, SyntaxError):
        pass  # the text is not complete: the tokens read so far are the result
    return tokens
