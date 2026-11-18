import QtQuick 2.12
import QtQuick.LocalStorage 2.0 as Sql
import "../app/Lookup.js" as Lookup
Item {
    Timer {
        interval:30; running:true
        onTriggered: {
            try {
                var reading=false;
                var payload=JSON.stringify({language:'ja',sentence:'図書館 QUEUE_RESTART_TEST',focus_word:'図書館',focus_start:0,focus_end:3});
                {
                    var db=Sql.LocalStorage.openDatabaseSync('TranslatePen','1.0','Japanese lookup and saved words',1000000);
                    db.transaction(function(tx) {
                        tx.executeSql('CREATE TABLE IF NOT EXISTS migaku_outbox(key TEXT PRIMARY KEY,payload TEXT UNIQUE,state TEXT,job TEXT,error TEXT)');
                        reading=tx.executeSql("SELECT key FROM migaku_outbox WHERE key='stable-legacy-key'").rows.length>0;
                        if (!reading) tx.executeSql("INSERT INTO migaku_outbox(key,payload,state) VALUES('stable-legacy-key',?,'pending')",[payload]);
                    });
                }
                Lookup.initialize('/userdata/translatepen');
                var row=Lookup.queueIngestion(payload,{headword:'図書館',reading:'としょかん',gloss:'library'});
                if (row.key!=='stable-legacy-key' || row.state!=='pending') throw new Error('Legacy queue key or state lost');
                var entries=Lookup.queueEntries(),found=false;
                for (var i=0;i<entries.length;++i) if (entries[i].key==='stable-legacy-key' && entries[i].gloss==='library') found=true;
                if (!found) throw new Error('Snapshot not durable');
                if (reading) Lookup.db.transaction(function(tx) { tx.executeSql("DELETE FROM migaku_outbox WHERE key='stable-legacy-key'"); });
                console.log('TRANSLATEPEN_QUEUE_PERSISTENCE_PASS '+(reading ? 'read after process restart' : 'legacy migration/write'));
            } catch(error) { console.log('TRANSLATEPEN_QUEUE_PERSISTENCE_FAIL '+error); }
            Qt.quit();
        }
    }
}
