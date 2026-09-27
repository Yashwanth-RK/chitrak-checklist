# -*- coding: utf-8 -*-
"""Verify every compliance-critical token (limits, standards, designations)
in the transcribed data against the source PDFs.

Prose may be merged or lightly normalised; a wrong number or standard would
make the checklist actively misleading, so those are checked exactly.
"""
import re
from _extract import build
from _data_rules import RULES
from _data_ti import INSPECTION

RB, TI = build()

def canon(t):
    t = (t.replace('\u2019', "'").replace('\u2018', "'")
           .replace('\u201c', '"').replace('\u201d', '"')
           .replace('\u2013', '-').replace('\u2014', '-')
           .replace('\u00b0', 'deg').replace('\u00a0', ' '))
    return re.sub(r'\s+', '', t).lower()

RB_C, TI_C = canon(RB), canon(TI)

# OCR renders digit-zero as letter-O in some standard designations
OCR_VARIANTS = [('ul-94vo', 'ul-94v0'), ('far25', 'far25'), ('sfi32a', 'sfi3.2a'),
                ('snellk2000', 'snellk2000'), ('8860', '8860')]

def present(token, source):
    k = canon(token)
    if k in source:
        return True, 'exact'
    # the source sometimes prints digit-zero as letter-O; try that form
    alt = re.sub(r'(?<=[a-z])0', 'o', k)
    if alt != k and alt in source:
        return True, 'ocr-zero'
    # the transcription may normalise morphology the rulebook prints differently
    # ("10 minutes" vs "10 minute", "3 hours" vs "3h rs") -- confirm the value
    m = re.match(r'^(\d[\d,.]*)\s*([a-z]+)$', k)
    if m:
        num, unit = m.group(1), m.group(2)
        for u in {unit.rstrip('s'), unit.rstrip('s') + 's',
                  unit.replace('hours', 'hrs').replace('hour', 'hr'),
                  unit.replace('minutes', 'min').replace('minute', 'min'),
                  unit.replace('seconds', 'sec').replace('second', 'sec'),
                  unit.replace('degrees', 'degree').replace('deg', 'degree')}:
            if f'{num}{u}' in source or f'{num}{u}s' in source:
                return True, 'normalised'
    return False, 'MISSING'

# quantities: number + unit, incl. ranges and percentages
QTY = re.compile(
    r'\b\d[\d,.]*\s?(?:'
    r'kwh|kw|wh|w|v|VDC|kg|kgs?|mm|cm|m|inch(?:es)?|ft|'
    r'deg(?:rees)?|%|seconds?|minutes?|hours?|hrs?|rpm|bar|psi'
    r')\b', re.I)

# named standards / ratings that must appear verbatim
STANDARDS = re.compile(
    r'\b(?:'
    r'SFI\s*[0-9.]+[A-Za-z]?(?:/[0-9.]+)?|'
    r'FIA\s*(?:Standard\s*)?[0-9]{3,4}(?:-[0-9]{2,4})?|'
    r'Snell\s*[A-Z]?[0-9]{4}|'
    r'UL-94\s*V[0O0]|FAR\s*25|IEC\s*60529|IP-?[0-9]{2}|'
    r'SAE\s*Grade\s*[58]|Metric\s*Grade\s*[0-9.]+|AN/MS|'
    r'NABL|3\.31\.4\.8\.2|K[KM]?20[0-9]{2}|M20[0-9]{2}|SA2005'
    r')\b', re.I)

def tokens(text):
    out = []
    for m in QTY.finditer(text):
        out.append(('qty', re.sub(r'\s+', ' ', m.group(0).strip())))
    for m in STANDARDS.finditer(text):
        out.append(('std', re.sub(r'\s+', ' ', m.group(0).strip())))
    seen, uniq = set(), []
    for kind, t in out:
        k = (kind, t.lower())
        if k not in seen:
            seen.add(k)
            uniq.append((kind, t))
    return uniq

def check(items, source, label, code_key):
    print(f'\n{"="*76}\n{label}\n{"="*76}')
    checked = 0
    tally = {'exact': 0, 'ocr-zero': 0, 'normalised': 0}
    problems = []
    for it in items:
        code = it.get(code_key, '?')
        for kind, tok in tokens(it['description']):
            checked += 1
            ok, how = present(tok, source)
            if ok:
                tally[how] = tally.get(how, 0) + 1
            else:
                problems.append((code, it['title'], kind, tok))
    print(f'  tokens checked : {checked}')
    print(f'  exact          : {tally["exact"]}')
    print(f'  ocr zero/O fix : {tally["ocr-zero"]}')
    print(f'  normalised     : {tally["normalised"]}  (e.g. "10 minutes" printed as "10 minute")')
    print(f'  MISSING        : {len(problems)}')
    if problems:
        print(f'\n  {"code":10s} {"kind":4s} {"token":22s} title')
        print('  ' + '-' * 72)
        for code, title, kind, tok in problems:
            print(f'  {code:10s} {kind:4s} {tok:22s} {title[:38]}')
    return problems

p1 = check(RULES,   RB_C, 'RULEBOOK tokens vs Rulebook-V-1.0.pdf', 'rule_code')
p2 = check(INSPECTION, TI_C, 'TI CHECKLIST tokens vs TI SHEET.pdf', 'item_number')

total_bad = len(p1) + len(p2)
print(f'\n{"="*76}\nTOTAL UNVERIFIED TOKENS: {total_bad}\n{"="*76}')
