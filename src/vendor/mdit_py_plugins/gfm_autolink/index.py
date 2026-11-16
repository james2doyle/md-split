"""GFM autolink extension rules.

Three inline scanners are registered:

- **gfm_autolink_www** (char ``w``): bare ``www.`` URLs.
  Uses ``add_terminator_char("w")`` so the text scanner interrupts at ``w``.
- **gfm_autolink_protocol** (char ``:``): ``http://``, ``https://``,
  ``mailto:``, ``xmpp:`` URLs via back-scanning ``pending``.
- **gfm_autolink_email** (char ``@``): bare email addresses via
  back-scanning ``pending``.

Since ``:`` and ``@`` are already default terminator characters in
markdown-it-py, the protocol and email rules are invoked at every occurrence
of those characters. They use a *back-scanning* approach: looking backwards
through ``state.pending`` for a protocol prefix or email local-part that was
accumulated by the text rule. This means every ``:`` and ``@`` in the
document incurs a (cheap) regex check or character scan of pending text.

The trade-off vs. a **core-rule** (post-processing) approach — which would
walk the final token stream, find autolink patterns in text tokens, and
split them — is:

- **Inline approach** (current): simpler, integrates naturally with
  ``state.linkLevel`` to suppress matching inside links, but relies on the
  prefix being present in ``state.pending`` (if a prior inline rule consumed
  part of the prefix, matching would fail — unlikely in practice).
- **Core-rule approach**: guaranteed to find all autolinks regardless of
  inline rule ordering, but requires token-stream surgery (splitting text
  tokens and inserting link tokens) and cannot easily interact with nesting
  guards like ``linkLevel``.

The ``w`` terminator is the only *new* terminator added. It causes the text
rule to interrupt at every ``w``, which is a minor performance cost for
documents heavy in that letter, but necessary since ``www.`` must be matched
from the start of the URL.

Specification: https://github.github.com/gfm/#autolinks-extension-

.. versionadded:: 0.5.0

Requires markdown-it-py ≥ 4.1.0.
"""

from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline

from ._match import check_prev, match_http, match_www

_PROTOCOLS = ("https", "http", "mailto", "xmpp")
_EMAIL_LOCAL_CHARS = frozenset(".+-_")


def gfm_autolink_plugin(md: MarkdownIt) -> None:
    """Enable the GFM autolink extension.

    Recognises bare ``www.`` URLs, ``http(s)://`` URLs,
    ``mailto:``/``xmpp:`` links, and bare email addresses.

    Requires markdown-it-py ≥ 4.1.0.
    """
    if not hasattr(md.inline, "add_terminator_char"):
        raise RuntimeError("gfm_autolink_plugin requires markdown-it-py >= 4.1.0")

    md.inline.add_terminator_char("w")
    md.inline.ruler.push("gfm_autolink_www", _www_inline_rule)
    md.inline.ruler.push("gfm_autolink_protocol", _protocol_rule)
    md.inline.ruler.push("gfm_autolink_email", _email_rule)


# ---------------------------------------------------------------------------
# Helpers (inline rules)
# ---------------------------------------------------------------------------


def _preceding_ok(state: StateInline, bscan_len: int) -> bool:
    """Check whether the character before the back-scanned portion allows an autolink."""
    abs_pos = state.pos - bscan_len
    if abs_pos <= 0:
        return True
    preceding = state.src[abs_pos - 1]
    return check_prev(preceding)


def _create_autolink(
    state: StateInline,
    bscan_len: int,
    total_len: int,
    url: str,
    text: str,
) -> bool:
    """Emit ``link_open`` / ``text`` / ``link_close`` tokens.

    *bscan_len* characters are trimmed from the end of ``state.pending``
    (the back-scanned protocol or local part).  The parser position is
    then advanced by ``total_len - bscan_len`` characters.
    """
    if bscan_len:
        state.pending = state.pending[:-bscan_len]

    full_url = state.md.normalizeLink(url)
    if not state.md.validateLink(full_url):
        return False

    token = state.push("link_open", "a", 1)
    token.attrs = {"href": full_url}
    token.markup = "autolink"
    token.info = "auto"

    token = state.push("text", "", 0)
    token.content = state.md.normalizeLinkText(text)

    token = state.push("link_close", "a", -1)
    token.markup = "autolink"
    token.info = "auto"

    state.pos += total_len - bscan_len
    return True


def _is_email_local_char(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in _EMAIL_LOCAL_CHARS)


def _scan_email_domain(
    src: str, start: int, end: int, protocol: str | None
) -> int | None:
    """Return the end of a valid email domain, or ``None``."""
    link_end = start
    periods = 0
    slashes = 0
    while link_end < end:
        ch = src[link_end]
        if ch.isascii() and ch.isalnum():
            pass
        elif ch == "@":
            if protocol != "xmpp":
                return None
        elif (
            ch == "."
            and link_end + 1 < end
            and src[link_end + 1].isascii()
            and src[link_end + 1].isalnum()
        ):
            periods += 1
        elif ch == "/" and protocol == "xmpp" and slashes == 0:
            slashes += 1
        elif ch != "-" and ch != "_":
            break
        link_end += 1

    if link_end < start + 1 or periods == 0:
        return None
    last_ch = src[link_end - 1]
    if not (last_ch.isascii() and last_ch.isalpha()) and last_ch != ".":
        return None
    return link_end


