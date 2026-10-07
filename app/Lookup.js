.pragma library
.import QtQuick.LocalStorage 2.0 as Sql

// Deinflection algorithm adapted from Yomichan, Copyright 2016-2022
// Yomichan Authors, GPL-3.0-or-later. See vendor/YOMICHAN-LICENSE.
var db = null;
var rules = [];
var ready = false;
var rankedForms = false;
var types = {v1:1, v5:2, vs:4, vk:8, vz:16, "adj-i":32, iru:64};

function initialize(directory) {
    if (ready) return;
    var request = new XMLHttpRequest();
    request.open("GET", "file://" + directory + "/deinflect.json", false);
    request.send();
    var source = JSON.parse(request.responseText);
    for (var reason in source) {
        var variants = source[reason];
        for (var n=0; n<variants.length; ++n) {
            var v = variants[n], incoming=0, outgoing=0;
            for (var j=0; j<v.rulesIn.length; ++j) incoming |= types[v.rulesIn[j]] || 0;
            for (j=0; j<v.rulesOut.length; ++j) outgoing |= types[v.rulesOut[j]] || 0;
            rules.push({input:v.kanaIn, output:v.kanaOut, incoming:incoming, outgoing:outgoing, reason:reason});
        }
    }
    db = Sql.LocalStorage.openDatabaseSync("TranslatePen", "1.0", "Japanese lookup and saved words", 1000000);
    db.transaction(function(tx) {
        var attached = tx.executeSql('PRAGMA database_list'), exists = false;
        for (var i=0; i<attached.rows.length; ++i) if (attached.rows.item(i).name === 'lexicon') exists=true;
        if (!exists) tx.executeSql('ATTACH DATABASE ? AS lexicon', [directory + '/dictionary.sqlite']);
        tx.executeSql('SELECT id FROM lexicon.entries LIMIT 1');
        var columns=tx.executeSql('PRAGMA lexicon.table_info(forms)');
        for (i=0;i<columns.rows.length;++i) if (columns.rows.item(i).name==='priority') rankedForms=true;
        tx.executeSql('CREATE TABLE IF NOT EXISTS saved(id INTEGER PRIMARY KEY, created TEXT, sentence TEXT, surface TEXT, headword TEXT, reading TEXT, gloss TEXT, start INTEGER, end INTEGER)');
        tx.executeSql('CREATE TABLE IF NOT EXISTS diagnostics(id INTEGER PRIMARY KEY, time INTEGER, event TEXT, details TEXT)');
        tx.executeSql('CREATE TABLE IF NOT EXISTS migaku_outbox(key TEXT PRIMARY KEY, payload TEXT UNIQUE, state TEXT, job TEXT, error TEXT)');
    });
    ready = true;
}

function deinflect(term) {
    var result = [{term:term, flags:0, reasons:[]}], seen = {};
    seen[term+'|0'] = true;
    for (var i=0; i<result.length && result.length<256; ++i) {
        var current = result[i];
        for (var j=0; j<rules.length; ++j) {
            var rule=rules[j];
            if (current.flags && !(current.flags & rule.incoming)) continue;
            if (current.term.slice(-rule.input.length) !== rule.input) continue;
            var next=current.term.slice(0,-rule.input.length)+rule.output;
            var key=next+'|'+rule.outgoing;
            if (!next || seen[key]) continue;
            seen[key]=true;
            result.push({term:next, flags:rule.outgoing, reasons:[rule.reason].concat(current.reasons)});
        }
    }
    return result;
}

function boundary(c) { return !c || /[\s。、！？!?「」『』（）()【】\[\]，,．.：:；;・…—―]/.test(c); }

