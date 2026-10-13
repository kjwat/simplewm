import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    // Presentation is transparent by default and Slide deliberately occupies
    // only its content area.  Cover the entire QQuickWidget so the installer
    // never exposes Qt's white base palette around a dark slide.
    Rectangle {
        anchors.fill: parent
        color: "#000000"
        z: -100
    }

    Timer {
        interval: 5000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#000000"
            Text {
                anchors.centerIn: parent
                width: parent.width * 0.8
                color: "#FFFFFF"
                font.family: "Ubuntu Sans"
                font.pixelSize: 26
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "SIMPLEOS\n\nThe writing system"
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#000000"
            Text {
                anchors.centerIn: parent
                width: parent.width * 0.8
                color: "#92A58E"
                font.family: "Ubuntu Sans"
                font.pixelSize: 22
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "Debian 13 + Liquorix underneath.\nSimpleWM: a quiet Wayland desk for writers.\nNo bar. Soft fonts. Room to think."
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#000000"
            Text {
                anchors.centerIn: parent
                width: parent.width * 0.8
                color: "#FFFFFF"
                font.family: "Ubuntu Sans"
                font.pixelSize: 22
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "After reboot, sign in and SimpleWM opens.\nWindows+S: apps. Windows+Enter: terminal.\nWindows+A: Writer. Windows+Q: sound.\nPrint: select and copy a screenshot.\nCtrl+Up: maximize. Ctrl+Down: restore.\nWindows+F1: the keys. simpleupdate: stay current."
            }
        }
    }

    function onActivate() { presentation.currentSlide = 0 }
    function onLeave() { }
}