# ---------------------------------------------------------------------------
# www inline rule  (requires add_terminator_char("w") — markdown-it-py >= 4.1.0)
# ---------------------------------------------------------------------------


def _www_inline_rule(state: StateInline, silent: bool) -> bool:
    """Match ``www.`` autolinks as an inline rule (trigger char: ``w``)."""
    if state.linkLevel > 0:
        return False

    pos = state.pos
    src = state.src

    # Quick check: must be 'w' and form "www."
    if src[pos] != "w":
        return False
    if pos + 4 > state.posMax or src[pos : pos + 4] != "www.":
        return False

    # Check preceding character (from pending text or start-of-line).
    if state.pending:
        preceding = state.pending[-1]
        if not check_prev(preceding):
            return False
    elif pos > 0:
        preceding = src[pos - 1]
        if not check_prev(preceding):
            return False

    result = match_www(src[pos : state.posMax])
    if result is None:
        return False

    url, length = result
    label = src[pos : pos + length]

    if silent:
        # Autolinks are only recognised when emitting tokens. When skipping
        # silently (e.g. scanning a link label), report no match so the parser
        # steps over this text as plain characters (#160).
        return False

    full_url = state.md.normalizeLink(url)
    if not state.md.validateLink(full_url):
        return False

    token = state.push("link_open", "a", 1)
    token.attrs = {"href": full_url}
    token.markup = "autolink"
    token.info = "auto"

    token = state.push("text", "", 0)
    token.content = state.md.normalizeLinkText(label)

    token = state.push("link_close", "a", -1)
    token.markup = "autolink"
    token.info = "auto"

    state.pos += length
    return True


# ---------------------------------------------------------------------------
# Protocol scanner  (trigger char: ':')
# ---------------------------------------------------------------------------


def _protocol_rule(state: StateInline, silent: bool) -> bool:
    if state.linkLevel > 0:
        return False

    pos = state.pos
    end = state.posMax
    if pos >= end or state.src[pos] != ":":
        return False

    # Check only the bounded suffix instead of searching all pending text at
    # every colon; pending-text searches make colon-heavy input quadratic.
    proto = next(
        (name for name in _PROTOCOLS if state.pending.endswith(name)), None
    )
    if proto is None:
        return False

    bscan_len = len(proto)
    if not _preceding_ok(state, bscan_len):
        return False

    if proto in ("mailto", "xmpp"):
        local_start = pos + 1
        local_end = local_start
        while local_end < end and _is_email_local_char(state.src[local_end]):
            local_end += 1
        if (
            local_end == local_start
            or local_end >= end
            or state.src[local_end] != "@"
        ):
            return False
        domain_end = _scan_email_domain(state.src, local_end + 1, end, proto)
        if domain_end is None:
            return False
        email_text = state.src[local_start:domain_end]
        full_url = f"{proto}:{email_text}"
        label = full_url
        total_len = bscan_len + 1 + len(email_text)
    else:
        # Avoid copying the remaining paragraph unless this is a real protocol.
        if pos + 3 > end or state.src[pos : pos + 3] != "://":
            return False
        remaining = state.src[pos:end]
        combined = proto + remaining
        result = match_http(combined)
        if result is None:
            return False
        full_url, total_len = result
        label = combined[:total_len]

    if silent:
        return False  # see _www_inline_rule
    return _create_autolink(state, bscan_len, total_len, full_url, label)


# ---------------------------------------------------------------------------
# Bare email scanner  (trigger char: '@')
# ---------------------------------------------------------------------------


def _email_rule(state: StateInline, silent: bool) -> bool:
    if state.linkLevel > 0:
        return False

    pos = state.pos
    if pos >= state.posMax or state.src[pos] != "@":
        return False
    # Need at least one character after '@'.
    if pos + 1 >= state.posMax:
        return False

    # Back-scan pending text for the local part of the email.
    local_start = len(state.pending)
    while (
        local_start > 0
        and _is_email_local_char(state.pending[local_start - 1])
    ):
        local_start -= 1
    local_len = len(state.pending) - local_start
    if local_len == 0:
        return False
    if not _preceding_ok(state, local_len):
        return False

    domain_end = _scan_email_domain(state.src, pos + 1, state.posMax, None)
    if domain_end is None:
        return False

    local_part = state.pending[local_start:]
    email_text = local_part + state.src[pos:domain_end]
    total_len = domain_end - pos + local_len
    url = "mailto:" + email_text

    if silent:
        return False  # see _www_inline_rule
    return _create_autolink(state, local_len, total_len, url, email_text)
