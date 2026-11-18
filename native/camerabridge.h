#pragma once
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QLockFile>
class CameraBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(int countdown READ countdown NOTIFY changed)
public:
    explicit CameraBridge(QObject *parent=nullptr);
    ~CameraBridge() override;
    bool busy() const {return !m_key.isEmpty();}
    int countdown() const {return m_countdown;}
    Q_INVOKABLE void capture(QString key);
    Q_INVOKABLE void cancel();
    Q_INVOKABLE QString photoPath(QString key) const;
    Q_INVOKABLE bool removePhoto(QString key);
    Q_INVOKABLE void recoverFlash();
signals:
    void changed();
    void captured(QString key,QString path);
    void failed(QString key,QString explanation);
private:
    void takeFrame();
    void finish(QString error=QString());
    bool restoreLight();
    QString m_directory,m_led,m_helper,m_key,m_prefix,m_previous;
    int m_countdown=0;
    QTimer m_timer;
    QProcess *m_process=nullptr;
    QLockFile *m_lock=nullptr;
};
