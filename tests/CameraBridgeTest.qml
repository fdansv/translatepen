import QtQuick 2.12
import TranslatePen.Native 1.0
Item {
    id:root
    property double began:0
    property int ticks:0
    property int phase:0
    CameraBridge {
        id:camera
        onCaptured: {
            if (!root.check(key==='native-fixture' && path.length>0 && Date.now()-root.began>=3990 && root.ticks>25,'four second nonblocking countdown'))return;
            if (!root.check(!busy && countdown===0,'capture finishes'))return;
            phase=1;camera.capture('native-cancel');cancelTimer.start();
        }
        onFailed: {
            if (!root.check(phase===1 && key==='native-cancel' && camera.photoPath(key)==='','cancel keeps no partial jpg'))return;
            console.log('TRANSLATEPEN_CAMERA_PASS fixture encoded on pen, four seconds, responsive timer, cancel');Qt.quit();
        }
    }
    function check(ok,reason) {if(!ok){console.log('TRANSLATEPEN_CAMERA_FAIL '+reason);Qt.quit();}return ok;}
    Timer {interval:100;running:true;repeat:true;onTriggered:root.ticks++}
    Timer {interval:100;running:true;onTriggered:{camera.recoverFlash();root.began=Date.now();camera.capture('native-fixture');root.check(camera.busy && camera.countdown===4,'countdown starts');}}
    Timer {id:cancelTimer;interval:150;onTriggered:camera.cancel()}
    Timer {interval:14000;running:true;onTriggered:{console.log('TRANSLATEPEN_CAMERA_FAIL deadline');Qt.quit();}}
}
