"""English Telegram Android accessibility selectors, independent of pixel scaling.

Telegram exposes message direction in its accessibility Sent/Received suffix.
Unsupported/ambiguous layouts produce no guessed message direction.
"""
import copy
import re
from .anon_xml import box
from .domain import LayoutError

PACKAGE='org.telegram.messenger'


def opaque_dialog_rows(root,package=PACKAGE):
    """Vidogram omits row labels; only recognize rows inside its verified chat home."""
    all_nodes=[n for n in root.iter('node') if n.get('package')==package and n.get('visible-to-user','true')!='false']
    if not any(n.get('content-desc')=='Search Chats' for n in all_nodes):return []
    tabs=[n for n in all_nodes if label(n).split('\n')[0] in {'All Chats','Private','Groups','Channels','Unread'}]
    if not any(label(n).split('\n')[0]=='Private' for n in tabs):return []
    width=max((box(n)[2] for n in all_nodes),default=0)
    height=max((box(n)[3] for n in all_nodes),default=0)
    lower=min(box(n)[1] for n in tabs)
    lists=[n for n in all_nodes if n.get('scrollable')=='true' and box(n)[3]-box(n)[1]>height*.5]
    if len(lists)!=1:return []
    return [n for n in lists[0] if n.get('class')=='android.view.ViewGroup'
        and box(n)[2]-box(n)[0]>=width*.85 and .035*height<box(n)[3]-box(n)[1]<.15*height
        and box(n)[1]>=lower and box(n)[3]<height*.94]

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
        if node.get('class','').endswith('DialogCell') and text.strip() and '\n' not in text:
            return text.strip()
        return None
    name=text.split('. ',1)[0].strip()
    if name in {'Telegram','Archived Chats','Archived chats'}:
        return None
    return name or None


def elements(root,role,package=PACKAGE):
    all_nodes=[n for n in root.iter('node') if n.get('package')==package and n.get('visible-to-user','true')!='false']
    if role=='chat_list':
        named=[n for n in all_nodes if n.get('scrollable')=='true'
                and any(dialog_name(c) and ('. Received ' in label(c) or '. Sent ' in label(c) or c.get('class','').endswith('DialogCell')) for c in n.iter('node'))]
        if named:return named
        if opaque_dialog_rows(root,package):
            height=max(box(n)[3] for n in all_nodes)
            return [n for n in all_nodes if n.get('scrollable')=='true' and box(n)[3]-box(n)[1]>height*.5]
        return []
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



def local_search_candidates(root,title,package):
    """Only local search results above the Global search boundary are eligible."""
    all_nodes=[n for n in root.iter('node') if n.get('package')==package]
    local_headers=[box(n)[1] for n in all_nodes if label(n) in {'Recent','Chats','Contacts'}
                   and n.get('class')=='android.widget.TextView']
    if not local_headers:
        return []
    start=min(local_headers)
    global_headers=[box(n)[1] for n in all_nodes if label(n)=='Global search']
    end=min(global_headers) if global_headers else float('inf')
    result=[]
    for n in all_nodes:
        text=label(n)
        if n.get('class')!='android.view.ViewGroup' or not start<box(n)[1]<end:
            continue
        if text.casefold()==title.casefold() or text.casefold().startswith(title.casefold()+', '):
            if not re.search(r'\b(subscribers|members)\b',text,re.I):
                result.append(n)
    return result
