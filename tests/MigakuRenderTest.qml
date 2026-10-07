import QtQuick 2.12
import "../app"
Rectangle {
    id:root
    width:800; height:480; color:'black'
    Japanese { id:page; standalone:true }
    Timer {
        interval:500; running:true
        onTriggered: {
            page.acceptScan('昨日、図書館で蛞蝓を見ました。今日は未知の言葉を読みました。');
            ready.start();
        }
    }
    Timer {
        id:ready; interval:400
        onTriggered: {
            page.lookupAt(7);
            page.unknownRanges=[{start:7,end:9},{start:18,end:20}];
            page.migakuNotice='Vol − / +: previous / next · B twice: Migaku';
            capture.start();
        }
    }
    Timer {
        id:capture; interval:300
        onTriggered:root.grabToImage(function(result) {
            console.log('TRANSLATEPEN_MIGAKU_RENDER '+result.saveToFile('/tmp/translatepen-migaku-page.png')); Qt.quit();
        })
    }
}
