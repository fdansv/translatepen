import QtQuick 2.12
import "../app/Lookup.js" as Lookup
Item {
    id: root
    width:800; height:480
    Timer { interval:10; running:true; onTriggered:root.runTests() }
    function runTests() {
        try {
            Lookup.initialize('/userdata/translatepen');
            var cases = [
                ['図書館',1,'図書館'], ['日本語',2,'日本語'],
                ['取り扱い',2,'取り扱い'], ['食べました',3,'食べる'],
                ['飲んだ',1,'飲む'], ['高かった',2,'高い'],
                ['来ました',2,'来る'], ['しました',1,'する'],
                ['昨日、図書館で日本語を勉強しました。',4,'図書館']
            ];
            for (var i=0; i<cases.length; ++i) {
                var test=cases[i], began=Date.now(), rows=Lookup.lookup(test[0],test[1]);
                var found=rows.length && rows[0].headword===test[2];
                if (test[2]==='する') found=rows.length && rows[0].reading==='する';
                // JMdict sometimes lists an orthographic alternative first.
                if (test[2]==='取り扱い') found=rows.some(function(x){return x.headword==='取り扱い';});
                if (!found) throw new Error('Unexpected first match for '+test[0]+': '+JSON.stringify(rows.slice(0,2)));
                console.log('PASS '+test[0]+' -> '+rows[0].headword+' '+(Date.now()-began)+'ms');
            }
            var exact=Lookup.lookup('昨日、図書館で読んだ',4,3,6);
            if (!exact.length || exact[0].surface!=='図書館') throw new Error('Exact span failed');
            if (Lookup.lookup('zqxv987654',3).length) throw new Error('No-match case failed');
            var savedId=0;
            Lookup.save('TRANSLATEPEN_AUTOMATED_TEST',exact[0]);
            Lookup.db.transaction(function(tx) {
                var rows=tx.executeSql("SELECT * FROM saved WHERE sentence='TRANSLATEPEN_AUTOMATED_TEST' ORDER BY id DESC LIMIT 1");
                if (rows.rows.length!==1 || rows.rows.item(0).headword!=='図書館') throw new Error('Saving word/context failed');
                savedId=rows.rows.item(0).id;
                tx.executeSql('DELETE FROM saved WHERE id=?',[savedId]);
            });
            console.log('PASS exact span, no-match, and saved context');
            console.log('TRANSLATEPEN_TESTS_PASS');
        } catch(error) { console.log('TRANSLATEPEN_TESTS_FAIL '+error); }
        Qt.quit();
    }
}
