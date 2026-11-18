import QtQuick 2.12
import TranslatePen.Native 1.0
Item {
    id:root
    property int errors:0
    CameraBridge {id:camera}
    MigakuBridge {
        id:service; endpoint:'http://127.0.0.1:18770'
        onIngested: {
            if (key!=='native-fixture' || jobId!=='photo-test-job') {root.fail('wrong key');return;}
            service.ingestPhoto('{}','wrong-key',camera.photoPath('native-fixture'));
            service.ingestPhoto('{}','missing','/missing.jpg');
            if (root.errors!==2) {root.fail('missing/path mismatch not rejected');return;}
            console.log('TRANSLATEPEN_PHOTO_UPLOAD_PASS native JPEG envelope and file validation');Qt.quit();
        }
        onIngestionFailed: {
            if (key==='native-fixture' || retryable) root.fail(explanation);
            else root.errors++;
        }
    }
    function fail(reason) {console.log('TRANSLATEPEN_PHOTO_UPLOAD_FAIL '+reason);Qt.quit();}
    Timer {interval:100;running:true;onTriggered:service.ingestPhoto(JSON.stringify({language:'ja',sentence:'図書館',focus_word:'図書館',focus_start:0,focus_end:3}),'native-fixture',camera.photoPath('native-fixture'))}
    Timer {interval:12000;running:true;onTriggered:root.fail('deadline')}
}
