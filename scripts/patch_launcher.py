#!/usr/bin/env python3
"""Patch the home QML and expose one existing Qt slot in a COPY of the inspected binary."""
import hashlib
from pathlib import Path
import re
import struct
import zlib
from extract_qml import EXPECTED, DATA, NAMES, TREE, NODE_COUNT

INJECT = '''
                 Button {
                     id: japaneseDictionary
                     x:22; y:27; width:174; height:109
                     background: Rectangle { color: parent.down ? "#32796c" : "#193f3b"; radius:18; border.color:"#67d6af"; border.width:2 }
                     contentItem: Text { text:"辞"; color:"#92f0ce"; font.pixelSize:64; horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter }
                     onClicked: {
                         statusbar.cur_module_name = "Jp";
                         startTransitions();
                         stackView.push("file:///userdata/translatepen/app/Japanese.qml");
                     }
                 }
                 Text {
                     anchors.top:japaneseDictionary.bottom; anchors.topMargin:25
                     anchors.horizontalCenter:japaneseDictionary.horizontalCenter
                     text:"Migaku\\nPen"; color:"#8ae5c3"; font.pixelSize:24
                     horizontalAlignment:Text.AlignHCenter
                 }
'''


def without_comments(source):
    # Preserve quoted strings (including URLs); drop only actual comments.
    pattern = r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|//[^\n]*|/\*[\s\S]*?\*/'
    return re.sub(pattern, lambda m: m.group(1) or '', source)


def patch(source, target, resource_revision=3):
    image=bytearray(source.read_bytes())
    if hashlib.sha256(image).hexdigest()!=EXPECTED: raise ValueError('Unknown original binary')
    # CommonCenter::scanTextResultHandle is a private Qt slot (flags 0x8).
    # Make this existing slot public (0xa) so the custom page can cancel the
    # online multiline timer. No native instructions or method IDs change.
    flags_offset=0xc91a08
    assert struct.unpack_from('<I',image,flags_offset)[0]==0x8
    struct.pack_into('<I',image,flags_offset,0xa)
    for node in range(NODE_COUNT):
        position=TREE+22*node
        no, flags=struct.unpack_from('>IH',image,position)
        length=struct.unpack_from('>H',image,NAMES+no)[0]
        name=image[NAMES+no+6:NAMES+no+6+length*2].decode('utf-16be')
        if name!='main.qml' or flags&2: continue
        offset=struct.unpack_from('>I',image,position+10)[0]
        size=struct.unpack_from('>I',image,DATA+offset)[0]
        raw=image[DATA+offset+4:DATA+offset+4+size]
        assert flags&1
        qml=zlib.decompress(raw[4:]).decode('utf-8-sig').replace('\r\n','\n')
        qml=without_comments(qml)
        for handler in ('onVolumeUpKeyPress', 'onVolumeDownKeyPress'):
            pattern=handler+r'\s*:\s*\{'
            qml, count=re.subn(pattern, lambda m: m.group(0)+'\nif(statusbar.cur_module_name === "Jp") return;', qml)
            assert count==1, 'Unexpected global volume handler layout'
        marker='                 Button {\n                     id: textTranslation'
        assert qml.count(marker)==1
        qml=qml.replace(marker,INJECT+'\n'+marker,1)
        begin=qml.index('id: textTranslation')
        anchor=qml.index('anchors.leftMargin: 22',begin)
        qml=qml[:anchor]+qml[anchor:].replace('anchors.leftMargin: 22','anchors.leftMargin: 218',1)
        assert qml.count('contentWidth: (9*174 + 10 * 22)-10')==1
        qml=qml.replace('contentWidth: (9*174 + 10 * 22)-10','contentWidth: (10*174 + 11 * 22)-10')
        qml='\n'.join(line.strip() for line in qml.splitlines() if line.strip())+'\n'
        payload=qml.encode('utf-8')
        compressed=struct.pack('>I',len(payload))+zlib.compress(payload,9)
        if len(compressed)>size: raise ValueError('Replacement does not fit original resource allocation')
        struct.pack_into('>I',image,DATA+offset,len(compressed))
        # QML's disk cache keys include QResource::lastModified. Invalidate the
        # original cached compilation without changing the vendor startup script.
        modified=struct.unpack_from('>Q',image,position+14)[0]
        struct.pack_into('>Q',image,position+14,modified+resource_revision*86400000)
        image[DATA+offset+4:DATA+offset+4+size]=compressed+bytes(size-len(compressed))
        target.write_bytes(image)
        target.with_suffix('.main.qml').write_text(qml)
        print(f'Patched main.qml: {size} -> {len(compressed)} compressed bytes; ELF size unchanged')
        print(hashlib.sha256(image).hexdigest())
        return
    raise ValueError('main.qml resource not found')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path); p.add_argument('target',type=Path)
    a=p.parse_args(); patch(a.source,a.target)
