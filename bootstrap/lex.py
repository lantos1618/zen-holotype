"""bootstrap/lex.py — the scanner, which exists to produce diagnostics.

tree-sitter parses; it does not diagnose. An `ERROR` node carries no message,
often no useful span, and nothing at all about *why* — so every lexical bug
class in `docs/TESTING.md` (EOF inside a string, an unknown escape, a stray
byte, a `'` with nothing after it) reaches the user as "syntax error near
`~~`" or as silence. This scanner runs first, over the same bytes, and says
what is wrong and where.

**It is not the parser's token source.** `bootstrap/cst.py` still walks the
tree-sitter tree; this file only rejects. The two therefore have to agree
about what a token is, and where they differ this one is deliberately the
STRICTER: `grammar.js` lets a string literal span lines (`/[^"\\]+/` matches a
newline) and lets `007` through, and both are rejected here. Stricter is safe
— the file is rejected before it is walked. Looser would be a hole.

Positions are byte offsets; `cst.py` turns them into 1-based line / 1-based
BYTE column `Span`s. A diagnostic is

    (start, end, message, notes)      notes: ((start, end, text), ...)

collected and returned, never raised: one bad file must not stop the run.

DECISIONS DESIGN.md DOES NOT STATE. Each one is settled here because a
scanner cannot abstain, and each needs a sentence in `DESIGN.md`:

  L1. The escape set is `\\n \\t \\r \\0 \\\\ \\' \\"` and nothing else. TESTING.md
      names `\\'` and `\\\\`; the corpus uses `\\t \\n \\\\ \\"`. An unknown escape is
      an error, never a silent literal character — `"\\q"` must not mean `q`.
  L2. Identifiers are ASCII, matching `grammar.js`'s
      `/[A-Za-z_][A-Za-z0-9_]*/`. Widening a charset later is compatible;
      narrowing it is not.
  L3. Block comments do not nest (grammar.js D9). `/* a /* b */` is closed.
  L4. A leading zero is rejected. Zen has no octal, so `010` cannot silently
      mean 8, and Python 3 made this exact call for this exact reason.
  L5. A string literal and a character literal do not span lines. The newline
      is the error, and the diagnostic points at the OPENING quote — pointing
      at EOF names no useful location.
  L6. A character literal holds exactly one byte (`str` is bytes). `''` and
      `'ab'` are both errors.
  L7. A BOM is stripped only at offset 0. Anywhere else it is an ordinary,
      invalid byte sequence.
  L8. A digit may not be followed by an identifier character: `1abc` and
      `0xFF` are errors, not a number beside a name. There are no type
      suffixes and no hex.
  L9. `12.` is an error: a float has digits on both sides of the point. So a
      number literal is never the base of a member access.
  L10. The `@` namespace is exactly `@Self`, `@meta`, `@scope` (DESIGN.md's
      "adding a fourth is a design change"), so `@foo` is rejected here rather
      than becoming an unresolved name later.
"""

from __future__ import annotations

# --- bytes, spelled once ---------------------------------------------------

BOM = b"\xef\xbb\xbf"

TAB, LF, CR, SPACE = 0x09, 0x0A, 0x0D, 0x20
QUOTE, APOS, BACKSLASH = 0x22, 0x27, 0x5C
SLASH, STAR, DOT, AT, ZERO = 0x2F, 0x2A, 0x2E, 0x40, 0x30

WHITESPACE = frozenset((TAB, LF, CR, SPACE, 0x0B, 0x0C))

# L1
ESCAPES = frozenset(b"ntr0\\'\"")

# L10
AT_NAMES = ("Self", "meta", "scope")

# every punctuation byte `grammar.js` spells as a token. `_` is an identifier
# character, and `@` `"` `'` are handled before this set is consulted.
PUNCTUATION = frozenset(b"!%&()*+,-./:;<=>[]{|}")

OPENERS = {0x28: "(", 0x5B: "[", 0x7B: "{"}
CLOSERS = {0x29: "(", 0x5D: "[", 0x7D: "{"}
MATCHING = {"(": ")", "[": "]", "{": "}"}

U64_MAX = (1 << 64) - 1


def _is_digit(b: int) -> bool:
    return 0x30 <= b <= 0x39


def _is_ident_start(b: int) -> bool:
    return b == 0x5F or 0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A


def _is_ident(b: int) -> bool:
    return _is_ident_start(b) or _is_digit(b)


def _show(source: bytes, start: int, end: int) -> str:
    """The offending bytes, printable. A control byte has no glyph, so it is
    named rather than emitted into the diagnostic stream."""
    raw = source[start:end]
    text = raw.decode("utf-8", "replace")
    if len(raw) == 1 and (raw[0] < 0x20 or raw[0] == 0x7F):
        return "U+%04X" % raw[0]
    return "`%s`" % text


