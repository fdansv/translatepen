// Runs with the pen's own Qt/SQLite. No live Migaku cards are created.
import QtQuick 2.12
import "../app"
import "../app/Lookup.js" as Lookup
Item {
    id:root
    width:800; height:480
    property var sent:[]
    property int analyses:0
    property var payload
    QtObject {
        id:gbKey
        signal foreKeyPress()
        signal scanKeyPress()
        signal scanKeyRelease()
        signal circularKeyPress()
        signal volumeUpKeyPress()
        signal volumeDownKeyPress()
    }
    QtObject { id:statusbar; property bool visible:true; property string cur_module_name:'Jp' }
    QtObject {
        id:commonCenter
        function getOcrlanid() { return 918; }
        function setOcrlanid(value) {}
        function stopAllaudioplay() {}
        function setScanread(value) {}
        function setInEdit(value) {}
        function setcanstoptts(value) {}
    }
    QtObject {
        id:scanner
        signal recognized(int requestId,string text,real roundtripMs,real serverMs)
        signal failed(int requestId,string explanation)
        signal captureStopped(int requestId,real durationMs,int imageBytes)
        function cancel() {}
        function beginScan(center) { return true; }
        function endScan(center,id) {}
    }
    QtObject {
        id:migaku
        property bool bRepeat:false
        signal analyzed(int requestId,string response)
        signal analysisFailed(int requestId)
        signal ingested(string key,string jobId,string state)
        signal ingestionFailed(string key,string explanation,bool retryable)
        signal jobStatus(string key,string state,string error)
        signal markedKnown(int requestId,string response)
        signal knownFailed(int requestId,string explanation)
        function markKnown(payload,id) {}
        function analyze(sentence,id) { root.analyses++; }
        function cancelAnalysis() {}
        function watchJob(job,key) {}
        function ingest(payload,key) { root.sent.push({payload:payload,key:key}); }
    }
    Japanese { id:page; scannerBridge:scanner; migakuBridge:migaku }
    function check(ok,reason) {
        if (!ok) { console.log('TRANSLATEPEN_MIGAKU_FAIL '+reason); cleanup(); Qt.quit(); }
        return ok;
    }
    function cleanup() {
        Lookup.db.transaction(function(tx) { tx.executeSql("DELETE FROM migaku_outbox WHERE payload LIKE '%TRANSLATEPEN_MIGAKU_TEST%'"); });
    }
    function pair() { gbKey.foreKeyPress(); page.firstBAt=Date.now()-100; gbKey.foreKeyPress(); }
    Timer {
        interval:300; running:true
        onTriggered: { cleanup(); page.acceptScan('図書館、蛞蝓。TRANSLATEPEN_MIGAKU_TEST'); ready.start(); }
    }
    Timer {
        id:ready; interval:300
        onTriggered: {
            if (!check(page.current && page.current.surface==='図書館' && root.analyses===1,'dictionary precedes status request')) return;
            migaku.analyzed(-1,JSON.stringify({text:page.sentence,spans:[{start:4,end:6,surface:'蛞蝓',status:'UNKNOWN'}]}));
            if (!check(page.unknownRanges.length===0,'stale status ignored')) return;
            migaku.analyzed(page.scanRequestId,JSON.stringify({text:page.sentence,spans:[
                {start:0,end:3,surface:'図書館',status:'KNOWN'}, {start:4,end:6,surface:'蛞蝓',status:'UNKNOWN'},
                {start:0,end:2,surface:'wrong',status:'UNKNOWN'}]}));
            if (!check(page.unknownRanges.length===1 && page.unknownRanges[0].start===4,'unknown spans filtered')) return;
            gbKey.foreKeyPress();
            if (!check(root.sent.length===0,'single B does not send')) return;
            second.start();
        }
    }
    Timer {
        id:second; interval:100
        onTriggered: {
            gbKey.foreKeyPress();
            if (!check(root.sent.length===1,'double B sends once')) return;
            root.payload=JSON.parse(root.sent[0].payload);
            if (!check(root.payload.focus_word==='図書館' && root.payload.focus_start===0 && root.payload.focus_end===3 &&
                root.payload.sentence===page.sentence && Object.keys(root.payload).length===5,'minimal selected snapshot')) return;
            pair();
            if (!check(root.sent.length===1,'in-flight double press deduped')) return;
            var key=root.sent[0].key;
            migaku.ingestionFailed(key,'Will retry',true);
            page.flushOutbox();
            if (!check(root.sent.length===2 && root.sent[1].key===key,'retry uses durable key')) return;
            migaku.ingested(key,'job-1','queued');
            pair();
            if (!check(root.sent.length===2,'accepted snapshot deduped')) return;
            migaku.jobStatus(key,'failed','ingestion_dictionary_empty');
            var retained=Lookup.sentIngestion('');
            if (!check(retained && retained.key===key && retained.state==='attention' && retained.job==='job-1' &&
                retained.error==='ingestion_dictionary_empty' && page.migakuNotice.indexOf('no definition')>=0,'failed job retains details and remains observable')) return;
            migaku.jobStatus(key,'synced','');
            if (!check(Lookup.sentIngestion('')===null && page.migakuNotice.indexOf('Created')===0,'recovered job completes without resubmission')) return;
            gbKey.foreKeyPress(); gbKey.volumeUpKeyPress(); gbKey.foreKeyPress();
            if (!check(root.sent.length===2,'selection change disarms B')) return;
            page.resetB(); migaku.bRepeat=true; pair(); migaku.bRepeat=false;
            if (!check(root.sent.length===2,'held B ignored')) return;
            gbKey.scanKeyPress(); pair();
            if (!check(root.sent.length===2 && page.unknownRanges.length===0,'scanning disarms B and clears status')) return;
            cleanup(); console.log('TRANSLATEPEN_MIGAKU_PASS double B, snapshots, retry idempotency, unknown spans and lookup priority'); Qt.quit();
        }
    }
    Timer { interval:8000; running:true; onTriggered: { cleanup();console.log('TRANSLATEPEN_MIGAKU_FAIL timeout');Qt.quit(); } }
}
