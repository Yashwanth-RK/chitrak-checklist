"""Assemble the single-file dashboard from head + generated script + tail.

The head and tail fragments are split out of the dashboard on first run so the
markup and CSS stay hand-editable, then re-joined with a freshly generated
<script> block. If the fragments are missing they are recovered from the
dashboard itself, so `npm run build` works from a clean checkout.
"""
import io
import os

TARGET = 'Chitrak — Rulebook Checklist.html'
HEAD = '_head.html'
SCRIPT = '_new_script.html'
TAIL = '_tail.html'


def ensure_fragments():
    if all(os.path.exists(f) for f in (HEAD, TAIL)) and os.path.exists(SCRIPT):
        return
    src = io.open(TARGET, encoding='utf-8').read()
    i = src.index('<script>')
    j = src.rindex('</script>') + len('</script>')
    if not os.path.exists(HEAD):
        io.open(HEAD, 'w', encoding='utf-8').write(src[:i])
    if not os.path.exists(TAIL):
        io.open(TAIL, 'w', encoding='utf-8').write(src[j:])
    if not os.path.exists(SCRIPT):
        io.open(SCRIPT, 'w', encoding='utf-8').write(src[i + len('<script>'):j - len('</script>')])


def main():
    ensure_fragments()
    out = (io.open(HEAD, encoding='utf-8').read()
           + io.open(SCRIPT, encoding='utf-8').read()
           + io.open(TAIL, encoding='utf-8').read())
    io.open(TARGET, 'w', encoding='utf-8').write(out)

    # hand a copy to node --check so a syntax error fails the build
    a = out.index('<script>') + len('<script>')
    b = out.rindex('</script>')
    io.open('/tmp/_chitrak_check.mjs', 'w', encoding='utf-8').write(out[a:b])

    print('assembled %s  (%d chars, %d lines)' % (TARGET, len(out), out.count('\n')))


if __name__ == '__main__':
    main()
