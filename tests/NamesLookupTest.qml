import QtQuick 2.12
import "../app/Lookup.js" as Lookup
Item {
    function check(ok, reason) { if (!ok) throw new Error(reason); }
    function hasReading(rows, word, reading, kind) {
        return rows.some(function(row) {
            return row.headword===word && row.reading===reading && row.source==='JMnedict' && row.kind.indexOf(kind)>=0;
        });
    }
    Timer {
        interval:20; running:true
        onTriggered: {
            try {
                Lookup.initialize('/userdata/translatepen');
                var cases=[['花子','はなこ','fem'],['健太','けんた','given'],['美咲','みさき','fem'],
                           ['翔太','しょうた','masc'],['陽菜','ひな','fem'],['軽井沢','かるいざわ','place'],
                           ['下田','しもだ','place']];
                for(var i=0;i<cases.length;i++) {
                    var item=cases[i],t=Date.now(),rows=Lookup.lookup(item[0],0,0,item[0].length);
                    check(hasReading(rows,item[0],item[1],item[2]),'Missing name/reading/category '+item[0]);
                    console.log('NAME_LOOKUP '+JSON.stringify({case_id:i,elapsed_ms:Date.now()-t,matches:rows.length}));
                }
                var reading=Lookup.lookup('けんた',0,0,3);
                check(hasReading(reading,'健太','けんた','given'),'Lookup by kana');
                var name=Lookup.lookupFrom('花子に会いました。',0);
                check(name[0].surface==='花子' && name[0].start===0 && name[0].end===2,'Full name wins over one character');
                check(name[0].reasons.length===0,'Names are exact forms');
                var ordinary=Lookup.lookup('下田',0,0,2);
                check(ordinary[0].source==='JMdict','Ordinary definitions stay first');
                check(ordinary.some(function(row){return row.source==='JMnedict';}),'Name alternative retained');
                check(!Lookup.lookup('健太ました',0,0,5).length,'Names cannot accept verb deinflection');
                check(!Lookup.lookup('zqxv987654',2).length,'No-match preserved');
                console.log('TRANSLATEPEN_NAMES_PASS places, given names, kana, alternatives, ranking, spans and deinflection guard');
            } catch(error) { console.log('TRANSLATEPEN_NAMES_FAIL '+error); }
            Qt.quit();
        }
    }
}
