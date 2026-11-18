import QtQuick 2.12
import TranslatePen.Native 1.0
Item {
    id:root
    CameraBridge {
        id:camera
        onCaptured: {console.log('TRANSLATEPEN_CAMERA_FAILURE_FAIL unexpected success');Qt.quit();}
        onFailed: {
            if (busy || photoPath(key)!=='' || explanation.length<5) console.log('TRANSLATEPEN_CAMERA_FAILURE_FAIL state');
            else console.log('TRANSLATEPEN_CAMERA_FAILURE_PASS failure retained for retake, no partial photo');
            Qt.quit();
        }
    }
    Timer {interval:100;running:true;onTriggered:{camera.recoverFlash();camera.capture('native-failure');}}
    Timer {interval:16000;running:true;onTriggered:{console.log('TRANSLATEPEN_CAMERA_FAILURE_FAIL deadline');Qt.quit();}}
}
