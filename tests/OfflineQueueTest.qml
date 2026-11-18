import QtQuick 2.12
import "../app"
import "../app/Lookup.js" as Lookup
Item {
    id:root; width:800; height:480
    property var sent:[]
    property int analyses:0
    property string firstKey:''
    QtObject {
        id:service
        property bool online:false
        property bool bRepeat:false
        signal analyzed(int requestId,string response)
        signal analysisFailed(int requestId)
        signal ingested(string key,string jobId,string state)
        signal ingestionFailed(string key,string explanation,bool retryable)
        signal jobStatus(string key,string state,string error)
        signal markedKnown(int requestId,string response)
        signal knownFailed(int requestId,string explanation)
        function analyze(text,id) { root.analyses++; }
        function cancelAnalysis() {}
        function checkConnection() {}
        function markKnown(payload,id) { root.fail('offline known request'); }
        function watchJob(job,key) {}
        function ingest(payload,key) {
            root.sent.push({payload:payload,key:key});
            if (root.sent.length===1) {
                root.firstKey=key; online=false;
                ingestionFailed(key,'Saved on pen',true);
                reconnect.start();
            } else ingested(key,'job-'+root.sent.length,'queued');
        }
    }
    Japanese { id:page; standalone:true; migakuBridge:service }
    function fail(reason) { console.log('TRANSLATEPEN_OFFLINE_QUEUE_FAIL '+reason); Qt.quit(); }
    function check(ok,reason) { if (!ok) fail(reason); return ok; }
    function pair() { page.pressB(); page.firstBAt=Date.now()-100; page.pressB(); }
    Timer {
        interval:250; running:true
        onTriggered: {
            Lookup.db.transaction(function(tx) { tx.executeSql("DELETE FROM migaku_outbox WHERE payload LIKE '%OFFLINE_QUEUE_TEST%'"); });
            page.acceptScan('図書館、日本語、食べました。OFFLINE_QUEUE_TEST');
            page.lookupAt(0); pair(); pair(); page.nextWord(); pair(); page.nextWord(); pair();
            page.refreshQueue();
            if (!check(root.sent.length===0 && root.analyses===0 && page.queueCounts.pending===3,'offline saves and dedupes without network')) return;
            var rows=Lookup.queueEntries();
            if (!check(rows.length===3 && rows[0].reading.length>0 && rows[0].gloss.length>0,'local dictionary snapshot retained')) return;
            page.queueVisible=true; pair();
            if (!check(Lookup.queueSummary().pending===3,'queue overlay blocks hidden B saves')) return;
            page.queueVisible=false;
            service.online=true;
        }
    }
    Timer {
        id:reconnect; interval:100
        onTriggered: {
            if (!check(Lookup.queueSummary().pending===3,'connection loss keeps all requests')) return;
            service.online=true; finished.start();
        }
    }
    Timer {
        id:finished; interval:250
        onTriggered: {
            if (root.sent.length<4 || Lookup.queueSummary().sent<3) { finished.restart(); return; }
            if (!check(root.sent.length===4 && root.sent[1].key===root.firstKey && Lookup.queueSummary().sent===3,'reconnect drains whole queue and reuses request key')) return;
            var keys={};
            for (var i=0;i<root.sent.length;++i) keys[root.sent[i].key]=true;
            if (!check(Object.keys(keys).length===3,'three unique cards despite uncertain first response')) return;
            service.jobStatus(root.firstKey,'uncertain','write_uncertain');
            if (!check(Lookup.queueSummary().attention===1,'uncertain card kept for checking')) return;
            page.flushOutbox();
            if (!check(root.sent.length===4,'accepted and uncertain cards never resubmitted')) return;
            for (var key in keys) service.jobStatus(key,'synced','');
            if (!check(page.queueCounts.total===0 && Lookup.queueSummary().complete===3,'only confirmed sync clears waiting count')) return;
            Lookup.db.transaction(function(tx) { tx.executeSql("DELETE FROM migaku_outbox WHERE payload LIKE '%OFFLINE_QUEUE_TEST%'"); });
            console.log('TRANSLATEPEN_OFFLINE_QUEUE_PASS offline lookup, durable snapshots, automatic batch, reconnect idempotency and uncertain writes'); Qt.quit();
        }
    }
    Timer { interval:6000; running:true; onTriggered:root.fail('deadline, uploads='+root.sent.length+' pending='+Lookup.queueSummary().pending+' retry='+page.retryAfter) }
}
