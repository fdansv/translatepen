import QtQuick 2.12
import "../app"
Rectangle {
    id:root; width:800; height:480; color:'black'
    property int phase:0
    QtObject {
        id:camera
        property bool busy:false
        property int countdown:4
        signal captured(string key,string path)
        signal failed(string key,string explanation)
        function cancel() {busy=false;}
        function recoverFlash() {}
        function photoPath(key) {return '';}
        function removePhoto(key) {return true;}
        function capture(key) {}
    }
    Japanese {id:page;standalone:true;serverOnline:false;cameraBridge:camera;mangaMode:true}
    Timer {interval:300;running:true;onTriggered:{page.mangaMode=true;page.acceptScan('漫画の写真をカードに保存する。');page.lookupAt(0);capture.start();}}
    Timer {
        id:capture;interval:400
        onTriggered:root.grabToImage(function(result) {
            console.log('TRANSLATEPEN_MANGA_RENDER '+result.saveToFile('/tmp/translatepen-manga-'+root.phase+'.png'));
            if (root.phase===0) {root.phase=1;camera.busy=true;capture.start();}
            else Qt.quit();
        })
    }
}
