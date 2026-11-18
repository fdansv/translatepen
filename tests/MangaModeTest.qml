import QtQuick 2.12
import "../app"
import "../app/Lookup.js" as Lookup
Item {
    id:root; width:800; height:480
    property var page:null
    property var uploads:[]
    property string firstKey:''
    property int shots:0
    property var files:({})
    property var removed:[]
    QtObject {
        id:camera
        property bool busy:false
        property int countdown:0
        property string key:''
        signal captured(string key,string path)
        signal failed(string key,string explanation)
        function capture(value) {key=value; busy=true; countdown=4; root.shots++;}
        function cancel() {if (!busy)return; busy=false; countdown=0; failed(key,'Photo cancelled; word saved.');}
        function photoPath(value) {return root.files[value] || '';}
        function removePhoto(value) {root.removed.push(value);delete root.files[value];return true;}
        function recoverFlash() {}
    }
    QtObject {
        id:service
        property bool online:false
        property bool photoSupported:true
        property bool bRepeat:false
        signal analyzed(int requestId,string response)
        signal analysisFailed(int requestId)
        signal ingested(string key,string jobId,string state)
        signal ingestionFailed(string key,string explanation,bool retryable)
        signal jobStatus(string key,string state,string error)
        signal markedKnown(int requestId,string response)
        signal knownFailed(int requestId,string explanation)
        function analyze(text,id) {}
        function cancelAnalysis() {}
        function checkConnection() {}
        function markKnown(payload,id) {}
        function watchJob(job,key) {}
        function ingest(payload,key) {root.uploads.push({key:key,photo:''});ingested(key,'job-text','queued');}
        function ingestPhoto(payload,key,path) {root.uploads.push({key:key,photo:path});ingested(key,'job-photo','queued');}
    }
    Component { id:factory; Japanese {standalone:true;migakuBridge:service;cameraBridge:camera} }
    function fail(reason) {console.log('TRANSLATEPEN_MANGA_FAIL '+reason);Qt.quit();}
    function check(ok,reason) {if (!ok)fail(reason);return ok;}
    function pair() {page.pressB();page.firstBAt=Date.now()-100;page.pressB();}
    Timer {
        interval:200; running:true
        onTriggered: {
            Lookup.initialize('/userdata/translatepen');
            page=factory.createObject(root);
            if (!check(!page.mangaMode,'default off'))return;
            page.mangaMode=true;Lookup.setSetting('manga','1');
            page.acceptScan('図書館、日本語。MANGA_TEST');page.lookupAt(0);pair();
            firstKey=camera.key;
            if (!check(camera.busy && camera.countdown===4 && Lookup.queueSummary().photo===1 && !Lookup.pendingIngestion(),'reserved word waits for photo'))return;
            var selected=page.current.surface;page.nextWord();pair();page.startScan();
            if (!check(shots===1 && page.current.surface===selected && !page.scanning,'countdown blocks navigation scans and repeated B'))return;
            camera.cancel();
            if (!check(Lookup.queueSummary().photo===1 && Lookup.queueEntries()[0].error.length>0,'cancel retains word'))return;
            page.retakePhoto(firstKey);
            files[firstKey]='/test/'+firstKey+'.jpg';camera.busy=false;camera.countdown=0;camera.captured(firstKey,files[firstKey]);
            if (!check(Lookup.pendingIngestion().photo===files[firstKey] && uploads.length===0,'offline photo attached before sending'))return;
            pair();
            if (!check(shots===2 && Lookup.queueSummary().pending===1,'same selection dedupes without taking second photo'))return;
            service.online=true;page.flushOutbox();
            if (!check(uploads.length===1 && uploads[0].key===firstKey && uploads[0].photo===files[firstKey],'online upload includes same photo and key'))return;
            service.jobStatus(firstKey,'synced','');
            page.cleanPhotos();
            if (!check(removed.length===0,'newly synced photo retained'))return;
            Lookup.db.transaction(function(tx){tx.executeSql('UPDATE migaku_outbox SET photo_done=? WHERE key=?',[Date.now()-8*86400000,firstKey]);});
            page.cleanPhotos();
            if (!check(removed.length===1 && removed[0]===firstKey,'only old confirmed photo cleaned'))return;
            service.online=false;page.nextWord();pair();
            camera.cancel();
            var key=camera.key;files[key]='/test/'+key+'.jpg';
            page.destroy(); page=null;
            restart.start();
        }
    }
    Timer {
        id:restart;interval:100
        onTriggered: {
            page=factory.createObject(root);
            if (!check(page.mangaMode && Lookup.queueSummary().photo===0 && Lookup.pendingIngestion().photo===files[camera.key],'mode persists and interrupted saved image recovered'))return;
            page.mangaMode=false;
            page.acceptScan('食べました。TEXT_TEST');page.lookupAt(0);pair();
            if (!check(shots===3 && Lookup.queueSummary().pending===2,'mode off uses original text flow'))return;
            page.mangaMode=true; service.photoSupported=false;
            page.acceptScan('本を読みました。TEXT_ONLY_SERVER_TEST');page.lookupAt(0);pair();
            if (!check(shots===3 && Lookup.queueSummary().photo===0,'text-only server cannot trigger capture'))return;
            service.online=true; page.flushOutbox();
            if (!check(uploads.length===2 && !uploads[1].photo,'text sends while saved photo waits for compatible backend'))return;
            console.log('TRANSLATEPEN_MANGA_PASS offline photo queue, cancel, retake, no early upload, stable keys, recovery, preferences, retention and normal flow');Qt.quit();
        }
    }
    Timer {interval:8000;running:true;onTriggered:root.fail('deadline')}
}
