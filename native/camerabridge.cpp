#include "camerabridge.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSaveFile>
#include <QImage>
#include <QRegularExpression>
#include <QStorageInfo>
#include <QUuid>
#include <QDateTime>

static bool validKey(const QString &key) {return QRegularExpression("^[A-Za-z0-9_-]{1,128}$").match(key).hasMatch();}
static QByteArray readFile(const QString &path) {QFile f(path);return f.open(QIODevice::ReadOnly) ? f.readAll() : QByteArray();}
static bool writeFile(const QString &path,const QByteArray &data) {QFile f(path);return f.open(QIODevice::WriteOnly) && f.write(data)==data.size();}
static void liftDarkPhoto(QImage &image) {
    if (qEnvironmentVariable("TRANSLATEPEN_PHOTO_NORMALIZE","1")=="0") return;
    int histogram[256]={};const int count=image.width()*image.height();
    for (int y=0;y<image.height();++y) for (int x=0;x<image.width();++x) ++histogram[image.constScanLine(y)[x]];
    int low=0,high=255,sum=0;const int lowTarget=qMax(1,count/100),highTarget=qMax(1,count*99/100);
    for (int value=0;value<256;++value) {sum+=histogram[value];if (sum>=lowTarget) {low=value;break;}}
    sum=0;for (int value=0;value<256;++value) {sum+=histogram[value];if (sum>=highTarget) {high=value;break;}}
    // A bounded monotonic tonal adjustment only. Keep well-lit or nearly-flat
    // frames unchanged, rather than stretching sensor noise into fake detail.
    if (high>=128 || high-low<8) return;
    uchar table[256];for (int value=0;value<256;++value) table[value]=uchar(qBound(0,(value-low)*240/(high-low),255));
    for (int y=0;y<image.height();++y) for (int x=0;x<image.width();++x) image.scanLine(y)[x]=table[image.constScanLine(y)[x]];
}
CameraBridge::CameraBridge(QObject *parent):QObject(parent) {
    m_directory=qEnvironmentVariable("TRANSLATEPEN_PHOTO_DIR","/mnt/sdcard/translatepen/photos");
    m_led=qEnvironmentVariable("TRANSLATEPEN_LED_PATH","/sys/class/leds/camera-led/brightness");
    m_helper=qEnvironmentVariable("TRANSLATEPEN_CAPTURE_HELPER","/userdata/translatepen/bin/manga_capture.sh");
    m_timer.setInterval(1000);
    m_timer.setTimerType(Qt::PreciseTimer);
    connect(&m_timer,&QTimer::timeout,this,[this]() {
        if (--m_countdown<=0) {m_timer.stop();emit changed();takeFrame();}
        else emit changed();
    });
}
CameraBridge::~CameraBridge() {cancel();}
QString CameraBridge::photoPath(QString key) const {
    if (!validKey(key)) return QString();
    const auto path=m_directory+"/"+key+".jpg";
    return QFileInfo(path).isFile() && !QFileInfo(path).isSymLink() && QFileInfo(path).size()>0 ? path : QString();
}
bool CameraBridge::removePhoto(QString key) {
    if (!validKey(key) || key==m_key) return false;
    const auto path=m_directory+"/"+key+".jpg";
    return !QFile::exists(path) || (!QFileInfo(path).isSymLink() && QFile::remove(path));
}
bool CameraBridge::restoreLight() {
    if (m_previous.isEmpty()) return true;
    const bool ok=writeFile(m_led,m_previous.toLatin1());
    if (ok) {QFile::remove(m_directory+"/.led-restore");m_previous.clear();}
    return ok;
}
void CameraBridge::recoverFlash() {
    if (busy() || !QDir(m_directory).exists()) return;
    QLockFile lock(m_directory+"/.camera.lock");
    if (!lock.tryLock(0)) return;
    auto old=readFile(m_directory+"/.led-restore").trimmed();
    if (QRegularExpression("^[0-9]{1,3}$").match(QString::fromLatin1(old)).hasMatch()) {
        if (writeFile(m_led,old)) QFile::remove(m_directory+"/.led-restore");
    }
    const auto format=QString::fromLatin1(readFile(m_directory+"/.format-restore").trimmed());
    const auto match=QRegularExpression("^width=([0-9]{1,3}),height=([0-9]{1,3}),pixelformat=(NV21|NV12|YUYV)$").match(format);
    if (match.hasMatch() && match.captured(1).toInt()>=2 && match.captured(1).toInt()<=528 &&
        match.captured(2).toInt()>=2 && match.captured(2).toInt()<=360 &&
        QProcess::execute("timeout",QStringList()<<"2"<<"v4l2-ctl"<<"-d"<<"/dev/video0"<<"--set-fmt-video="+format)==0)
        QFile::remove(m_directory+"/.format-restore");
    const auto exposure=readFile(m_directory+"/.exposure-restore").trimmed();
    const int exposureValue=exposure.toInt();
    if (!exposure.isEmpty() && exposureValue>=4 && exposureValue<=412 &&
        QProcess::execute("timeout",QStringList()<<"2"<<"v4l2-ctl"<<"-d"<<"/dev/video0"<<"--set-ctrl=exposure="+QString::fromLatin1(exposure))==0)
        QFile::remove(m_directory+"/.exposure-restore");
    for (const auto &file:QDir(m_directory).entryInfoList(QStringList()<<".capture-*.raw"<<".capture-*.format",QDir::Files|QDir::Hidden))
        if (file.lastModified().secsTo(QDateTime::currentDateTime())>60) QFile::remove(file.absoluteFilePath());
}
void CameraBridge::capture(QString key) {
    if (busy()) return;
    recoverFlash();
    if (QFile::exists(m_directory+"/.format-restore")) {
        emit failed(key,"Camera settings need recovery. Reopen Anki Pen before taking another photo.");return;
    }
    if (!validKey(key)) {emit failed(key,"Invalid photo request; word saved.");return;}
    const auto existing=photoPath(key);
    if (!existing.isEmpty()) {emit captured(key,existing);return;}
    if (!QDir().mkpath(m_directory)) {emit failed(key,"Photo storage unavailable; word saved. Retry photo in Queue.");return;}
    QStorageInfo storage(m_directory);qint64 used=0;
    for (const auto &file:QDir(m_directory).entryInfoList(QStringList()<<"*.jpg",QDir::Files)) used+=file.size();
    if (!storage.isValid() || storage.bytesAvailable()<64LL*1024*1024 || used>512LL*1024*1024) {
        emit failed(key,"Photo storage is full. Upload saved cards before taking more photos.");return;
    }
    m_lock=new QLockFile(m_directory+"/.camera.lock");
    if (!m_lock->tryLock(0)) {delete m_lock;m_lock=nullptr;emit failed(key,"Camera is busy; word saved. Retry photo in Queue.");return;}
    m_key=key;
    // Recover an interrupted countdown before taking ownership of the light.
    const auto old=readFile(m_directory+"/.led-restore").trimmed();
    if (!old.isEmpty()) writeFile(m_led,old);
    m_previous=QString::fromLatin1(readFile(m_led).trimmed());
    if (!QRegularExpression("^[0-9]{1,3}$").match(m_previous).hasMatch() ||
        !writeFile(m_directory+"/.led-restore",m_previous.toLatin1()) || !writeFile(m_led,"255")) {
        finish("Could not turn on the camera light; word saved. Retry photo in Queue.");return;
    }
    m_prefix=m_directory+"/.capture-"+key+"-"+QUuid::createUuid().toString(QUuid::WithoutBraces);
    m_countdown=4;emit changed();m_timer.start();
}
void CameraBridge::takeFrame() {
    auto process=new QProcess(this);m_process=process;
    connect(process,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this,process](int code,QProcess::ExitStatus status) {
        if (m_process!=process) return;
        m_process=nullptr;process->deleteLater();
        if (code || status!=QProcess::NormalExit) {finish("Photo failed; word saved. Tap Retake photo in Queue.");return;}
        const auto format=QString::fromUtf8(readFile(m_prefix+".format"));
        auto size=QRegularExpression("Width/Height\\s*:\\s*(\\d+)\\s*/\\s*(\\d+)").match(format);
        auto type=QRegularExpression("Pixel Format\\s*:\\s*'([A-Za-z0-9 ]{4})'").match(format);
        auto strideMatch=QRegularExpression("Bytes per Line\\s*:\\s*(\\d+)").match(format);
        auto byteMatch=QRegularExpression("Size Image\\s*:\\s*(\\d+)").match(format);
        const int w=size.captured(1).toInt(),h=size.captured(2).toInt(),stride=strideMatch.captured(1).toInt();
        const auto pixel=type.captured(1);const int step=pixel=="YUYV" ? 2 : 1;
        const auto raw=readFile(m_prefix+".raw");
        if (w<2 || h<2 || qint64(w)*h>1000000 || stride<w*step ||
            (pixel!="YUYV" && pixel!="NV12" && pixel!="NV21") || raw.size()<stride*h ||
            (byteMatch.hasMatch() && raw.size()!=byteMatch.captured(1).toInt())) {
            finish("Camera returned an invalid image; word saved. Retry photo in Queue.");return;
        }
        QImage image(w,h,QImage::Format_Grayscale8);
        for (int y=0;y<h;++y) for (int x=0;x<w;++x) image.scanLine(y)[x]=uchar(raw[y*stride+x*step]);
        liftDarkPhoto(image);
        QSaveFile photo(m_directory+"/"+m_key+".jpg");
        if (!photo.open(QIODevice::WriteOnly) || !image.save(&photo,"JPG",85) || !photo.commit()) {
            finish("Could not save photo; word saved. Check storage and retry photo in Queue.");return;
        }
        finish();
    });
    connect(process,&QProcess::errorOccurred,this,[this,process](QProcess::ProcessError error) {
        if (m_process==process && error==QProcess::FailedToStart) {m_process=nullptr;process->deleteLater();finish("Camera helper unavailable; word saved.");}
    });
    QTimer::singleShot(18000,process,[this,process]() {
        if (m_process==process) {process->terminate();if (!process->waitForFinished(3000)) {process->kill();process->waitForFinished(1000);}if (busy()) finish("Photo timed out; word saved. Retry photo in Queue.");}
    });
    process->start("sh",QStringList()<<m_helper<<m_prefix<<m_previous);
}
void CameraBridge::finish(QString error) {
    const auto key=m_key;if (key.isEmpty()) return;
    m_timer.stop();
    if (!restoreLight() && error.isEmpty()) error="Photo saved, but camera light needs attention.";
    if (!m_prefix.isEmpty()) for (const auto &suffix:{".raw",".format"}) QFile::remove(m_prefix+suffix);
    m_key.clear();m_prefix.clear();m_countdown=0;
    delete m_lock;m_lock=nullptr;emit changed();
    if (error.isEmpty()) emit captured(key,photoPath(key));else emit failed(key,error);
}
void CameraBridge::cancel() {
    if (!busy()) return;
    if (m_process) {auto process=m_process;m_process=nullptr;process->disconnect(this);process->terminate();if (!process->waitForFinished(3000)) {process->kill();process->waitForFinished(1000);}process->deleteLater();}
    finish("Photo cancelled; word saved. Tap Retake photo in Queue.");
}
