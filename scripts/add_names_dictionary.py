#!/usr/bin/env python3
"""Add EDRDG JMnedict personal/place names to a copy of the local dictionary.

Derived data remains CC BY-SA 4.0. The base dictionary and pen are untouched.
Existing entry IDs and deinflection flags are preserved.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import xml.etree.ElementTree as ET


NAME_TYPES = {
    "place": "place name",
    "station": "station name",
    "given": "given name",
    "fem": "female given name",
    "masc": "male given name",
    "surname": "surname",
    "person": "person's full name",
    "unclass": "unclassified name",
}


def build(base, source, target):
    if target.exists():
        raise FileExistsError(target)
    text = gzip.open(source, "rt", encoding="utf-8").read()
    entities = dict(re.findall(r'<!ENTITY\s+([\w-]+)\s+"([^"]+)"', text))
    text = re.sub(r"&([\w-]+);", lambda m: m[1] if m[1] in entities else m[0], text)
    origin = sqlite3.connect(f"file:{base.resolve()}?mode=ro", uri=True)
    db = sqlite3.connect(target)
    try:
        if origin.execute("SELECT value FROM metadata WHERE key='names_source'").fetchone():
            raise ValueError("Use the original JMdict database, not an already augmented copy")
        word_count = origin.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        origin.backup(db)
        db.executescript("""
            PRAGMA journal_mode=OFF;
            ALTER TABLE entries ADD COLUMN source TEXT NOT NULL DEFAULT 'JMdict';
            ALTER TABLE entries ADD COLUMN kind TEXT NOT NULL DEFAULT '';
            ALTER TABLE forms ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;
            UPDATE forms SET priority=(SELECT priority FROM entries WHERE id=entry_id);
        """)
        count, categories = 0, Counter()
        context = ET.iterparse(io.StringIO(text), events=("start", "end"))
        _, root = next(context)
        for event, entry in context:
            if event != "end" or entry.tag != "entry":
                continue
            meanings, kinds = [], set()
            for translation in entry.findall("trans"):
                tags = [node.text for node in translation.findall("name_type") if node.text in NAME_TYPES]
                if not tags:
                    continue
                glosses = [node.text for node in translation.findall("trans_det") if node.text and
                           node.get("{http://www.w3.org/XML/1998/namespace}lang", "eng") == "eng"]
                if not glosses:
                    continue
                meanings.append("; ".join(glosses) + " [" + ", ".join(NAME_TYPES[tag] for tag in tags) + "]")
                kinds.update(tags)
            if meanings:
                seq = int(entry.findtext("ent_seq"))
                spellings = [node.findtext("keb") for node in entry.findall("k_ele")]
                gloss = "\n".join(f"{i + 1}. {value}" for i, value in enumerate(meanings))
                for reading in entry.findall("r_ele"):
                    kana = reading.findtext("reb")
                    restrictions = [node.text for node in reading.findall("re_restr")]
                    words = [word for word in spellings if not restrictions or word in restrictions]
                    if not spellings:
                        words = [kana]
                    for word in words:
                        row = db.execute("""INSERT INTO entries
                            (seq,headword,reading,gloss,pos,priority,source,kind)
                            VALUES(?,?,?,?,0,-1,'JMnedict',?)""",
                            (seq, word, kana, gloss, "|".join(sorted(kinds))))
                        db.executemany("INSERT INTO forms(term,entry_id,priority) VALUES(?,?,-1)",
                                       [(form, row.lastrowid) for form in sorted({word, kana})])
                        count += 1
                        categories.update(kinds)
            entry.clear()
            root.clear()
        # Ordering in this index avoids sorting thousands of name readings for
        # an ambiguous kana form. Ordinary dictionary definitions come first.
        db.executescript("""
            CREATE INDEX forms_term_rank ON forms(term,priority DESC,entry_id);
            DROP INDEX forms_term;
        """)
        db.executemany("INSERT INTO metadata(key,value) VALUES(?,?)", [
            ("word_entries", str(word_count)),
            ("names_source", "EDRDG JMnedict"),
            ("names_license", "CC BY-SA 4.0"),
            ("names_source_sha256", hashlib.sha256(source.read_bytes()).hexdigest()),
            ("names_entries", str(count)),
            ("names_categories", json.dumps(dict(sorted(categories.items())))),
            ("lookup_schema", "2"),
        ])
        db.execute("UPDATE metadata SET value=? WHERE key='entries'", (str(word_count + count),))
        db.execute("UPDATE metadata SET value=? WHERE key='source'", ("EDRDG JMdict_e + JMnedict",))
        db.commit()
        db.execute("VACUUM")
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        total = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    finally:
        origin.close()
        db.close()
    result = {"names_entries": count, "total_entries": total, "categories": dict(categories),
              "bytes": target.stat().st_size, "path": str(target)}
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    build(args.base, args.source, args.target)
