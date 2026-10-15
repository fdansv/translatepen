import QtQuick 2.12
import "../app"
Item {
    id:root
    width:800; height:480
    property int requests:0
    property int firstRequest:0
    MockMigaku {
        id:migaku
        function translate(text,id) { root.requests++; }
    }
    Japanese { id:page; standalone:true; migakuBridge:migaku }
    function check(ok,reason) { if (!ok) throw new Error(reason); }
    Timer {
        interval:300; running:true
        onTriggered: {
            page.acceptScan('図書館で本を読みました。');
            page.nextWord(); // Navigation before the first-lookup timer must still request translation.
            first.start();
        }
    }
    Timer {
        id:first; interval:300
        onTriggered: {
            try {
                check(page.current && page.current.surface==='図書館','definition available while translation pending');
                check(page.translating && root.requests===1,'one translation request for whole scan');
                root.firstRequest=page.translationRequestId;
                migaku.translated(root.firstRequest-1,JSON.stringify({text:page.sentence,translation:'stale'}));
                check(!page.translation && page.translating,'stale response ignored');
                migaku.translated(root.firstRequest,JSON.stringify({text:page.sentence,translation:'I read a book at the library.'}));
                check(page.translation==='I read a book at the library.' && !page.translating,'matching translation shown');
                page.nextWord(); page.previousWord();
                check(root.requests===1 && !!page.translation,'word navigation preserves sentence translation');
                page.acceptScan('日本語を勉強しました。'); second.start();
                check(!page.translation,'new scan clears old translation');
            } catch(error) { console.log('TRANSLATEPEN_TRANSLATION_FAIL '+error); Qt.quit(); }
        }
    }
    Timer {
        id:second; interval:300
        onTriggered: {
            try {
                check(root.requests===2 && page.translating,'new scan starts new translation');
                migaku.translated(root.firstRequest,JSON.stringify({text:'図書館で本を読みました。',translation:'old sentence'}));
                check(!page.translation && page.translating,'previous scan cannot replace current translation');
                migaku.translated(page.translationRequestId,JSON.stringify({text:'wrong sentence',translation:'wrong'}));
                check(!page.translation && !page.translating && !!page.translationNotice,'mismatched sentence rejected');
                page.translateSentence();
                migaku.translationFailed(page.translationRequestId,'Translation unavailable. Tap to retry.');
                check(!page.translating && !!page.translationNotice && !!page.current,'failure leaves dictionary usable');
                page.translateSentence();
                migaku.translated(page.translationRequestId,JSON.stringify({text:page.sentence,translation:'I studied Japanese.'}));
                check(page.translation==='I studied Japanese.','retry succeeds');
                page.acceptScan('');
                check(!page.translation && !page.translating,'empty scan clears translation');
                console.log('TRANSLATEPEN_TRANSLATION_PASS lookup priority, scan snapshots, navigation, failure and retry');
            } catch(error) { console.log('TRANSLATEPEN_TRANSLATION_FAIL '+error); }
            Qt.quit();
        }
    }
    Timer { interval:5000; running:true; onTriggered: { console.log('TRANSLATEPEN_TRANSLATION_FAIL timeout'); Qt.quit(); } }
}
