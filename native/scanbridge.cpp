#include "scanbridge.h"
#include <QElapsedTimer>
#include <QCryptographicHash>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaObject>
#include <QNetworkRequest>
#include <cstring>

namespace {
// V2.2.83, checksum-locked original 606ba418... and our home/QML metadata patch.
// The vendor executable has no dynamic exports for these native methods.
template<class Function> Function native(quintptr address) {
    return reinterpret_cast<Function>(address);
}
using CenterCall = void (*)(void *);
const char *const scanPath = "/mnt/sdcard/cache/linebmp.bmp";

void clearPending(QObject *center) {
    auto bytes = reinterpret_cast<unsigned char *>(center);
    // The native timer is a member, not a QObject child. Its address was verified
    // inside the live vendor process and is specific to this firmware layout.
    reinterpret_cast<QTimer *>(bytes + 0x68)->stop();
    native<CenterCall>(0x4308a8)(center); // Clear_stJointImages; frees/reset image set.
    *reinterpret_cast<int *>(bytes + 20) = 0; // Native multiline scan count.
    reinterpret_cast<QString *>(bytes + 0x48)->clear(); // Preliminary OCR text.
}

class ImagePathMode {
public:
    explicit ImagePathMode(QObject *center) : m_center(center) {
        m_status = native<void *(*)()>(0x4e82a0)();
        m_connected = native<int (*)(void *)>(0x4e8308)(m_status);
        auto bytes = reinterpret_cast<unsigned char *>(center);
        m_dns = bytes[1152];
        std::memcpy(m_modes, bytes + 17, sizeof(m_modes));
        // These flags guarantee scan-stop only schedules a finalizer. The
        // connected-phone/edit modes would dispatch cloud OCR synchronously.
        bytes[17] = 1; // Scanread.
        bytes[18] = 0; // inConnectAPP.
        bytes[19] = 0; // inEdit.
        // This updates only the vendor's logical network flags, not Wi-Fi radio
        // state. Force its image-producing path even when WAN/DNS is unavailable.
        native<void (*)(void *, bool)>(0x431f08)(center, true);
    }
    ~ImagePathMode() {
        *reinterpret_cast<int *>(reinterpret_cast<unsigned char *>(m_status) + 20) = m_connected;
        auto bytes = reinterpret_cast<unsigned char *>(m_center);
        bytes[1152] = m_dns;
        std::memcpy(bytes + 17, m_modes, sizeof(m_modes));
    }
private:
    QObject *m_center;
    void *m_status;
    int m_connected;
    unsigned char m_dns;
    unsigned char m_modes[3];
};
}

ScanBridge::ScanBridge(QObject *parent) : QObject(parent) {
    m_timeout.setSingleShot(true);
    m_timeout.setInterval(4000);
    connect(&m_timeout, &QTimer::timeout, this, [this]() {
        m_timedOut = true;
        if (m_reply) m_reply->abort();
    });
}
ScanBridge::~ScanBridge() { cancel(); }

bool ScanBridge::validCenter(QObject *center) {
    if (!center || std::strcmp(center->metaObject()->className(), "CommonCenter")) return false;
#if defined(__aarch64__)
    // Verify all native instructions once. Home/QRC and Qt metadata patches are
    // outside .text, so production and temporary verification launchers match.
    static const bool compatible = []() {
        QFile executable(QStringLiteral("/proc/self/exe"));
        if (!executable.open(QIODevice::ReadOnly) || !executable.seek(130496)) return false;
        auto code = executable.read(1481676);
        return code.size() == 1481676 && QCryptographicHash::hash(code, QCryptographicHash::Sha256).toHex() ==
            "80cf660cd95cc924cc516c435713a953bdfaaa73ccbd425510b110d3a1dc864d";
    }();
    if (!compatible) return false;
    // Check mapped code as well, before touching native object offsets.
    const unsigned char start[] = {0x02,0x18,0x40,0xf9,0x62,0x00,0x00,0xb4};
    const unsigned char stop[] = {0xfd,0x7b,0xa1,0xa9,0x02,0x20,0x80,0xd2};
    return !std::memcmp(reinterpret_cast<void *>(0x4321b8), start, sizeof(start)) &&
           !std::memcmp(reinterpret_cast<void *>(0x439d58), stop, sizeof(stop));
#else
    return false;
#endif
}

