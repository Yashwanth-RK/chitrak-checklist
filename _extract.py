# -*- coding: utf-8 -*-
"""Extract plain text from the source PDFs, robust to positional/fragmented text."""
import re, zlib, io

def pdf_streams(path):
    data = io.open(path, 'rb').read()
    out = []
    for m in re.finditer(rb'stream[\r\n]+(.*?)[\r\n]+endstream', data, re.S):
        raw = m.group(1)
        for wbits in (15, -15):
            try:
                out.append(zlib.decompress(raw, wbits))
                break
            except Exception:
                try:
                    out.append(zlib.decompress(raw))
                    break
                except Exception:
                    continue
    return out

def text_from_streams(streams):
    """Pull literal strings out of Tj / TJ / ' / " operators."""
    parts = []
    for d in streams:
        try:
            s = d.decode('latin-1')
        except Exception:
            continue
        for m in re.finditer(r'\((?:\\.|[^\\()])*\)', s):
            lit = m.group(0)[1:-1]
            lit = re.sub(r'\\([()\\])', r'\1', lit)
            lit = lit.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')
            parts.append(lit)
    return ' '.join(parts)

def squeeze(t):
    """Whitespace-insensitive form. Kills every PDF spacing artifact at once."""
    return re.sub(r'\s+', '', t).lower()

def raw_literals(path):
    """TI SHEET.pdf is a scan-adjacent export whose page text sits in plain
    uncompressed operators alongside DCTDecode images, so read the file body."""
    data = io.open(path, 'rb').read().decode('latin-1')
    parts = []
    for m in re.finditer(r'\((?:\\.|[^\\()])*\)\s*Tj', data):
        lit = m.group(0)
        lit = lit[1:lit.rindex(')')]
        lit = re.sub(r'\\([()\\])', r'\1', lit)
        parts.append(lit)
    return ' '.join(parts)

def build():
    rb = squeeze(text_from_streams(pdf_streams('Rulebook-V-1.0.pdf')))
    ti = squeeze(raw_literals('TI SHEET.pdf'))
    return rb, ti

if __name__ == '__main__':
    rb, ti = build()
    print('rulebook squeezed chars:', len(rb))
    print('TI sheet squeezed chars:', len(ti))
    io.open('_src_rb.txt', 'w', encoding='utf-8').write(rb)
    io.open('_src_ti.txt', 'w', encoding='utf-8').write(ti)
    probes = [
        'minimum ground clearance should be 5 inches',
        'it should vary from 1250W to 2000W',
        'SFI 3.2A/5',
        'UL-94 V0',
        'IEC 60529 IP67',
        'range of 48 inches to 62 inches',
        'Bicycle tires are prohibited',
        'should not exceed more than 80 inches',
        'minimum diameter of the tires should be 16 inches',
        'Minimum Energy: 1.5 KWh',
        'track should be covered within 10 seconds',
        'at least two dry chemical',
        'metric grade 8.8',
        'Snell K2000',
    ]
    for probe in probes:
        k = re.sub(r'\s+', '', probe).lower()
        print(f'  {probe[:44]:46s} rb={str(k in rb):5s} ti={k in ti}')
