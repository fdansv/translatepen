import QtQuick 2.12
import "../app"
Item {
    id:root
    width:800; height:480
    property var requests:[]
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
        function analyze(sentence,id) {}
        function cancelAnalysis() {}
        function watchJob(job,key) {}
        function ingest(payload,key) {}
        function markKnown(payload,id) { root.requests.push({payload:JSON.parse(payload),id:id}); }
    }
    Japanese { id:page; standalone:true; migakuBridge:migaku }
    function check(ok,reason) {
        if (!ok) { console.log('TRANSLATEPEN_KNOWN_FAIL '+reason); Qt.quit(); }
        return ok;
    }
    function respond(id) { migaku.markedKnown(id,JSON.stringify({word:{knownStatus:'KNOWN'},synced:true})); }
    function findButton(item) {
        if (item.objectName==='markKnownButton') return item;
        for (var i=0;i<item.children.length;++i) {
            var found=findButton(item.children[i]);
            if (found) return found;
        }
        return null;
    }
    Timer {
        interval:300; running:true
        onTriggered: { page.acceptScan('図書館、蛞蝓。'); ready.start(); }
    }
    Timer {
        id:ready; interval:300
        onTriggered: {
            migaku.analyzed(page.scanRequestId,JSON.stringify({text:page.sentence,spans:[
                {start:0,end:3,surface:'図書館',status:'KNOWN'},{start:4,end:6,surface:'蛞蝓',status:'UNKNOWN'}]}));
            var button=findButton(page);
            if (!check(button && button.text==='Known ✓' && !button.enabled,'known button state')) return;
            button.clicked();
            if (!check(page.currentKnown && root.requests.length===0,'already known cannot be marked again')) return;
            page.nextWord();
            if (!check(button.enabled && button.text==='Mark known','unknown button state')) return;
            button.clicked(); button.clicked();
            if (!check(root.requests.length===1 && page.markingKnown && !button.enabled && button.text==='Marking…' && page.unknownRanges.length===1,'one request and no optimistic underline removal')) return;
            var request=root.requests[0];
            if (!check(request.payload.sentence===page.sentence && request.payload.focus_word==='蛞蝓' &&
                       request.payload.focus_start===4 && request.payload.focus_end===6,'selected snapshot')) return;
            migaku.knownFailed(request.id,'Offline · try again');
            if (!check(!page.markingKnown && !page.currentKnown && button.enabled && page.unknownRanges.length===1,'failure retains unknown state')) return;
            page.markCurrentKnown(); request=root.requests[1]; page.previousWord(); respond(request.id);
            if (!check(page.current.surface==='図書館' && page.migakuNotice==='' && page.unknownRanges.length===0,'late completion affects original word without feedback on new selection')) return;
            page.nextWord();
            if (!check(page.currentKnown && !page.markingKnown,'confirmed original selection known')) return;
            page.wordStatuses=[]; page.unknownRanges=[{start:4,end:6}]; page.markCurrentKnown();
            request=root.requests[2]; page.scanRequestId++; page.acceptScan('蛞蝓。'); respond(request.id);
            if (!check(page.wordStatuses.length===0 && page.unknownRanges.length===0 && !page.markingKnown,'old scan completion ignored')) return;
            console.log('TRANSLATEPEN_KNOWN_PASS known state, snapshots, failures, navigation and stale completions'); Qt.quit();
        }
    }
    Timer { interval:8000; running:true; onTriggered: { console.log('TRANSLATEPEN_KNOWN_FAIL timeout'); Qt.quit(); } }
}
