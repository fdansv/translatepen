#pragma once
#include <QObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QPointer>
#include <QTimer>
#include <QUrl>

class MigakuBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool configured READ configured CONSTANT)
    Q_PROPERTY(bool bRepeat READ bRepeat)
    Q_PROPERTY(QUrl endpoint READ endpoint WRITE setEndpoint)
public:
    explicit MigakuBridge(QObject *parent = nullptr);
    ~MigakuBridge() override;
    bool configured() const { return !m_token.isEmpty() && m_endpoint.isValid(); }
    bool bRepeat() const { return m_repeat; }
    QUrl endpoint() const { return m_endpoint; }
    void setEndpoint(const QUrl &url) { m_endpoint = url; }
    Q_INVOKABLE void analyze(QString text, int requestId);
    Q_INVOKABLE void ingest(QString payload, QString key);
    Q_INVOKABLE void watchJob(QString jobId, QString key);
    Q_INVOKABLE void markKnown(QString payload, int requestId);
    Q_INVOKABLE void cancelAnalysis();
signals:
    void analyzed(int requestId, QString response);
    void analysisFailed(int requestId);
    void ingested(QString key, QString jobId, QString state);
    void ingestionFailed(QString key, QString explanation, bool retryable);
    void jobStatus(QString key, QString state, QString error);
    void markedKnown(int requestId, QString response);
    void knownFailed(int requestId, QString explanation);
private:
    bool eventFilter(QObject *object, QEvent *event) override;
    QNetworkRequest request(QString route) const;
    QUrl m_endpoint;
    QByteArray m_token;
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_analysis, m_ingestion, m_poll, m_known;
    bool m_repeat = false;
};
