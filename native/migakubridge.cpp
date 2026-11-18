#include "migakubridge.h"
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkRequest>
#include <QCoreApplication>
#include <QKeyEvent>
#include <QFileInfo>
#include <QCryptographicHash>

MigakuBridge::MigakuBridge(QObject *parent) : QObject(parent) {
    QCoreApplication::instance()->installEventFilter(this);
    m_probeTimer.setInterval(20000);
    connect(&m_probeTimer, &QTimer::timeout, this, &MigakuBridge::checkConnection);
    m_probeTimer.start();
    QTimer::singleShot(0,this,&MigakuBridge::checkConnection);
    QFile file(QStringLiteral("/userdata/translatepen/migaku.json"));
    if (!file.open(QIODevice::ReadOnly)) return;
    const auto config = QJsonDocument::fromJson(file.readAll()).object();
    m_endpoint = QUrl(config.value("endpoint").toString());
    m_token = config.value("token").toString().toUtf8();
    if (m_endpoint.scheme() != "http" && m_endpoint.scheme() != "https") m_endpoint = QUrl();
}
bool MigakuBridge::eventFilter(QObject *, QEvent *event) {
    // The vendor emits only a B-press signal. Observe Qt's repeat flag before
    // that signal is dispatched so holding B cannot become a double press.
    if (event->type() == QEvent::KeyPress) m_repeat = static_cast<QKeyEvent *>(event)->isAutoRepeat();
    return false;
}
MigakuBridge::~MigakuBridge() {
    if (m_probe) { m_probe->disconnect(this); m_probe->abort(); }
    cancelAnalysis();
    cancelTranslation();
    if (m_ingestion) m_ingestion->abort();
    if (m_poll) m_poll->abort();
    if (m_known) m_known->abort();
}
void MigakuBridge::setOnline(bool value) {
    if (m_online==value) return;
    m_online=value; emit onlineChanged();
}
void MigakuBridge::setPhotoSupported(bool value) {
    if (m_photoSupported == value) return;
    m_photoSupported = value;
    emit photoSupportedChanged();
}
void MigakuBridge::setEndpoint(const QUrl &url) {
    if (m_endpoint == url) return;
    m_endpoint = url;
    if (m_probe) m_probe->abort();
    setOnline(false);
    setPhotoSupported(false);
}
void MigakuBridge::checkConnection() {
    if (m_probe) return;
    if (!configured()) { setOnline(false); return; }
    auto reply=m_network.get(request("/health"));
    m_probe=reply;
    QTimer::singleShot(2500,reply,[reply]() { if (reply->isRunning()) reply->abort(); });
    connect(reply,&QNetworkReply::finished,this,[this,reply]() {
        m_probe=nullptr;
        auto result=QJsonDocument::fromJson(reply->readAll()).object();
        const bool healthy = reply->error() == QNetworkReply::NoError &&
            reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() == 200 &&
            result.value("service").toString() == "ok";
        if (healthy)
            setPhotoSupported(result.value("card_destination").toString() == "anki" &&
                              result.value("pen_photos").toBool());
        setOnline(healthy);
        reply->deleteLater();
    });
}
QNetworkRequest MigakuBridge::request(QString route) const {
    auto url = m_endpoint;
    url.setPath(url.path() + route);
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    request.setRawHeader("Authorization", "Bearer " + m_token);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    return request;
}
void MigakuBridge::cancelAnalysis() {
    auto reply = m_analysis; m_analysis = nullptr;
    if (reply) { reply->abort(); reply->deleteLater(); }
}
void MigakuBridge::cancelTranslation() {
    auto reply = m_translation; m_translation = nullptr;
    if (reply) { reply->abort(); reply->deleteLater(); }
}
void MigakuBridge::translate(QString text, int requestId) {
    cancelTranslation();
    if (!configured()) {
        emit translationFailed(requestId, QStringLiteral("Configure Migaku to translate scans.")); return;
    }
    QJsonObject input{{"language", "ja"}, {"text", text}};
    auto reply = m_network.post(request("/text/translate"), QJsonDocument(input).toJson(QJsonDocument::Compact));
    m_translation = reply;
    QTimer::singleShot(30000, reply, [reply]() { if (reply->isRunning()) reply->abort(); });
    connect(reply, &QNetworkReply::finished, this, [this, reply, requestId]() {
        if (reply != m_translation) { reply->deleteLater(); return; }
        m_translation = nullptr;
        int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (reply->error() == QNetworkReply::NoError && status == 200)
            emit translated(requestId, QString::fromUtf8(reply->readAll()));
        else emit translationFailed(requestId, status == 401 ?
            QStringLiteral("Migaku credentials need updating.") :
            QStringLiteral("Translation unavailable. Tap to retry."));
        reply->deleteLater();
    });
}
void MigakuBridge::analyze(QString text, int requestId) {
    cancelAnalysis();
    if (!configured()) { emit analysisFailed(requestId); return; }
    QJsonObject input{{"language", "ja"}, {"text", text}};
    auto reply = m_network.post(request("/text/analyze"), QJsonDocument(input).toJson(QJsonDocument::Compact));
    m_analysis = reply;
    QTimer::singleShot(15000, reply, [reply]() { if (reply->isRunning()) reply->abort(); });
    connect(reply, &QNetworkReply::finished, this, [this, reply, requestId]() {
        if (reply != m_analysis) { reply->deleteLater(); return; }
        m_analysis = nullptr;
        if (reply->error() == QNetworkReply::NoError &&
            reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() == 200)
            emit analyzed(requestId, QString::fromUtf8(reply->readAll()));
        else emit analysisFailed(requestId);
        reply->deleteLater();
    });
}
void MigakuBridge::ingest(QString payload, QString key) {
    sendIngestion(payload,key);
}
void MigakuBridge::ingestPhoto(QString payload,QString key,QString path) {
    QFileInfo info(path);
    const auto directory=qEnvironmentVariable("TRANSLATEPEN_PHOTO_DIR","/mnt/sdcard/translatepen/photos");
    if (info.isSymLink() || info.canonicalPath()!=QFileInfo(directory).canonicalFilePath() || info.fileName()!=key+".jpg" || info.size()>400000) {
        emit ingestionFailed(key,"Photo file needs attention; saved on pen.",false);return;
    }
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {emit ingestionFailed(key,"Saved photo is missing; request kept on pen.",false);return;}
    const auto data=file.readAll();
    if (!data.startsWith(QByteArray::fromHex("ffd8")) || !data.endsWith(QByteArray::fromHex("ffd9"))) {
        emit ingestionFailed(key,"Saved photo is invalid; request kept on pen.",false);return;
    }
    auto input=QJsonDocument::fromJson(payload.toUtf8()).object();
    input.insert("photo",QJsonObject{{"sha256",QString::fromLatin1(QCryptographicHash::hash(data,QCryptographicHash::Sha256).toHex())},
                                   {"data",QString::fromLatin1(data.toBase64())}});
    sendIngestion(QString::fromUtf8(QJsonDocument(input).toJson(QJsonDocument::Compact)),key);
}
void MigakuBridge::sendIngestion(QString payload, QString key) {
    if (m_ingestion) return;
    if (!configured()) {
        emit ingestionFailed(key, QStringLiteral("Migaku is not configured."), false); return;
    }
    auto req = request("/ingest");
    req.setRawHeader("Idempotency-Key", key.toUtf8());
    auto reply = m_network.post(req, payload.toUtf8());
    m_ingestion = reply;
    QTimer::singleShot(10000, reply, [reply]() { if (reply->isRunning()) reply->abort(); });
    connect(reply, &QNetworkReply::finished, this, [this, reply, key]() {
        m_ingestion = nullptr;
        int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        auto result = QJsonDocument::fromJson(reply->readAll()).object();
        if (reply->error() == QNetworkReply::NoError && status == 202 && result.value("id").isString())
            emit ingested(key, result.value("id").toString(), result.value("state").toString());
        else {
            bool retryable = status == 0 || status >= 500 || status == 429 || status == 408 || (status == 202);
            if (status==0 || status>=500 || status==401) setOnline(false);
            emit ingestionFailed(key, status == 401 ? QStringLiteral("Migaku credentials need updating.") :
                status == 409 ? QStringLiteral("Migaku request conflicts. Check the API.") :
                retryable ? QStringLiteral("Saved on pen. Will send when connected.") :
                QStringLiteral("Migaku rejected this sentence. Check the API."), retryable);
        }
        reply->deleteLater();
    });
}
void MigakuBridge::watchJob(QString jobId, QString key) {
    if (!configured() || m_poll) return;
    auto reply = m_network.get(request("/jobs/" + jobId));
    m_poll = reply;
    QTimer::singleShot(10000, reply, [reply]() { if (reply->isRunning()) reply->abort(); });
    connect(reply, &QNetworkReply::finished, this, [this, reply, key]() {
        m_poll = nullptr;
        if (reply->error() == QNetworkReply::NoError &&
            reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() == 200) {
            auto result = QJsonDocument::fromJson(reply->readAll()).object();
            if (result.value("state").isString()) emit jobStatus(key, result.value("state").toString(), result.value("error").toString());
        }
        reply->deleteLater();
    });
}
void MigakuBridge::markKnown(QString payload, int requestId) {
    if (m_known) { emit knownFailed(requestId, QStringLiteral("A word update is already running.")); return; }
    if (!configured()) { emit knownFailed(requestId, QStringLiteral("Migaku is not configured.")); return; }
    auto reply = m_network.post(request("/words/known"), payload.toUtf8());
    m_known = reply;
    QTimer::singleShot(20000, reply, [reply]() { if (reply->isRunning()) reply->abort(); });
    connect(reply, &QNetworkReply::finished, this, [this, reply, requestId]() {
        m_known = nullptr;
        int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        auto body = reply->readAll();
        auto result = QJsonDocument::fromJson(body).object();
        if (reply->error() == QNetworkReply::NoError && status == 200 &&
            result.value("word").toObject().value("knownStatus").toString() == "KNOWN")
            emit markedKnown(requestId, QString::fromUtf8(body));
        else emit knownFailed(requestId, status == 401 ? QStringLiteral("Migaku credentials need updating.") :
            status == 422 ? QStringLiteral("Select a single word that Migaku recognizes.") :
            QStringLiteral("Could not confirm known status. Try again."));
        reply->deleteLater();
    });
}
