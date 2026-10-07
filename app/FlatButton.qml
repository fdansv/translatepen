import QtQuick 2.12
import QtQuick.Controls 2.12
Button {
    id:control
    background: Rectangle {
        color: control.down ? '#346053' : '#243e49'
        border.color: control.enabled ? '#45606b' : '#2c3c44'
        radius:6
    }
    contentItem: Text {
        text:control.text; font:control.font
        color:control.enabled ? '#e1f6ed' : '#7e949f'
        horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter
    }
}
