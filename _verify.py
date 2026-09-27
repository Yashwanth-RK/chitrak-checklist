# -*- coding: utf-8 -*-
"""Verify every transcribed description against the source PDFs.

Both sides are compared whitespace-insensitively, which erases the PDF's
fragmentation artifacts ("T h e   w h e e l b a s e") so a faithful
transcription must appear verbatim in the source.
"""
import re, io
from _extract import build
from _data_rules import RULES
from _data_ti import INSPECTION

RB, TI = build()

def squeeze(t):
    return re.sub(r'\s+', '', t).lower()

# normalise quote/dash variants the OCR likes to mutate
def canon(t):
    t = (t.replace('\u2019', "'").replace('\u2018', "'")
           .replace('\u201c', '"').replace('\u201d', '"')
           .replace('\u2013', '-').replace('\u2014', '-')
           .replace('\u00b0', 'deg').replace('\u00a0', ' '))
    return squeeze(t)

RB_C, TI_C = canon(RB), canon(TI)

# OCR writes digit zero as letter O in standard designations
OCR_FIX = [('ul-94vo', 'ul-94v0'), ('32a/5', '32.2a/5'), ('sfi32a', 'sfi3.2a'),
           ('886-2004', '8860-2004'), ('k2005', 'k2005')]
def variants(key):
    out = {key}
    for bad, good in OCR_FIX:
        if bad in key:
            out.add(key.replace(bad, good))
    return out

def sentences(text):
    parts = re.split(r'(?<=[.;])\s+', text)
    return [p.strip() for p in parts if len(p.strip()) > 12]

def probe(s):
    """The source frequently ends a clause with a lettered marker (a\\ b\\ c\\)
    instead of punctuation, so trailing sentence punctuation cannot be trusted."""
    return canon(s.rstrip(' .,;:'))

def verify(items, source, label, code_key):
    full_ok, partial, missing = [], [], []
    for it in items:
        key = probe(it['description'])
        if any(v in source for v in variants(key)):
            full_ok.append(it)
            continue
        sents = sentences(it['description'])
        hit = [s for s in sents if probe(s) in source]
        if not hit:
            missing.append((it, sents))
        elif len(hit) < len(sents):
            partial.append((it, [s for s in sents if probe(s) not in source]))
    total = len(items)
    print(f'\n{"="*74}\n{label}  ({total} items)\n{"="*74}')
    print(f'  exact match in source        : {len(full_ok):3d}  ({len(full_ok)*100//total}%)')
    print(f'  partially matched (review)   : {len(partial):3d}')
    print(f'  no sentence matched (review): {len(missing):3d}')
    return full_ok, partial, missing

ok_r, part_r, miss_r = verify(RULES, RB_C, 'RULEBOOK (vs Rulebook-V-1.0.pdf)', 'rule_code')
ok_t, part_t, miss_t = verify(INSPECTION, TI_C, 'TI CHECKLIST (vs TI SHEET.pdf)', 'item_number')

def dump(title, rows, code_key):
    if not rows:
        return
    print(f'\n{title}')
    for it, sents in rows:
        code = it.get(code_key) or it.get('rule_code') or it.get('item_number')
        print(f'\n  [{code}] {it["title"]}')
        for s in sents:
            print(f'      - {s[:150]}')

dump('RULEBOOK — sentences not found verbatim', part_r, 'rule_code')
dump('RULEBOOK — no sentence matched', miss_r, 'rule_code')
dump('TI — sentences not found verbatim', part_t, 'item_number')
dump('TI — no sentence matched', miss_t, 'item_number')
