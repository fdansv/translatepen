#pragma once
#include <QObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QPointer>
#include <QTimer>
#include <QUrl>

class ScanBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(QUrl endpoint READ endpoint WRITE setEndpoint)
public:
    explicit ScanBridge(QObject *parent = nullptr);
    ~ScanBridge() override;
    QUrl endpoint() const { return m_endpoint; }
    void setEndpoint(const QUrl &url) { m_endpoint = url; }
    Q_INVOKABLE bool beginScan(QObject *center);
    Q_INVOKABLE void endScan(QObject *center, int requestId);
    Q_INVOKABLE void recognizeFile(const QString &path, int requestId);
    Q_INVOKABLE void cancel();
signals:
    void recognized(int requestId, QString text, double roundtripMs, double serverMs);
    void failed(int requestId, QString explanation);
    void captureStopped(int requestId, double durationMs, int imageBytes);
private:
    bool validCenter(QObject *center);
    void submit(const QByteArray &data, int requestId);
    QUrl m_endpoint { QStringLiteral("http://192.168.8.199:8193/ocr") };
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_reply;
    QTimer m_timeout;
    bool m_timedOut = false;
};
