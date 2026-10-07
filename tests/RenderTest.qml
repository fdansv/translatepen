import QtQuick 2.12
import "../app"
Rectangle {
    id:root
    width:800; height:480; color:'black'
    Japanese { id:page; standalone:true }
    Timer {
        interval:500; running:true
        onTriggered: { page.acceptScan('昨日、図書館で日本語を勉強しました。'); page.lookupAt(4); capture.start(); }
    }
    Timer {
        id:capture; interval:500
        onTriggered: root.grabToImage(function(result) {
            console.log('TRANSLATEPEN_RENDER '+result.saveToFile('/tmp/translatepen-page.png'));
            Qt.quit();
        })
    }
}
