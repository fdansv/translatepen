#include "scanbridge.h"
#include "migakubridge.h"
#include <QQmlExtensionPlugin>
#include <qqml.h>

class TranslatePenPlugin : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID "org.qt-project.Qt.QQmlExtensionInterface/1.0")
public:
    void registerTypes(const char *uri) override {
        qmlRegisterType<ScanBridge>(uri, 1, 0, "ScanBridge");
        qmlRegisterType<MigakuBridge>(uri, 1, 0, "MigakuBridge");
    }
};

#include "plugin.moc"