# ===========================================================================
# the scanner
# ===========================================================================


class _Scanner:
    def __init__(self, source: bytes):
        self.src = source
        self.n = len(source)
        self.i = 0
        self.tokens: list = []
        self.diags: list = []
        self.opens: list = []  # (byte offset, opener char) still unclosed
        self.brackets_lost = False  # a mismatch was reported; stop tracking

    # -- reporting --

    def err(self, start: int, end: int, message: str, notes=()) -> None:
        self.diags.append((start, end, message, tuple(notes)))

    def token(self, kind: str, start: int, end: int) -> None:
        self.tokens.append((kind, start, end))

    # -- driver --

    def run(self):
        src, n = self.src, self.n
        if src.startswith(BOM):  # L7
            self.i = len(BOM)
        while self.i < n:
            b = src[self.i]
            if b in WHITESPACE:
                self.i += 1
            elif b == SLASH and self.i + 1 < n and src[self.i + 1] == SLASH:
                self.line_comment()
            elif b == SLASH and self.i + 1 < n and src[self.i + 1] == STAR:
                self.block_comment()
            elif b == QUOTE:
                self.string()
            elif b == APOS:
                self.char()
            elif _is_digit(b):
                self.number()
            elif _is_ident_start(b):
                self.identifier()
            elif b == AT:
                self.at_name()
            elif b in OPENERS or b in CLOSERS:
                self.bracket()
            elif b in PUNCTUATION:
                self.token("punct", self.i, self.i + 1)
                self.i += 1
            else:
                self.stray()
        self.unclosed_at_eof()
        return self.tokens, self.diags

    # -- comments (L3) --

    def line_comment(self) -> None:
        end = self.src.find(b"\n", self.i)
        self.i = self.n if end < 0 else end

    def block_comment(self) -> None:
        start = self.i
        end = self.src.find(b"*/", start + 2)
        if end < 0:
            self.err(
                start,
                self.n,
                "unterminated block comment: reached end of file before `*/`",
            )
            self.i = self.n
            return
        self.i = end + 2

    # -- string (L1, L5) --

    def string(self) -> None:
        start = self.i
        i = self.i + 1
        src, n = self.src, self.n
        while True:
            if i >= n:
                self.err(start, n, "unterminated string literal: reached end of file")
                self.i = n
                return
            b = src[i]
            if b == LF:
                self.err(
                    start,
                    i,
                    "unterminated string literal: a string literal does not span lines",
                )
                self.i = i
                return
            if b == BACKSLASH:
                i = self.escape(i)
                if i >= n:
                    self.i = n
                    return
                continue
            if b == QUOTE:
                self.token("string", start, i + 1)
                self.i = i + 1
                return
            i += 1

    # -- character (L1, L5, L6) --

    def char(self) -> None:
        start = self.i
        src, n = self.src, self.n
        i = start + 1
        if i >= n:
            self.err(start, n, "unterminated character literal: reached end of file")
            self.i = n
            return
        if src[i] == APOS:  # L6
            self.err(
                start,
                i + 1,
                "empty character literal: a character literal holds exactly one byte",
            )
            self.i = i + 1
            return
        if src[i] == LF:
            self.unterminated_char(start, i)
            return
        if src[i] == BACKSLASH:
            i = self.escape(i)
            if i >= n:
                self.i = n
                return
        else:
            i += 1
        if i < n and src[i] == APOS:
            self.token("char", start, i + 1)
            self.i = i + 1
            return
        # it did not close where a one-byte literal must. Say which of the two
        # reasons it is, rather than "syntax error".
        j = i
        while j < n and src[j] not in (APOS, LF):
            j += 1
        if j < n and src[j] == APOS:  # L6
            self.err(
                start,
                j + 1,
                "a character literal holds exactly one byte; this one holds more",
            )
            self.i = j + 1
            return
        self.unterminated_char(start, j)

    def unterminated_char(self, start: int, at: int) -> None:
        if at >= self.n:
            self.err(start, at, "unterminated character literal: reached end of file")
        else:
            self.err(
                start,
                at,
                "unterminated character literal: a character literal does not "
                "span lines",
            )
        self.i = at

    def escape(self, i: int) -> int:
        """`i` is at the backslash. -> the offset just past the escape."""
        if i + 1 >= self.n:
            self.err(i, self.n, "unterminated escape sequence: reached end of file")
            return self.n
        b = self.src[i + 1]
        if b not in ESCAPES:  # L1
            self.err(
                i,
                i + 2,
                "unknown escape sequence %s: the escapes are "
                "\\n \\t \\r \\0 \\\\ \\' \\\"" % _show(self.src, i, i + 2),
            )
        return i + 2

    # -- numbers (L4, L8, L9) --

    def number(self) -> None:
        src, n = self.src, self.n
        start = self.i
        i = start
        while i < n and _is_digit(src[i]):
            i += 1
        whole = src[start:i]
        if len(whole) > 1 and whole[0] == ZERO:  # L4
            self.err(
                start,
                i,
                "leading zero in `%s`: a decimal literal has no leading zero, "
                "and Zen has no octal" % whole.decode("ascii"),
            )
        is_float = False
        if i < n and src[i] == DOT:
            if i + 1 < n and _is_digit(src[i + 1]):
                is_float = True
                i += 2
                while i < n and _is_digit(src[i]):
                    i += 1
            else:  # L9
                self.err(i, i + 1, "a float literal needs a digit after the `.`")
                i += 1
        if i < n and _is_ident_start(src[i]):  # L8
            j = i
            while j < n and _is_ident(src[j]):
                j += 1
            self.err(
                i,
                j,
                "unexpected character %s after a number literal: an identifier "
                "may not start with a digit, and a number carries no suffix"
                % _show(src, i, i + 1),
            )
            i = j
        elif not is_float and int(whole) > U64_MAX:
            self.err(
                start,
                i,
                "integer literal out of range: %s does not fit any integer "
                "type — the widest is u64" % whole.decode("ascii"),
            )
        self.token("float" if is_float else "number", start, i)
        self.i = i

    # -- names (L2, L10) --

    def identifier(self) -> None:
        start = self.i
        i = start
        while i < self.n and _is_ident(self.src[i]):
            i += 1
        self.token("ident", start, i)
        self.i = i

    def at_name(self) -> None:
        start = self.i
        i = start + 1
        while i < self.n and _is_ident(self.src[i]):
            i += 1
        name = self.src[start + 1 : i].decode("ascii", "replace")
        if name not in AT_NAMES:  # L10
            self.err(
                start,
                i,
                "unknown `@%s`: the `@` namespace is exactly `@Self`, `@meta`, "
                "`@scope`, and adding a fourth is a design change" % name,
            )
        self.token("at", start, i)
        self.i = i

    # -- brackets --

    def bracket(self) -> None:
        b = self.src[self.i]
        here = self.i
        self.token("punct", here, here + 1)
        self.i = here + 1
        if self.brackets_lost:
            return
        if b in OPENERS:
            self.opens.append((here, OPENERS[b]))
            return
        want = CLOSERS[b]
        if not self.opens:
            self.err(here, here + 1, "unmatched `%s`" % chr(b))
            self.brackets_lost = True
            return
        at, opener = self.opens[-1]
        if opener == want:
            self.opens.pop()
            return
        # `println("{}", 1 + 2;` then `}`: the `}` closes nothing, and the
        # useful location is the `(` that is still open, not the `}`.
        self.err(
            at,
            at + 1,
            "unclosed `%s`: `%s` closes it, and `%s` arrived first"
            % (opener, MATCHING[opener], chr(b)),
            notes=((here, here + 1, "`%s` here closes nothing" % chr(b)),),
        )
        self.brackets_lost = True

    # -- anything that begins no token (L2, L7) --

    def unexpected_at(self, i: int) -> bool:
        b = self.src[i]
        if b in WHITESPACE or b in PUNCTUATION or b in (QUOTE, APOS, AT):
            return False
        return not (_is_digit(b) or _is_ident_start(b))

    def unit_end(self, i: int) -> int:
        """One byte, or one whole UTF-8 sequence — so a non-ASCII identifier
        is one diagnostic and not three."""
        if self.src[i] < 0x80:
            return i + 1
        j = i + 1
        while j < self.n and 0x80 <= self.src[j] < 0xC0:
            j += 1
        return j

    def stray(self) -> None:
        """A maximal run of such bytes, reported once: `~~` is one mistake."""
        start = self.i
        i = self.unit_end(start)
        while i < self.n and self.unexpected_at(i):
            i = self.unit_end(i)
        if self.src[start:i].startswith(BOM):  # L7
            self.err(
                start,
                i,
                "unexpected character: a byte-order mark is stripped only at "
                "the start of a file, and is an ordinary invalid byte anywhere "
                "else",
            )
        else:
            self.err(
                start,
                i,
                "unexpected character %s: it begins no Zen token"
                % _show(self.src, start, i),
            )
        self.i = i

    def unclosed_at_eof(self) -> None:
        # A file that already failed to lex has an unreliable bracket stack;
        # reporting off it is how one error becomes fifty (TESTING.md).
        if self.brackets_lost or not self.opens or self.diags:
            return
        at, opener = self.opens[0]
        self.err(
            self.n,
            self.n,
            "unclosed `%s`: reached end of file with it still open" % opener,
            notes=((at, at + 1, "`%s` opened here" % opener),),
        )


def scan(source: bytes):
    """-> (tokens, diags). `tokens` is `(kind, start, end)`; a file whose token
    list is empty holds nothing but comments and whitespace."""
    return _Scanner(source).run()
