import QtQuick 2.12
import "../app"
Rectangle {
    id:root
    width:800; height:480; color:'black'
    Japanese { id:page; standalone:true }
    function expect(surface) {
        if (!page.current || page.current.surface!==surface)
            throw new Error('Expected '+surface+' got '+JSON.stringify(page.current));
        console.log('PASS navigation '+surface+' ['+page.current.start+','+page.current.end+']');
    }
    Timer {
        interval:300; running:true
        onTriggered: {
            try {
                page.acceptScan('「図書館、日本語、食べました。」');
                page.firstWord(); expect('図書館');
                page.nextWord(); expect('日本語');
                page.nextWord(); expect('食べました');
                if (page.current.headword!=='食べる') throw new Error('Deinflection lost');
                page.previousWord(); expect('日本語');
                page.previousWord(); expect('図書館');
                page.previousWord(); expect('食べました');
                page.nextWord(); expect('図書館');
                // Navigation after a tap uses the chosen word's span.
                page.lookupAt(6); expect('日本語');
                page.previousWord(); expect('図書館');
                page.nextWord(); expect('日本語');
                page.nextWord(); expect('食べました');
                page.acceptScan('「まだ全然。」');
                page.firstWord(); expect('まだ');
                page.nextWord(); expect('全然');
                page.nextWord(); expect('まだ');
                page.previousWord(); expect('全然');
                page.previousWord(); expect('まだ');
                page.acceptScan('zqxv987654。');
                page.firstWord(); page.nextWord(); page.previousWord();
                if (page.current) throw new Error('Unknown text has a match');
                page.acceptScan('日本語'); page.firstWord();
                page.previousWord(); expect('日本語');
                page.scanning=true; page.nextWord(); page.previousWord(); expect('日本語');
                page.scanning=false; page.recognizing=true; page.nextWord(); page.previousWord(); expect('日本語');
                page.recognizing=false;
                console.log('TRANSLATEPEN_NAVIGATION_PASS');
            } catch(error) { console.log('TRANSLATEPEN_NAVIGATION_FAIL '+error); }
            Qt.quit();
        }
    }
}
