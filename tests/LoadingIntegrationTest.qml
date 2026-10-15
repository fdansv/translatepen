// Exercise overlapping operations without creating live Migaku cards.
import QtQuick 2.12
import "../app"
import "../app/Lookup.js" as Lookup
Rectangle {
    id:root
    width:800; height:480; color:'black'
    property var sent:[]
    property string firstKey:''
    property string secondKey:''
    property int oldTranslationId:0
    MockMigaku {
        id:migaku
        function ingest(payload,key) { root.sent.push({payload:payload,key:key}); }
    }
    Japanese { id:page; standalone:true; migakuBridge:migaku }
    function find(item,name) {
        if (item.objectName===name) return item;
        for (var i=0;i<item.children.length;++i) {
            var result=find(item.children[i],name);
            if (result) return result;
        }
        return null;
    }
    function check(ok,reason) { if (!ok) throw new Error(reason); }
    function indicator(busy,reason) {
        check(page.loading===busy && find(page,'loadingIndicator').visible===busy,reason);
    }
    function pair() { page.pressB(); page.firstBAt=Date.now()-100; page.pressB(); }
    function cleanup() {
        Lookup.db.transaction(function(tx) {
            tx.executeSql("DELETE FROM migaku_outbox WHERE payload LIKE '%TRANSLATEPEN_LOADING_TEST%'");
        });
    }
    function fail(error) { cleanup(); console.log('TRANSLATEPEN_LOADING_FAIL '+error); Qt.quit(); }
    Timer {
        interval:300; running:true
        onTriggered: {
            try {
                cleanup(); indicator(false,'idle hides indicator');
                page.acceptScan('図書館、蛞蝓。TRANSLATEPEN_LOADING_TEST');
                indicator(true,'lookup is loading immediately'); ready.start();
            } catch(error) { root.fail(error); }
        }
    }
    Timer {
        id:ready; interval:300
        onTriggered: {
            try {
                check(page.current && page.translating && page.analyzing,'local definition remains available');
                indicator(true,'translation and analysis show indicator');
                root.grabToImage(function(result) {
                    console.log('TRANSLATEPEN_LOADING_RENDER '+result.saveToFile('/tmp/translatepen-loading.png'));
                    exercise.start();
                });
            } catch(error) { root.fail(error); }
        }
    }
    Timer {
        id:exercise; interval:50
        onTriggered: {
            try {
                migaku.translated(page.translationRequestId,JSON.stringify({text:page.sentence,translation:'A library and a slug.'}));
                indicator(true,'analysis outlives translation');
                migaku.analyzed(page.scanRequestId,JSON.stringify({text:page.sentence,spans:[]}));
                indicator(false,'all scan work completed');
                pair(); check(root.sent.length===1,'card submission started'); root.firstKey=root.sent[0].key;
                indicator(true,'submitting card shows indicator');
                migaku.ingestionFailed(root.firstKey,'Saved for retry',true);
                indicator(false,'offline queued retry does not spin');
                page.flushOutbox(); indicator(true,'actual retry shows indicator');
                migaku.ingested(root.firstKey,'loading-job-1','queued');
                check(!page.ingesting,'submission completed'); indicator(true,'queued card is still loading');
                page.nextWord(); check(page.activeIngestionKey==='','navigation changed active card');
                indicator(true,'navigation retains background card indicator');
                pair(); root.secondKey=root.sent[root.sent.length-1].key;
                check(root.secondKey!==root.firstKey,'second selection queues separate card');
                migaku.ingested(root.secondKey,'loading-job-2','running');
                migaku.jobStatus(root.firstKey,'created',''); indicator(true,'syncing is still loading');
                migaku.jobStatus(root.firstKey,'synced',''); indicator(true,'another card is still loading');
                migaku.jobStatus(root.secondKey,'blocked','login_required'); indicator(false,'blocked card stops loading');
                migaku.jobStatus(root.secondKey,'running',''); indicator(true,'recovered job resumes loading');
                migaku.jobStatus(root.secondKey,'uncertain','write_unverified'); indicator(false,'uncertain job stops loading');
                migaku.jobStatus(root.secondKey,'created','');
                page.acceptScan('日本語。TRANSLATEPEN_LOADING_TEST'); newScan.start();
            } catch(error) { root.fail(error); }
        }
    }
    Timer {
        id:newScan; interval:300
        onTriggered: {
            try {
                root.oldTranslationId=page.translationRequestId;
                migaku.translationFailed(root.oldTranslationId,'Translation unavailable');
                migaku.analysisFailed(page.scanRequestId);
                indicator(true,'new scan does not hide previous card sync');
                migaku.jobStatus(root.secondKey,'synced',''); indicator(false,'translation failure and synced card stop loading');
                page.translateSentence(); indicator(true,'translation retry starts loading');
                migaku.translationFailed(root.oldTranslationId-1,'stale'); indicator(true,'stale failure cannot hide active translation');
                migaku.translated(page.translationRequestId,JSON.stringify({text:page.sentence,translation:'Japanese.'}));
                indicator(false,'translation retry completes');
                page.markCurrentKnown(); check(page.markingKnown,'known update requested');
                indicator(true,'known update shows indicator');
                migaku.knownFailed(page.knownRequestId,'Update unavailable'); refresh.start();
            } catch(error) { root.fail(error); }
        }
    }
    Timer {
        id:refresh; interval:150
        onTriggered: {
            try {
                indicator(true,'status refresh remains loading');
                migaku.analysisFailed(page.scanRequestId); indicator(false,'status failure stops loading');
                page.recognizing=true; indicator(true,'OCR shows indicator');
                page.recognizing=false; indicator(false,'OCR completion stops loading');
                cleanup();
                console.log('TRANSLATEPEN_LOADING_PASS overlapping operations, card generation and sync, navigation, retry and failures');
                Qt.quit();
            } catch(error) { root.fail(error); }
        }
    }
    Timer { interval:8000; running:true; onTriggered:root.fail('timeout') }
}
