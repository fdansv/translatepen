import QtQuick 2.12
QtObject {
    property bool bRepeat:false
    property string fixtureTranslation:''
    signal analyzed(int requestId,string response)
    signal analysisFailed(int requestId)
    signal translated(int requestId,string response)
    signal translationFailed(int requestId,string explanation)
    signal ingested(string key,string jobId,string state)
    signal ingestionFailed(string key,string explanation,bool retryable)
    signal jobStatus(string key,string state,string error)
    signal markedKnown(int requestId,string response)
    signal knownFailed(int requestId,string explanation)
    function analyze(text,id) {}
    function cancelAnalysis() {}
    function translate(text,id) {
        if (fixtureTranslation) translated(id,JSON.stringify({text:text,translation:fixtureTranslation}));
    }
    function cancelTranslation() {}
    function ingest(payload,key) {}
    function watchJob(job,key) {}
    function markKnown(payload,id) {}
}
