"""Check name restrictions, source preservation, safe builds and ranked lookup."""
from contextlib import redirect_stdout
import gzip
import io
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from add_names_dictionary import build


class NamesBuildTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.base, self.source, self.target = root / "base.sqlite", root / "names.gz", root / "combined.sqlite"
        with sqlite3.connect(self.base) as db:
            db.executescript("""
                CREATE TABLE entries(id INTEGER PRIMARY KEY, seq INTEGER, headword TEXT,
                    reading TEXT, gloss TEXT, pos INTEGER, priority INTEGER);
                CREATE TABLE forms(term TEXT NOT NULL, entry_id INTEGER NOT NULL);
                CREATE INDEX forms_term ON forms(term);
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);
                INSERT INTO entries VALUES(42,100,'高い','たかい','high',32,90);
                INSERT INTO forms VALUES('高い',42),('たかい',42);
                INSERT INTO metadata VALUES('source','JMdict'),('entries','1');
            """)
        with gzip.open(self.source, "wt", encoding="utf-8") as stream:
            stream.write('''<?xml version="1.0"?>
                <!DOCTYPE JMnedict [<!ENTITY given "given name"><!ENTITY place "place name">
                    <!ENTITY company "company name">]>
                <JMnedict>
                <entry><ent_seq>200</ent_seq><k_ele><keb>甲</keb></k_ele><k_ele><keb>乙</keb></k_ele>
                  <r_ele><reb>こう</reb><re_restr>甲</re_restr></r_ele>
                  <r_ele><reb>おつ</reb><re_restr>乙</re_restr></r_ele>
                  <trans><name_type>&place;</name_type><trans_det>A &amp; B</trans_det></trans></entry>
                <entry><ent_seq>201</ent_seq><k_ele><keb>高い</keb></k_ele><r_ele><reb>たかい</reb></r_ele>
                  <trans><name_type>&given;</name_type><trans_det>Takai</trans_det></trans></entry>
                <entry><ent_seq>202</ent_seq><r_ele><reb>あき</reb></r_ele>
                  <trans><name_type>&given;</name_type><trans_det>Aki</trans_det>
                    <trans_det xml:lang="ger">not English</trans_det></trans></entry>
                <entry><ent_seq>203</ent_seq><k_ele><keb>会社</keb></k_ele><r_ele><reb>かいしゃ</reb></r_ele>
                  <trans><name_type>&company;</name_type><trans_det>Company</trans_det></trans></entry>
                </JMnedict>''')

    def test_preserves_words_and_reading_restrictions_and_filters_types(self):
        before = self.base.read_bytes()
        with redirect_stdout(io.StringIO()):
            result = build(self.base, self.source, self.target)
        self.assertEqual(self.base.read_bytes(), before)
        self.assertEqual(result["names_entries"], 4)
        with sqlite3.connect(self.target) as db:
            self.assertEqual(db.execute("SELECT id,pos,priority,source FROM entries WHERE id=42").fetchone(),
                             (42,32,90,"JMdict"))
            self.assertEqual(db.execute("SELECT headword,reading FROM entries WHERE kind='place' ORDER BY headword").fetchall(),
                             [("乙","おつ"),("甲","こう")])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM entries WHERE headword='会社'").fetchone()[0], 0)
            gloss = db.execute("SELECT gloss FROM entries WHERE headword='あき'").fetchone()[0]
            self.assertIn("given name", gloss)
            self.assertNotIn("not English", gloss)
            self.assertIn("A & B", db.execute("SELECT gloss FROM entries WHERE headword='甲'").fetchone()[0])
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='entries'").fetchone()[0], "5")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM entries WHERE source='JMnedict' AND pos!=0").fetchone()[0], 0)

    def test_ranked_index_keeps_words_first_without_sorting_name_readings(self):
        with redirect_stdout(io.StringIO()):
            build(self.base, self.source, self.target)
        with sqlite3.connect(self.target) as db:
            query = """SELECT e.* FROM forms f JOIN entries e ON e.id=f.entry_id
                WHERE f.term=? ORDER BY f.priority DESC,f.entry_id LIMIT 24"""
            self.assertEqual([row[0] for row in db.execute(query, ("高い",))][0], 42)
            plan = " ".join(row[-1] for row in db.execute("EXPLAIN QUERY PLAN " + query, ("高い",)))
            self.assertIn("COVERING INDEX forms_term_rank", plan)
            self.assertNotIn("TEMP B-TREE", plan)

    def test_existing_target_is_not_overwritten(self):
        self.target.write_bytes(b"keep this file")
        with self.assertRaises(FileExistsError):
            build(self.base, self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b"keep this file")


if __name__ == "__main__":
    unittest.main()
