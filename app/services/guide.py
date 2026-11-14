"""A tiny, safe markdown subset for setup guides. Everything is escaped first; only these shapes become HTML:

    # Heading / ## Heading      -> <h3> / <h4>
    - item                      -> bullet list
    1. step                     -> numbered list
    ```                         -> a code block (lines kept as typed, escaped)
    `code`                      -> inline code
    blank line                  -> new paragraph

No raw HTML, no links, no images, no attributes: a guide cannot carry markup of its own.
"""
import re

from markupsafe import Markup, escape

_INLINE_CODE = re.compile(r"`([^`\n]{1,200})`")


def _inline(line):
    safe = str(escape(line))
    return _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", safe)


def render_guide(text):
    out, para, lst, code = [], [], None, None

    def flush_para():
        if para:
            out.append("<p>" + " ".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def flush_list():
        nonlocal lst
        if lst:
            tag, items, start = lst
            open_tag = f'<ol start="{start}">' if tag == "ol" and start != 1 else f"<{tag}>"
            out.append(open_tag + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{tag}>")
        lst = None

    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if code is not None:
            if line.strip().startswith("```"):
                out.append("<pre><code>" + "\n".join(str(escape(c)) for c in code) + "</code></pre>")
                code = None
            else:
                code.append(raw)
            continue
        if line.strip().startswith("```"):
            flush_para(); flush_list()
            code = []
            continue
        if not line.strip():
            flush_para(); flush_list()
            continue
        m = re.match(r"^(#{1,2})\s+(.*)$", line)
        if m:
            flush_para(); flush_list()
            tag = "h3" if len(m.group(1)) == 1 else "h4"
            out.append(f"<{tag}>{_inline(m.group(2))}</{tag}>")
            continue
        m = re.match(r"^\s*(?:[-*]|(\d{1,3})\.)\s+(.*)$", line)
        if m:
            flush_para()
            tag = "ol" if m.group(1) else "ul"
            if lst is None or lst[0] != tag:
                flush_list()
                lst = (tag, [], int(m.group(1)) if m.group(1) else 1)
            lst[1].append(m.group(2))
            continue
        flush_list()
        para.append(line.strip())
    if code is not None:                                  # an unclosed block still comes out escaped
        out.append("<pre><code>" + "\n".join(str(escape(c)) for c in code) + "</code></pre>")
    flush_para(); flush_list()
    return Markup("".join(out))  # nosec B704 - every piece above went through escape()