bool ScanBridge::beginScan(QObject *center) {
    cancel();
    if (!validCenter(center)) return false;
    clearPending(center);
    // Empty/bad scans must not reuse a BMP from an earlier scan.
    if (QFile::exists(scanPath) && !QFile::remove(scanPath)) return false;
    ImagePathMode mode(center);
    native<CenterCall>(0x4321b8)(center);
    return true;
}

void ScanBridge::endScan(QObject *center, int requestId) {
    if (!validCenter(center)) {
        emit failed(requestId, QStringLiteral("Scanner firmware is not supported."));
        return;
    }
    QElapsedTimer stopped;
    stopped.start();
    {
        ImagePathMode mode(center);
        native<CenterCall>(0x439d58)(center);
        // Scanread + !inEdit + !inConnectAPP schedules the vendor finalizer.
        // Stop it synchronously before returning to Qt's event loop; no cloud
        // dispatch is made. Its line BMP has already been written by scan-stop.
        clearPending(center);
    }
    QFile file(scanPath);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 2000000) {
        emit failed(requestId, QStringLiteral("No scan image. Please scan again."));
        return;
    }
    QByteArray data = file.readAll();
    file.close();
    if (!data.startsWith("BM") || data.size() < 54) {
        emit failed(requestId, QStringLiteral("No readable scan. Please scan again."));
        return;
    }
    emit captureStopped(requestId, stopped.elapsed(), data.size());
    submit(data, requestId);
}

void ScanBridge::recognizeFile(const QString &path, int requestId) {
    cancel();
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 2000000) {
        emit failed(requestId, QStringLiteral("Could not read the scan image."));
        return;
    }
    submit(file.readAll(), requestId);
}

void ScanBridge::cancel() {
    m_timeout.stop();
    auto reply = m_reply;
    m_reply = nullptr;
    if (reply) { reply->abort(); reply->deleteLater(); }
}

void ScanBridge::submit(const QByteArray &data, int requestId) {
    cancel();
    QNetworkRequest request(m_endpoint);
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("image/bmp"));
    // Do not follow an HTTP redirect to an unexpected server.
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    auto reply = m_network.post(request, data);
    m_reply = reply;
    m_timedOut = false;
    auto clock = QElapsedTimer();
    clock.start();
    m_timeout.start();
    connect(reply, &QNetworkReply::finished, this, [this, reply, requestId, clock]() {
        if (reply != m_reply) { reply->deleteLater(); return; }
        m_timeout.stop();
        m_reply = nullptr;
        int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        auto document = QJsonDocument::fromJson(reply->readAll());
        auto result = document.object();
        if (reply->error() != QNetworkReply::NoError || status != 200) {
            QString message = m_timedOut ? QStringLiteral("Home OCR timed out. Check Wi-Fi and the server.") :
                status == 429 ? QStringLiteral("Home OCR is busy. Please scan again.") :
                status == 400 || status == 413 ? QStringLiteral("Could not read this scan. Try a shorter line.") :
                QStringLiteral("Home OCR unavailable. Check Wi-Fi and the server.");
            emit failed(requestId, message);
        } else if (document.isNull() || !result.value("text").isString()) {
            emit failed(requestId, QStringLiteral("Home OCR returned an invalid result."));
        } else {
            emit recognized(requestId, result.value("text").toString(), clock.elapsed(),
                            result.value("server_ms").toDouble());
        }
        reply->deleteLater();
    });
}
