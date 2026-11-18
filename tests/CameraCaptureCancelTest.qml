import QtQuick 2.12
import TranslatePen.Native 1.0
Item {
    id:root
    property bool cancelled:false
    CameraBridge {
        id:camera
        onCaptured:{console.log('TRANSLATEPEN_CAPTURE_CANCEL_FAIL unexpected image');Qt.quit();}
        onFailed:{
            if (!root.cancelled || busy || photoPath(key)!=='') console.log('TRANSLATEPEN_CAPTURE_CANCEL_FAIL wrong state');
            else console.log('TRANSLATEPEN_CAPTURE_CANCEL_PASS cancellation during running capture');
            Qt.quit();
        }
    }
    Timer {interval:100;running:true;onTriggered:camera.capture('native-capture-cancel')}
    Timer {interval:4700;running:true;onTriggered:{root.cancelled=true;camera.cancel();}}
    Timer {interval:10000;running:true;onTriggered:{console.log('TRANSLATEPEN_CAPTURE_CANCEL_FAIL deadline');Qt.quit();}}
}
