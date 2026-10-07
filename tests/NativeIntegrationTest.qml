// Page-level scan lifecycle tests; native capture is verified in the live app.
import QtQuick 2.12
import "../app"
Rectangle {
    id:root
    width:800; height:480; color:'black'
    property var calls: []
    QtObject {
        id:gbKey
        signal scanKeyPress()
        signal scanKeyRelease()
        signal foreKeyPress()
        signal volumeUpKeyPress()
        signal volumeDownKeyPress()
        signal circularKeyPress()
    }
    QtObject {
        id:statusbar
        property bool visible:true
        property string cur_module_name:'Jp'
    }
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
        id:bridge
        signal recognized(int requestId, string text, real roundtripMs, real serverMs)
        signal failed(int requestId, string explanation)
        signal captureStopped(int requestId, real durationMs, int imageBytes)
        function beginScan(center) { root.calls.push('start'); return true; }
        function endScan(center, requestId) { root.calls.push('stop'); }
        function cancel() { root.calls.push('cancel'); }
    }
    Japanese { id:page; scannerBridge:bridge }
    function check(ok, reason) {
        if (!ok) { console.log('TRANSLATEPEN_NATIVE_FAIL '+reason); Qt.quit(); }
        return ok;
    }
    Timer {
        interval:300; running:true
        onTriggered: {
            gbKey.scanKeyPress(); gbKey.scanKeyRelease();
            if (!check(root.calls.join(',')==='start,stop' && page.recognizing, 'capture lifecycle')) return;
            bridge.recognized(0,'stale response',80,60);
            if (!check(page.sentence==='', 'stale response rejected')) return;
            bridge.recognized(1,'図書館、日本語。',80,60);
            checkWords.start();
        }
    }
    Timer {
        id:checkWords; interval:250
        onTriggered: {
            if (!check(page.current && page.current.surface==='図書館', 'first word')) return;
            gbKey.foreKeyPress();
            if (!check(page.current && page.current.surface==='図書館', 'B no longer navigates')) return;
            gbKey.volumeUpKeyPress();
            if (!check(page.current && page.current.surface==='日本語', 'volume up advances')) return;
            gbKey.volumeDownKeyPress();
            if (!check(page.current && page.current.surface==='図書館', 'volume down goes back')) return;
            gbKey.volumeDownKeyPress();
            if (!check(page.current && page.current.surface==='日本語', 'volume down wraps')) return;
            gbKey.volumeUpKeyPress();
            if (!check(page.current && page.current.surface==='図書館', 'volume up wraps')) return;
            gbKey.scanKeyPress();
            bridge.recognized(1,'old request',80,60);
            if (!check(page.sentence==='図書館、日本語。', 'result ignored during new scan')) return;
            gbKey.scanKeyRelease();
            bridge.failed(1,'old failure');
            if (!check(page.recognizing, 'stale failure rejected')) return;
            bridge.failed(2,'Home OCR unavailable.');
            if (!check(!page.recognizing && page.notice==='Home OCR unavailable.', 'network failure shown')) return;
            page.standalone=true;
            page.goBack();
            bridge.recognized(2,'late response',80,60);
            if (!check(root.calls[root.calls.length-1]==='cancel' && page.sentence==='図書館、日本語。', 'exit cancellation')) return;
            console.log('TRANSLATEPEN_NATIVE_PASS scan lifecycle, stale replies, failures, exit and volume navigation');
            Qt.quit();
        }
    }
    Timer { interval:8000; running:true; onTriggered: { console.log('TRANSLATEPEN_NATIVE_FAIL timeout'); Qt.quit(); } }
}
