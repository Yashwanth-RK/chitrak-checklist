# -*- coding: utf-8 -*-
"""Readable extraction of the rulebook: repairs the PDF's intra-word letter
spacing (e.g. "T h e   w h e e l b a s e") without merging separate words."""
import re, io, zlib
from _extract import build, pdf_streams, text_from_streams

def ordered_text(path):
    """Walk each page's content stream in operator order so words come out in
    reading order rather than byte order (the PDF interleaves columns)."""
    chunks = []
    for d in pdf_streams(path):
        try:
            s = d.decode('latin-1')
        except Exception:
            continue
        if 'Tj' not in s and 'TJ' not in s:
            continue
        for m in re.finditer(r'\[((?:[^\[\]\\]|\\.)*)\]\s*TJ|\(((?:[^()\\]|\\.)*)\)\s*Tj', s):
            if m.group(1) is not None:
                lits = re.findall(r'\(((?:[^()\\]|\\.)*)\)', m.group(1))
                chunks.append(''.join(lits))
            else:
                chunks.append(m.group(2))
        chunks.append(' ')
    out = []
    for c in chunks:
        c = re.sub(r'\\([()\\])', r'\1', c)
        out.append(c.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' '))
    return ' '.join(out)

def defrag(s):
    # Each single letter must stand alone as a word, hence \b on both sides.
    # Repeated to a fixed point: a greedy long pass can leave a short remainder.
    pats = [r'\b(?:' + r'[A-Za-z]\s' * (n - 1) + r'[A-Za-z])\b' for n in range(12, 1, -1)]
    for _ in range(6):
        before = s
        for pat in pats:
            s = re.sub(pat, lambda m: re.sub(r'\s+', '', m.group(0)), s)
        if s == before:
            break
    s = re.sub(r'(?<=\d)\s(?=\d)', '', s)          # rejoin split digits
    s = re.sub(r'(?<=\d)\s*\.\s*(?=\d)', '.', s)   # rejoin split decimals
    s = re.sub(r'I SIEINDIA All Right Reserved\s*2024\s*-\s*2025\s*'
               r'Rulebook Last Updated\s*25\s*th\s*Febru\s*ary\s*2024\s*\|\s*\d+',
               ' [[PAGE]] ', s)
    s = re.sub(r'\.{4,}', ' ... ', s)
    s = re.sub(r'[ \t]+', ' ', s)
    return s

def readable():
    return defrag(ordered_text('Rulebook-V-1.0.pdf'))

if __name__ == '__main__':
    T = readable()
    io.open('_rb_readable.txt', 'w', encoding='utf-8').write(T)
    print('chars:', len(T))
    probes = ['wheelbase of the bike', 'C.10.4.7', 'Zip tags are prohibited',
              'sports shoes', 'Static Rounds', 'Acceleration Test',
              'Command Flags', 'Slack Rating', 'Self Balancing']
    low = T.lower()
    for p in probes:
        print(f'  {p:28s} {low.find(p.lower())}')
