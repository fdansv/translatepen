import QtQuick 2.12
import "../app"
Rectangle {
    id:root; width:800; height:480; color:'black'
    Japanese { id:page; standalone:true; serverOnline:false }
    function pair() { page.pressB(); page.firstBAt=Date.now()-100; page.pressB(); }
    Timer {
        interval:300; running:true
        onTriggered: {
            page.acceptScan('昨日、図書館で日本語を勉強しました。');
            page.lookupAt(4); pair(); page.nextWord(); pair(); page.queueVisible=true; capture.start();
        }
    }
    Timer {
        id:capture; interval:400
        onTriggered:root.grabToImage(function(result) {
            console.log('TRANSLATEPEN_OFFLINE_QUEUE_RENDER '+result.saveToFile('/tmp/translatepen-offline-queue.png')); Qt.quit();
        })
    }
}