function lookup(sentence, position, exactStart, exactEnd, forward) {
    if (!ready) throw new Error('Dictionary is not ready');
    if (!sentence.length) return [];
    position = Math.max(0,Math.min(position,sentence.length-1));
    var first=position, last=position+1;
    while (first>0 && position-first<16 && !boundary(sentence[first-1])) --first;
    while (last<sentence.length && last-position<24 && !boundary(sentence[last])) ++last;
    if (forward) first=position;
    var exact=typeof exactStart==='number' && exactStart>=0;
    if (exact) { first=exactStart; last=exactEnd; }
    var matches=[], cache={}, seen={};
    db.readTransaction(function(tx) {
        for (var start=first; start<=(exact?first:position); ++start) {
            for (var end=last; end>=(exact?last:position+1); --end) {
                var surface=sentence.substring(start,end);
                if (!surface || boundary(surface[0]) || boundary(surface[surface.length-1])) continue;
                var forms=deinflect(surface);
                for (var f=0; f<forms.length; ++f) {
                    var form=forms[f], rows=cache[form.term];
                    if (typeof rows==='undefined') {
                        var order=rankedForms ? 'f.priority DESC,f.entry_id' : 'e.priority DESC';
                        var query=tx.executeSql('SELECT e.* FROM lexicon.forms f JOIN lexicon.entries e ON e.id=f.entry_id WHERE f.term=? ORDER BY '+order+' LIMIT 24',[form.term]);
                        rows=[];
                        for (var r=0; r<query.rows.length; ++r) rows.push(query.rows.item(r));
                        cache[form.term]=rows;
                    }
                    for (r=0; r<rows.length; ++r) {
                        var row=rows[r];
                        if (form.flags && !(row.pos & form.flags)) continue;
                        var key=start+'|'+end+'|'+row.id;
                        if (seen[key]) continue;
                        seen[key]=true;
                        matches.push({id:row.id, seq:row.seq, headword:row.headword, reading:row.reading,
                            gloss:row.gloss, priority:row.priority, surface:surface, start:start, end:end,
                            source:row.source || 'JMdict', kind:row.kind || '',
                            reasons:form.reasons, score:surface.length*10000+row.priority*10-form.reasons.length*50});
                    }
                }
            }
        }
    });
    matches.sort(function(a,b) { return b.score-a.score || a.start-b.start || a.id-b.id; });
    return matches.slice(0,40);
}

// Advancing through a sentence must not match an earlier word across the
// navigation cursor. Touch lookup still considers spans on both sides.
function lookupFrom(sentence, position) {
    return lookup(sentence, position, undefined, undefined, true);
}

function recordEvent(event, details) {
    if (!ready) return;
    try {
        db.transaction(function(tx) {
            tx.executeSql('INSERT INTO diagnostics(time,event,details) VALUES(?,?,?)',
                [Date.now(),event,JSON.stringify(details || {})]);
            tx.executeSql('DELETE FROM diagnostics WHERE id <= (SELECT MAX(id)-200 FROM diagnostics)');
        });
    } catch(error) { console.log('TRANSLATEPEN_DIAGNOSTICS '+error); }
}

function save(sentence, match) {
    db.transaction(function(tx) {
        tx.executeSql('INSERT INTO saved(created,sentence,surface,headword,reading,gloss,start,end) VALUES(?,?,?,?,?,?,?,?)',
            [new Date().toISOString(),sentence,match.surface,match.headword,match.reading,match.gloss,match.start,match.end]);
    });
}

function queueIngestion(payload) {
    var result;
    db.transaction(function(tx) {
        var rows=tx.executeSql('SELECT * FROM migaku_outbox WHERE payload=?',[payload]);
        if (rows.rows.length) {
            result=rows.rows.item(0);
            if (result.state==='failed') {
                tx.executeSql("UPDATE migaku_outbox SET state='pending',error=NULL WHERE key=?",[result.key]);
                result.state='pending';
            }
        } else {
            var key='pen-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
            tx.executeSql("INSERT INTO migaku_outbox(key,payload,state) VALUES(?,?,'pending')",[key,payload]);
            result={key:key,payload:payload,state:'pending'};
        }
    });
    return result;
}
function pendingIngestion() {
    var result=null;
    db.readTransaction(function(tx) {
        var rows=tx.executeSql("SELECT * FROM migaku_outbox WHERE state='pending' ORDER BY rowid LIMIT 1");
        if (rows.rows.length) result=rows.rows.item(0);
    });
    return result;
}
function sentIngestion(afterKey) {
    var result=null;
    db.readTransaction(function(tx) {
        var rows=tx.executeSql("SELECT * FROM migaku_outbox WHERE state IN ('sent','attention') AND rowid>COALESCE((SELECT rowid FROM migaku_outbox WHERE key=?),0) ORDER BY rowid LIMIT 1",[afterKey]);
        if (!rows.rows.length) rows=tx.executeSql("SELECT * FROM migaku_outbox WHERE state IN ('sent','attention') ORDER BY rowid LIMIT 1");
        if (rows.rows.length) result=rows.rows.item(0);
    });
    return result;
}
function finishIngestion(key, state, job, error) {
    db.transaction(function(tx) {
        tx.executeSql('UPDATE migaku_outbox SET state=?,job=COALESCE(?,job),error=? WHERE key=?',[state,job || null,error || null,key]);
    });
}
