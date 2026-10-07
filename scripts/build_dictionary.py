#!/usr/bin/env python3
"""Convert the original EDRDG JMdict_e XML to a local indexed SQLite dictionary.

Derived dictionary data: EDRDG, CC BY-SA 4.0. Reading/spelling and sense
restrictions are retained. This script does not contact the pen.
"""
import argparse
import gzip
import io
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path


def flags(parts):
    result = 0
    for part in parts:
        if part.startswith('v1'): result |= 1
        if part.startswith('v5') or part == 'v4r': result |= 2
        if part in ('vs', 'vs-i', 'vs-s'): result |= 4
        if part == 'vk': result |= 8
        if part == 'vz': result |= 16
        if part in ('adj-i', 'adj-ix'): result |= 32
    return result


def build(source, target):
    text = gzip.open(source, 'rt', encoding='utf-8').read()
    labels = dict(re.findall(r'<!ENTITY\s+([\w-]+)\s+"([^"]+)"', text))
    text = re.sub(r'&([\w-]+);', lambda m: m[1] if m[1] in labels else m[0], text)
    if target.exists(): raise FileExistsError(target)
    db = sqlite3.connect(target)
    db.executescript('''
        PRAGMA journal_mode=OFF;
        CREATE TABLE entries(id INTEGER PRIMARY KEY, seq INTEGER, headword TEXT,
            reading TEXT, gloss TEXT, pos INTEGER, priority INTEGER);
        CREATE TABLE forms(term TEXT NOT NULL, entry_id INTEGER NOT NULL);
        CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);
    ''')
    count = 0
    context = ET.iterparse(io.StringIO(text), events=('start', 'end'))
    _, root = next(context)
    for event, entry in context:
        if event != 'end' or entry.tag != 'entry': continue
        seq = int(entry.findtext('ent_seq'))
        spellings = entry.findall('k_ele')
        senses = []
        previous_pos = []
        for sense in entry.findall('sense'):
            pos = [p.text for p in sense.findall('pos')] or previous_pos
            previous_pos = pos
            senses.append((sense, pos))
        for reading in entry.findall('r_ele'):
            kana = reading.findtext('reb')
            restrictions = [r.text for r in reading.findall('re_restr')]
            kanji = [k for k in spellings if not restrictions or k.findtext('keb') in restrictions]
            if not kanji or reading.find('re_nokanji') is not None: kanji = [None]
            for k in kanji:
                word = k.findtext('keb') if k is not None else kana
                meanings, tags = [], []
                for sense, pos in senses:
                    sk, sr = [x.text for x in sense.findall('stagk')], [x.text for x in sense.findall('stagr')]
                    if (sk and word not in sk) or (sr and kana not in sr): continue
                    glosses = [g.text for g in sense.findall('gloss') if g.get('{http://www.w3.org/XML/1998/namespace}lang', 'eng') == 'eng']
                    if not glosses: continue
                    qualifiers = [labels.get(x.text, x.text) for tag in ('misc', 'field', 'dial') for x in sense.findall(tag)]
                    meaning = '; '.join(glosses)
                    if qualifiers: meaning += ' [' + ', '.join(qualifiers) + ']'
                    notes = [x.text for x in sense.findall('s_inf')]
                    if notes: meaning += ' (' + '; '.join(notes) + ')'
                    meanings.append(meaning)
                    tags += pos
                if not meanings: continue
                priorities = [x.text for x in reading.findall('re_pri')]
                if k is not None: priorities += [x.text for x in k.findall('ke_pri')]
                priority = max([0] + [100-int(p[2:]) if p.startswith('nf') else 100 if p.endswith('1') else 30 for p in priorities])
                gloss = '\n'.join(f'{i+1}. {g}' for i, g in enumerate(meanings))
                row = db.execute('INSERT INTO entries(seq,headword,reading,gloss,pos,priority) VALUES(?,?,?,?,?,?)',
                                 (seq, word, kana, gloss, flags(tags), priority))
                db.executemany('INSERT INTO forms VALUES(?,?)', [(form, row.lastrowid) for form in sorted({word, kana})])
                count += 1
        entry.clear()
        root.clear()
    db.executescript('CREATE INDEX forms_term ON forms(term); CREATE INDEX entries_seq ON entries(seq);')
    db.executemany('INSERT INTO metadata VALUES(?,?)', [('source','EDRDG JMdict_e'),('license','CC BY-SA 4.0'),('entries',str(count))])
    db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()
    print(json.dumps({'entries': count, 'bytes': target.stat().st_size, 'path': str(target)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    build(args.source, args.target)
