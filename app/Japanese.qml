import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Window 2.12
import "Lookup.js" as Lookup
import TranslatePen.Native 1.0 as Native

Item {
    id: page
    objectName: "translatepenJapanese"
    width: 800
    height: 480
    property bool standalone: false
    property bool scanning: false
    property bool recognizing: false
    property bool initialized: false
    property bool selecting: false
    property int anchorPosition: -1
    property int previousLanguage: -1
    property string sentence: ""
    property string notice: "Scan Japanese text to look up a word"
    property var matches: []
    property int matchIndex: 0
    property var current: matches.length ? matches[matchIndex] : null
    property var wordCache: ({})
    property double releasedAt: 0
    property double resultAt: 0
    property bool awaitingSentenceFrame: false
    property int scanRequestId: 0
    property var scannerBridge: defaultScanner
    property var migakuBridge: defaultMigaku
    property var unknownRanges: []
    property var wordStatuses: []
    property bool markingKnown: false
    property int knownRequestId: 0
    property var knownSnapshot: null
    property bool currentKnown: isCurrentKnown()
    property string migakuNotice: ""
    property string activeIngestionKey: ""
    property string lastMonitorKey: ""
    property var attentionMonitorAt: ({})
    property bool ingesting: false
    property double firstBAt: 0
    property int bScanId: -1
    property string bFocus: ""
    Native.ScanBridge { id: defaultScanner }
    Native.MigakuBridge { id: defaultMigaku }
    signal backRequested()
    FontLoader { id: cjk; source:'file:///oem/fonts/NotoSansCJK-Regular.ttc' }

    Component.onCompleted: {
        try {
            Lookup.initialize('/userdata/translatepen');
            initialized = true;
        } catch (error) { notice = 'Dictionary could not open: ' + error; }
        if (!standalone) {
            previousLanguage = commonCenter.getOcrlanid();
            commonCenter.stopAllaudioplay();
            commonCenter.setScanread(true);
            commonCenter.setInEdit(false);
            commonCenter.setcanstoptts(true);
            commonCenter.setOcrlanid(918);
            statusbar.visible = false;
            console.log('TRANSLATEPEN_READY');
        }
    }
    Component.onDestruction: {
        scannerBridge.cancel();
        migakuBridge.cancelAnalysis();
        if (!standalone) {
            commonCenter.setScanread(false);
            if (previousLanguage >= 0) commonCenter.setOcrlanid(previousLanguage);
            statusbar.visible = true;
        }
    }
    function goBack() {
        if (scanning) return;
        scanRequestId++;
        scannerBridge.cancel();
        migakuBridge.cancelAnalysis();
        resetB();
        if (standalone) { backRequested(); return; }
        commonCenter.stopAllaudioplay();
        statusbar.cur_module_name = 'Dt';
        statusbar.visible = true;
        stackView.pop();
    }
    function acceptScan(text) {
        resultAt = Date.now();
        recognizing = false;
        Lookup.recordEvent('ocr-ready', {releaseToOcrMs:releasedAt ? resultAt-releasedAt : null, characters:text.length});
        firstLookup.stop();
        statusLookup.stop();
        resetB();
        unknownRanges=[]; wordStatuses=[]; migakuNotice=''; activeIngestionKey='';
        sentence = text.trim();
        matches=[]; wordCache=({});
        selecting = false; anchorPosition = -1;
        sourceText.text = sentence;
        sourceScroll.contentY = 0;
        if (!sentence) { matches=[]; notice='No text recognized. Please scan again.'; return; }
        notice='Looking up the first word…';
        awaitingSentenceFrame=true;
        // Give Qt a frame to display the recognized sentence before doing SQL.
        firstLookup.start();
    }
    Connections {
        target: page.scannerBridge
        onRecognized: {
            if (requestId !== page.scanRequestId || page.scanning || !page.recognizing) return;
            Lookup.recordEvent('home-ocr', {roundtripMs:roundtripMs, serverMs:serverMs});
            page.acceptScan(text);
        }
        onFailed: {
            if (requestId !== page.scanRequestId || page.scanning || !page.recognizing) return;
            page.recognizing=false;
            page.notice=explanation;
            Lookup.recordEvent('home-ocr-failed', {});
        }
        onCaptureStopped: {
            if (requestId !== page.scanRequestId) return;
            Lookup.recordEvent('scanner-stop-returned', {stopCallMs:durationMs, imageBytes:imageBytes});
        }
    }
    Timer {
        id:firstLookup; interval:40
        onTriggered: page.firstWord()
    }
    Connections {
        target: page.Window.window
        onFrameSwapped: {
            if (page.awaitingSentenceFrame) {
                page.awaitingSentenceFrame=false;
                Lookup.recordEvent('sentence-frame', {ocrToFrameMs:Date.now()-page.resultAt, releaseToFrameMs:page.releasedAt ? Date.now()-page.releasedAt : null});
            }
        }
    }
    function navigationNotice() { return 'Vol − / +: previous / next · B twice: Migaku'; }
    function resetB() { firstBAt=0; bScanId=-1; bFocus=''; }
    function focusIdentity() { return current ? sentence+'|'+current.start+'|'+current.end : ''; }
    function ingestionProblem(error) {
        if (error==='ingestion_dictionary_empty') return 'Migaku has no definition for this selection · request saved';
        if (error==='ingestion_ai_failed' || error==='ingestion_generation_failed') return 'Migaku AI could not fill the card · request saved';
        if (error==='ingestion_timeout') return 'Migaku AI took too long · request saved';
        if (error==='deck_missing' || error==='ingestion_destination_missing') return 'Choose a Migaku deck · request saved';
        if (error==='login_required') return 'Sign in to Migaku · request saved';
        return 'Migaku needs attention · request saved';
    }
    function isCurrentKnown() {
        if (!current) return false;
        for (var i=0;i<wordStatuses.length;++i) {
            var span=wordStatuses[i];
            if (span.start===current.start && span.end===current.end && span.status==='KNOWN') return true;
        }
        return false;
    }
    function markCurrentKnown() {
        if (!initialized || !current || currentKnown || markingKnown || scanning || recognizing || selecting || firstLookup.running) return;
        resetB(); statusLookup.stop(); migakuBridge.cancelAnalysis();
        knownSnapshot={sentence:sentence,start:current.start,end:current.end,surface:current.surface,scanId:scanRequestId};
        markingKnown=true; knownRequestId++;
        migakuNotice='Marking '+current.surface+' as known…';
        migakuBridge.markKnown(JSON.stringify({language:'ja',sentence:sentence,focus_word:current.surface,
            focus_start:current.start,focus_end:current.end}),knownRequestId);
    }
    function pressB() {
        if (migakuBridge.bRepeat || !initialized || !current || scanning || recognizing || selecting || firstLookup.running) {
            resetB(); return;
        }
        var now=Date.now(), identity=focusIdentity();
        if (firstBAt && now-firstBAt>=60 && now-firstBAt<=450 && bScanId===scanRequestId && bFocus===identity) {
            resetB();
            try {
                var payload=JSON.stringify({language:'ja',sentence:sentence,focus_word:current.surface,
                    focus_start:current.start,focus_end:current.end});
                var row=Lookup.queueIngestion(payload);
                activeIngestionKey=row.key;
                migakuNotice=row.state==='complete' ? 'Created in Migaku' : row.state==='attention' ? ingestionProblem(row.error) :
                    row.state==='sent' ? 'Sent to Migaku' : 'Saved for Migaku…';
                if (row.state==='attention' && row.job) migakuBridge.watchJob(row.job,row.key);
                flushOutbox();
            } catch(error) { migakuNotice='Could not queue for Migaku: '+error; }
        } else { firstBAt=now; bScanId=scanRequestId; bFocus=identity; }
    }
    function flushOutbox() {
        if (!initialized || ingesting || scanning || recognizing || firstLookup.running) return;
        try {
            var row=Lookup.pendingIngestion();
            if (!row) return;
            ingesting=true;
            migakuBridge.ingest(row.payload,row.key);
        } catch(error) { ingesting=false; migakuNotice='Could not read Migaku queue'; }
    }
    Timer { interval:15000; running:page.initialized; repeat:true; onTriggered:page.flushOutbox() }
    Timer {
        interval:3000; running:page.initialized; repeat:true
        onTriggered: {
            if (page.scanning || page.recognizing || firstLookup.running) return;
            var row=Lookup.sentIngestion(page.lastMonitorKey);
            if (row) {
                page.lastMonitorKey=row.key;
                if (row.state==='attention') {
                    if (Date.now()-(page.attentionMonitorAt[row.key] || 0)<30000) return;
                    page.attentionMonitorAt[row.key]=Date.now();
                }
                page.migakuBridge.watchJob(row.job,row.key);
            }
        }
    }
    Timer {
        id:statusLookup; interval:1
        onTriggered: { if (!page.scanning && !page.recognizing) page.migakuBridge.analyze(page.sentence,page.scanRequestId); }
    }
    Connections {
        target:page.migakuBridge
        onAnalyzed: {
            if (requestId!==page.scanRequestId || page.scanning || page.recognizing || page.markingKnown) return;
            try {
                var result=JSON.parse(response), ranges=[], statuses=[];
                if (result.text!==page.sentence || !Array.isArray(result.spans)) return;
                for (var i=0;i<result.spans.length;++i) {
                    var span=result.spans[i];
                    if (span.start>=0 && span.end>span.start && span.end<=page.sentence.length &&
                        page.sentence.substring(span.start,span.end)===span.surface) {
                        statuses.push(span);
                        if (span.status==='UNKNOWN') ranges.push(span);
                    }
                }
                page.wordStatuses=statuses;
                page.unknownRanges=ranges;
            } catch(error) { page.unknownRanges=[]; page.wordStatuses=[]; }
        }
        onMarkedKnown: {
            if (requestId!==page.knownRequestId) return;
            page.markingKnown=false;
            var snapshot=page.knownSnapshot;
            if (!snapshot || snapshot.scanId!==page.scanRequestId || snapshot.sentence!==page.sentence || page.scanning || page.recognizing) return;
            var result=JSON.parse(response), statuses=page.wordStatuses.filter(function(span) {
                return span.start!==snapshot.start || span.end!==snapshot.end;
            });
            statuses.push({start:snapshot.start,end:snapshot.end,surface:snapshot.surface,status:'KNOWN'});
            page.wordStatuses=statuses;
            page.unknownRanges=page.unknownRanges.filter(function(span) { return span.start!==snapshot.start || span.end!==snapshot.end; });
            if (page.current && page.current.start===snapshot.start && page.current.end===snapshot.end)
                page.migakuNotice='Marked known ✓';
            statusLookup.restart();
        }
        onKnownFailed: {
            if (requestId!==page.knownRequestId) return;
            page.markingKnown=false;
            var snapshot=page.knownSnapshot;
            if (snapshot && snapshot.scanId===page.scanRequestId && snapshot.sentence===page.sentence && !page.scanning && !page.recognizing) {
                if (page.current && page.current.start===snapshot.start && page.current.end===snapshot.end) page.migakuNotice=explanation;
                statusLookup.restart();
            }
        }
        onAnalysisFailed: {
            if (requestId===page.scanRequestId && !page.scanning && !page.recognizing && !page.activeIngestionKey)
                page.migakuNotice='Migaku word status unavailable';
        }
        onIngested: {
            page.ingesting=false;
            Lookup.finishIngestion(key,'sent',jobId,'');
            if (key===page.activeIngestionKey) page.migakuNotice=state==='synced' ? 'Created in Migaku' : 'Sent to Migaku · filling card…';
        }
        onIngestionFailed: {
            page.ingesting=false;
            if (!retryable) Lookup.finishIngestion(key,'failed','',explanation);
            if (key===page.activeIngestionKey) page.migakuNotice=explanation;
        }
        onJobStatus: {
            if (state==='synced' || state==='failed' || state==='uncertain')
                Lookup.finishIngestion(key,state==='synced' ? 'complete' : 'attention','',error);
            if (key===page.activeIngestionKey)
                page.migakuNotice=state==='synced' ? 'Created in Migaku ✓' :
                    state==='blocked' || state==='failed' || state==='uncertain' ? page.ingestionProblem(error) :
                    state==='created' ? 'Created in Migaku · syncing…' : 'Sent to Migaku · filling card…';
        }
    }
    function findWord(first, limit) {
        for (var position=first; position<limit; ++position) {
            if (Lookup.boundary(sentence[position])) continue;
            var rows=wordCache[position];
            if (typeof rows==='undefined') {
                rows=Lookup.lookupFrom(sentence,position);
                wordCache[position]=rows;
            }
            if (rows.length) return rows;
        }
        return [];
    }
    function showMatches(rows) {
        matches=rows; matchIndex=0;
        selecting=false; anchorPosition=-1;
        notice=rows.length ? navigationNotice() : 'No dictionary match. Scan again or select a phrase.';
        selectCurrent();
    }
    function firstWord() {
        if (!initialized || !sentence || scanning || recognizing) return;
        var began=Date.now();
        try { showMatches(findWord(0,sentence.length)); }
        catch(error) { matches=[]; notice='Lookup failed: '+error; }
        Lookup.recordEvent('first-word', {lookupMs:Date.now()-began, matches:matches.length});
        // Status lookup starts only after the local definition is available.
        statusLookup.start();
    }
    function nextWord() {
        if (!initialized || !sentence || scanning || recognizing) return;
        firstLookup.stop();
        var began=Date.now(), start=current ? current.end : 0;
        try {
            var rows=findWord(start,sentence.length);
            if (!rows.length && start>0) rows=findWord(0,start);
            showMatches(rows);
        } catch(error) { matches=[]; notice='Lookup failed: '+error; }
        Lookup.recordEvent('next-word', {lookupMs:Date.now()-began, start:current ? current.start : null, end:current ? current.end : null});
    }
    function lastWordBefore(limit) {
        // Walk forward with the same compound/deinflection choices as nextWord.
        // Searching backward by character could select a suffix inside a word.
        var previous=[], position=0;
        while (position<limit) {
            var rows=findWord(position,limit);
            if (!rows.length || rows[0].end>limit) break;
            previous=rows;
            position=rows[0].end;
        }
        return previous;
    }
    function previousWord() {
        if (!initialized || !sentence || scanning || recognizing) return;
        firstLookup.stop();
        var began=Date.now(), limit=current ? current.start : sentence.length;
        try {
            var rows=lastWordBefore(limit);
            if (!rows.length && limit<sentence.length) rows=lastWordBefore(sentence.length);
            showMatches(rows);
        } catch(error) { matches=[]; notice='Lookup failed: '+error; }
        Lookup.recordEvent('previous-word', {lookupMs:Date.now()-began, start:current ? current.start : null, end:current ? current.end : null});
    }
    function lookupAt(position, start, end) {
        if (!initialized || !sentence) return;
        firstLookup.stop();
        var began = Date.now();
        try {
            matches = Lookup.lookup(sentence, position, start, end);
            matchIndex = 0;
            selectCurrent();
            if (!matches.length) notice='No dictionary match here. Tap another word or select a phrase.';
            console.log('TRANSLATEPEN_LOOKUP matches=' + matches.length + ' ms=' + (Date.now()-began));
            Lookup.recordEvent('touch-lookup', {lookupMs:Date.now()-began, matches:matches.length});
        } catch(error) { notice='Lookup failed: ' + error; matches=[]; }
    }
    function selectCurrent() {
        resetB();
        activeIngestionKey=''; migakuNotice='';
        if (current) {
            sourceText.select(current.start,current.end);
            var rectangle=sourceText.positionToRectangle(current.start);
            if (rectangle.y<sourceScroll.contentY) sourceScroll.contentY=rectangle.y;
            else if (rectangle.y+rectangle.height>sourceScroll.contentY+sourceScroll.height)
                sourceScroll.contentY=Math.max(0,Math.min(sourceScroll.contentHeight-sourceScroll.height,rectangle.y+rectangle.height-sourceScroll.height));
        }
        else sourceText.deselect();
        definitionScroll.contentY=0;
    }
    function choosePosition(position) {
        position=Math.max(0,Math.min(position,sentence.length-1));
        if (selecting) {
            if (anchorPosition<0) { anchorPosition=position; notice='Tap the last character of the phrase'; sourceText.select(position,position+1); }
            else {
                var start=Math.min(anchorPosition,position), end=Math.max(anchorPosition,position)+1;
                selecting=false; anchorPosition=-1; notice='Selected phrase';
                lookupAt(start,start,end);
                if (!matches.length) sourceText.select(start,end);
            }
        } else { notice=navigationNotice(); lookupAt(position); }
    }

    Connections {
        target: page.standalone ? null : gbKey
        onScanKeyPress: {
            if (!page.scanning) {
                firstLookup.stop();
                statusLookup.stop();
                page.migakuBridge.cancelAnalysis();
                page.resetB(); page.unknownRanges=[]; page.wordStatuses=[]; page.migakuNotice=''; page.activeIngestionKey='';
                page.scanRequestId++;
                page.recognizing=false;
                page.releasedAt=0; page.awaitingSentenceFrame=false;
                commonCenter.stopAllaudioplay();
                page.scanning=page.scannerBridge.beginScan(commonCenter);
                page.notice=page.scanning ? 'Scanning…' : 'Scanner unavailable. Reopen Migaku Pen.';
            }
        }
        onScanKeyRelease: {
            if (page.scanning) {
                page.releasedAt=Date.now(); page.scanning=false; page.recognizing=true;
                page.notice='Recognizing Japanese…';
                Lookup.recordEvent('scan-released', {});
                page.scannerBridge.endScan(commonCenter, page.scanRequestId);
            }
        }
        onCircularKeyPress: page.goBack()
        onForeKeyPress: page.pressB()
        onVolumeUpKeyPress: { Lookup.recordEvent('volume-up-key', {}); page.nextWord(); }
        onVolumeDownKeyPress: { Lookup.recordEvent('volume-down-key', {}); page.previousWord(); }
    }

    Rectangle {
        id: panel
        x: 0; y: 106; width: 800; height: 268
        color: '#101c26'
        Rectangle { x:0; y:0; width:800; height:44; color:'#182c39' }
        FlatButton {
            x:0; y:0; width:64; height:44
            text:'‹'; font.pixelSize:38; font.family:cjk.name
            background: Rectangle { color: parent.down ? '#345366' : 'transparent' }
            contentItem: Text { text:parent.text; color:'white'; font:parent.font; horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter }
            onClicked: page.goBack()
        }
        Text { x:72; y:6; text:'Migaku Pen'; color:'#edf7fa'; font.pixelSize:25; font.family:cjk.name }
        FlatButton {
            x:330; y:2; width:110; height:40; text:page.selecting ? 'Cancel' : 'Select'; font.pixelSize:20; font.family:cjk.name
            onClicked: { page.selecting=!page.selecting; page.anchorPosition=-1; page.notice=page.selecting ? 'Tap the first character of the phrase' : 'Tap any word'; }
        }
        FlatButton {
            objectName:'markKnownButton'
            x:452; y:2; width:144; height:40; text:page.markingKnown ? 'Marking…' : page.currentKnown ? 'Known ✓' : 'Mark known';
            enabled:page.current!==null && !page.currentKnown && !page.markingKnown && !page.scanning && !page.recognizing && !page.selecting;
            font.pixelSize:20; font.family:cjk.name
            onClicked: page.markCurrentKnown()
        }
        FlatButton {
            x:608; y:2; width:180; height:40; text:page.matches.length ? (page.matchIndex+1)+' / '+page.matches.length+'  ›' : 'No matches'; font.pixelSize:20; enabled:page.matches.length>1; font.family:cjk.name
            onClicked: { page.matchIndex=(page.matchIndex+1)%page.matches.length; page.selectCurrent(); }
        }
        Flickable {
            id: sourceScroll
            x:14; y:49; width:772; height:66
            contentHeight: Math.max(height,sourceText.height)
            clip:true
            TextEdit {
                id:sourceText
                width:parent.width; height:Math.max(64,implicitHeight)
                color:'#eaf6fa'; selectionColor:'#296f68'; selectedTextColor:'#ffffff'
                font.pixelSize:28; font.family:cjk.name; wrapMode:TextEdit.Wrap; readOnly:true; selectByMouse:false; textFormat:TextEdit.PlainText
                persistentSelection:true; cursorVisible:false
                Canvas {
                    id:unknownUnderline
                    anchors.fill:parent
                    onPaint: {
                        var ctx=getContext('2d'); ctx.clearRect(0,0,width,height);
                        ctx.strokeStyle='#ff555f'; ctx.lineWidth=2;
                        for (var r=0;r<page.unknownRanges.length;++r) {
                            var range=page.unknownRanges[r];
                            for (var i=range.start;i<range.end;++i) {
                                var a=sourceText.positionToRectangle(i), b=sourceText.positionToRectangle(i+1);
                                var endX=b.y===a.y ? b.x : sourceText.width;
                                ctx.beginPath(); ctx.moveTo(a.x,a.y+a.height-2);
                                ctx.lineTo(endX,a.y+a.height-2); ctx.stroke();
                            }
                        }
                    }
                    Connections { target:page; onUnknownRangesChanged:unknownUnderline.requestPaint() }
                    Connections { target:sourceText; onHeightChanged:unknownUnderline.requestPaint(); onTextChanged:unknownUnderline.requestPaint() }
                }
                MouseArea {
                    anchors.fill:parent
                    onClicked: page.choosePosition(sourceText.positionAt(mouse.x,mouse.y))
                    onPressAndHold: {
                        page.selecting=true;
                        page.anchorPosition=Math.max(0,Math.min(sourceText.positionAt(mouse.x,mouse.y),page.sentence.length-1));
                        sourceText.select(page.anchorPosition,page.anchorPosition+1);
                        page.notice='Tap the last character of the phrase';
                    }
                }
            }
        }
        Rectangle { x:14; y:118; width:772; height:1; color:'#304652' }
        Flickable {
            id:definitionScroll
            x:14; y:124; width:772; height:116; clip:true
            contentHeight:definitionColumn.height
            Column {
                id:definitionColumn; width:parent.width; spacing:3
                Text {
                    width:parent.width; color:'#80e2bc'; font.pixelSize:28; font.family:cjk.name; font.bold:true; wrapMode:Text.Wrap
                    text:page.current ? page.current.headword + (page.current.headword!==page.current.reading ? '  【'+page.current.reading+'】' : '') : '日本語'
                }
                Text {
                    width:parent.width; color:'#9dbcca'; font.pixelSize:18; font.family:cjk.name; wrapMode:Text.Wrap
                    visible:page.current ? page.current.reasons.length>0 : false
                    text:page.current ? page.current.surface+' → '+page.current.headword+'  ('+page.current.reasons.join(' · ')+')' : ''
                }
                Text {
                    width:parent.width; color:'#edf4f8'; font.pixelSize:22; font.family:cjk.name; wrapMode:Text.Wrap; textFormat:Text.PlainText
                    text:page.current ? page.current.gloss : 'Scan a word or sentence, then tap a word for its reading and meaning.'
                }
                Text {
                    visible:!!page.current
                    width:parent.width; color:'#95afbe'; font.pixelSize:13; font.family:cjk.name; wrapMode:Text.Wrap
                    text:page.current ? 'EDRDG · '+page.current.source+' · CC BY-SA 4.0' : ''
                }
            }
        }
        Text { x:14; y:244; width:772; height:22; text:page.migakuNotice || page.notice; color:'#95afbe'; font.pixelSize:17; font.family:cjk.name; elide:Text.ElideRight }
    }
}
