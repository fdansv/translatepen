import QtQuick 2.12
import "../app"
Item {
    id:root
    width:800; height:480
    MockMigaku { id:migaku }
    Japanese { id:page; standalone:true; migakuBridge:migaku }
    property var spans:[{start:0,end:3,surface:'図書館',status:'KNOWN'},
        {start:4,end:6,surface:'蛞蝓',status:'UNKNOWN'},
        {start:7,end:10,surface:'日本語',status:'UNKNOWN'}]
    function check(ok,reason) { if (!ok) throw new Error(reason); }
    function scan(text) {
        page.scanRequestId++;
        page.acceptScan(typeof text==='undefined' ? '図書館、蛞蝓、日本語。' : text);
        page.firstWord();
    }
    function respond(rows,text,id) {
        migaku.analyzed(typeof id==='undefined' ? page.scanRequestId : id,
            JSON.stringify({text:typeof text==='undefined' ? page.sentence : text,spans:rows}));
    }
    function find(item,name) {
        if (item.objectName===name) return item;
        for (var i=0;i<item.children.length;++i) {
            var result=find(item.children[i],name);
            if (result) return result;
        }
        return null;
    }
    Timer {
        interval:300; running:true
        onTriggered: {
            try {
                scan();
                check(page.current.surface==='図書館' && page.pendingUnknownFocus,'local fallback is immediate');
                respond(root.spans,'wrong sentence');
                respond(root.spans,page.sentence,page.scanRequestId-1);
                check(page.current.surface==='図書館' && page.pendingUnknownFocus,'stale replies leave initial focus intact');
                respond([root.spans[2],{start:4,end:5,surface:'wrong',status:'UNKNOWN'},root.spans[0],root.spans[1]]);
                check(page.current.surface==='蛞蝓' && page.current.start===4 && page.current.end===6,
                    'first valid unknown in scan order selected at exact span');
                check(!page.pendingUnknownFocus && page.unknownRanges.length===2,'default selection is consumed once');
                page.nextWord();
                check(page.current.surface==='日本語','navigation starts at unknown focus');
                respond(root.spans);
                check(page.current.surface==='日本語','later status refresh does not move cursor');

                scan(); page.lookupAt(7); respond(root.spans);
                check(page.current.surface==='日本語','tap before status preserves chosen word');
                scan(); page.nextWord(); page.nextWord(); respond(root.spans);
                check(page.current.surface==='日本語','volume navigation before status is preserved');
                scan(); page.previousWord(); respond(root.spans);
                check(page.current.surface==='日本語','previous navigation before status is preserved');
                scan(); page.pressB(); respond(root.spans);
                check(page.current.surface==='図書館' && page.firstBAt>0,'B press keeps its selected snapshot armed');
                page.resetB();
                scan(); find(page,'selectButton').clicked(); respond(root.spans);
                check(page.selecting && page.current.surface==='図書館','manual span selection is preserved');
                page.selecting=false;

                scan(); respond([{start:0,end:3,surface:'図書館',status:'KNOWN'}]);
                check(page.current.surface==='図書館' && !page.pendingUnknownFocus,'all-known scan retains local fallback');
                scan(); migaku.analysisFailed(page.scanRequestId); respond(root.spans);
                check(page.current.surface==='図書館' && !page.pendingUnknownFocus,'offline status retains local fallback');

                scan('図書館、zqxv987654、日本語。');
                respond([{start:4,end:14,surface:'zqxv987654',status:'UNKNOWN'}]);
                check(!page.current && page.unknownFocus && page.unknownFocus.surface==='zqxv987654',
                    'unknown without local dictionary entry is still prioritized');
                check(find(page,'sourceText').selectedText==='zqxv987654','unmatched unknown remains highlighted');
                page.nextWord();
                check(page.current.surface==='日本語' && !page.unknownFocus,'navigation continues after unmatched unknown');

                scan('😀図書館、蛞蝓。');
                respond([{start:2,end:5,surface:'図書館',status:'KNOWN'},
                    {start:6,end:8,surface:'蛞蝓',status:'UNKNOWN'}]);
                check(page.current.surface==='蛞蝓' && page.current.start===6,'UTF-16 offsets preserved');
                scan('');
                check(!page.pendingUnknownFocus && !page.unknownFocus,'empty scan resets priority');
                console.log('TRANSLATEPEN_UNKNOWN_FOCUS_PASS initial priority, exact spans, manual choices, stale replies and fallback');
            } catch(error) { console.log('TRANSLATEPEN_UNKNOWN_FOCUS_FAIL '+error); }
            Qt.quit();
        }
    }
    Timer { interval:12000; running:true; onTriggered: { console.log('TRANSLATEPEN_UNKNOWN_FOCUS_FAIL timeout'); Qt.quit(); } }
}
