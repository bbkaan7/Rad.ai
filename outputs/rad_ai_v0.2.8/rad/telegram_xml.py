"""English Telegram Android accessibility selectors, independent of pixel scaling.

Telegram exposes message direction in its accessibility Sent/Received suffix.
Unsupported/ambiguous layouts produce no guessed message direction.
"""
import copy
import re
from .anon_xml import box
from .domain import LayoutError

PACKAGE='org.telegram.messenger'

def label(node):
    return node.get('text') or node.get('content-desc','')


def message_info(node):
    text=label(node)
    matches=list(re.finditer(r'\n(Sent|Received) ([^\n]+)(?=\n|$)',text))
    if not matches:
        return None
    marker=matches[-1]
    body=text[:marker.start()].strip()
    if not body:
        return None
    # Status/read flags can change; they are not part of message identity.
    stamp=marker.group(2).split(', ')[0]
    return ('assistant' if marker.group(1)=='Sent' else 'user',body,stamp)


def dialog_name(node):
    text=label(node)
    if text.startswith(('Bot. ','Group. ','Channel. ','Secret chat. ','Topic. ')):
        return None
    if '. ' not in text:
        return None
    name=text.split('. ',1)[0].strip()
    if name in {'Telegram','Archived Chats','Archived chats'}:
        return None
    return name or None


def elements(root,role,package=PACKAGE):
    all_nodes=[n for n in root.iter('node') if n.get('package')==package and n.get('visible-to-user','true')!='false']
    if role=='chat_list':
        return [n for n in all_nodes if n.get('scrollable')=='true'
                and any(dialog_name(c) and ('. Received ' in label(c) or '. Sent ' in label(c)) for c in n.iter('node'))]
    if role=='chat_rows':
        return [n for n in all_nodes if n.get('clickable')=='true' and dialog_name(n)
                and ('. Received ' in label(n) or '. Sent ' in label(n) or n.get('class','').endswith('DialogCell'))]
    if role in {'send','back','reply','delete'}:
        expected={'send':{'Send'},'back':{'Go back','Back'},'reply':{'Reply'},'delete':{'Delete'}}[role]
        return [n for n in all_nodes if label(n) in expected]
    inputs=[n for n in all_nodes if n.get('class')=='android.widget.EditText' and n.get('content-desc')!='Search Chats']
    if role=='input':
        return inputs if len(inputs)==1 else []
    if role=='identity':
        if len(inputs)!=1:
            return []
        limit=box(inputs[0])[1]
        texts=[n for n in all_nodes if n.get('class')=='android.widget.TextView' and n.get('text')
               and box(n)[3]<=limit and not re.match(r'^(online|offline|typing|last seen|\d+ members|\d+ subscribers)',label(n),re.I)]
        return sorted(texts,key=lambda n:box(n)[1])[:1]
    if role in {'incoming','outgoing'}:
        wanted='user' if role=='incoming' else 'assistant'
        result=[]
        for n in all_nodes:
            info=message_info(n)
            if info and info[0]==wanted:
                normalized=copy.deepcopy(n)
                normalized.set('text',info[1])
                normalized.set('rad-stamp',info[2])
                result.append(normalized)
        return result
    if role=='quote':
        # Resource selectors can override this for Android versions exposing a quote ID.
        return [n for n in all_nodes if n.get('content-desc','').startswith('Reply to ')]
    return []


def login_screen(root):
    texts={label(n) for n in root.iter('node')}
    return bool(texts & {'Start Messaging','Your Phone','Your phone number','Enter code','Two-Step Verification','Your Password'})


def records(root,selectors):
    from .domain import nodes,center
    result=[]
    for role,name in [('user','incoming'),('assistant','outgoing')]:
        for n in nodes(root,selectors[name]):
            text=n.get('text','').strip()
            if text:
                x,y=center(n)
                result.append((y,x,role,text,n.get('rad-stamp',''),n))
    result.sort(key=lambda r:(r[0],r[1]))
    if len({(r[0],r[1]) for r in result})!=len(result):
        raise LayoutError('Telegram message selectors overlap.')
    return result

