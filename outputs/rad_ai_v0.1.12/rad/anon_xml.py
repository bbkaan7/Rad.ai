"""Structural selectors verified against io.anonchat's React Native UI XML."""

import re


def box(node):
    values=re.findall(r"-?\d+",node.get("bounds",""))
    return tuple(map(int,values)) if len(values)==4 else (0,0,0,0)


def elements(root,role):
    all_nodes=[n for n in root.iter('node') if n.get('package')=='io.anonchat']
    parents={child:parent for parent in root.iter() for child in parent}
    inputs=[n for n in all_nodes if n.get('class')=='android.widget.EditText']
    if role=='next':
        width=max((box(n)[2] for n in all_nodes),default=0)
        return [n for n in all_nodes if n.get('content-desc')=='New partner'
                and n.get('clickable')=='true' and box(n)[2]-box(n)[0]>width*.5]
    width=max((box(n)[2] for n in all_nodes),default=0)
    height=max((box(n)[3] for n in all_nodes),default=0)
    # Choose the top-level transcript viewport, never a nested bio/message scroller.
    panes=[n for n in all_nodes if n.get('class')=='android.widget.ScrollView'
        and 0<box(n)[1]<height*.3 and box(n)[2]-box(n)[0]>=width*.85
        and box(n)[3]-box(n)[1]>height*.15]
    pane=min(panes,key=lambda n:(box(n)[1],-(box(n)[3]-box(n)[1]))) if panes else None
    if role=='input':
        return inputs if len(inputs)==1 else []
    if pane is None:
        return []
    px1,py1,px2,py2=box(pane)
    if role=='identity':
        controls={n.get('content-desc') for n in all_nodes if n.get('clickable')=='true'}
        if not inputs and not controls.intersection({'New partner','End chat','Report'}):
            return []  # The Friends list title is not a conversation identity.
        body=set(pane.iter('node'))
        candidates=[n for n in all_nodes if n not in body and n.get('class')=='android.widget.TextView'
            and n.get('text') and 0<=box(n)[1]<box(n)[3]<=py1
            and n.get('text').lower() not in {'online','offline','typing...'}
            and not n.get('text').lower().startswith(('last seen','typing'))]
        # A missing/ambiguous header is an unreadable view, not a new person.
        return candidates if len(candidates)==1 else []
    if role=='bio':
        return [n for n in pane.iter('node') if n.get('content-desc','').startswith('About partner,')]
    if role=='send':
        if len(inputs)!=1:
            return []
        entry=inputs[0]
        ex1,ey1,ex2,ey2=box(entry)
        parent_right=box(parents[entry])[2]
        candidates=[n for n in all_nodes if n.get('clickable')=='true'
            and box(n)[0]>=parent_right and box(n)[1]<ey2 and box(n)[3]>ey1]
        # Nested click targets are ambiguous unless they describe the same bounds.
        unique={box(n):n for n in candidates}
        return list(unique.values())
    if role not in {'incoming','outgoing'}:
        return []
    result=[]
    for node in pane.iter('node'):
        label=node.get('content-desc','')
        if not label or label.startswith('About partner') or label=='Chat starts':
            continue
        texts=[n for n in node if n.get('class')=='android.widget.TextView' and n.get('text')==label]
        parent=parents.get(node)
        timestamps=[] if parent is None else [n for n in parent if re.fullmatch(r'\d{1,2}:\d{2}(?:\s*[AP]M)?',n.get('text',''))]
        if len(texts)!=1:
            continue
        left,_,right,_=box(node)
        left_gap,right_gap=left-px1,px2-right
        if abs(left_gap-right_gap)<(px2-px1)*.05:
            continue  # Centered system notices are not message bubbles.
        direction='incoming' if left_gap<right_gap else 'outgoing'
        if direction==role:
            result.append(texts[0])
    return result


def navigation(root):
    """Return the three exposed bottom navigation nodes, left to right."""
    all_nodes=[n for n in root.iter('node') if n.get('package')=='io.anonchat']
    width=max((box(n)[2] for n in all_nodes),default=0)
    height=max((box(n)[3] for n in all_nodes),default=0)
    candidates=[n for n in all_nodes if n.get('class')=='android.view.View'
        and n.get('clickable')=='true' and box(n)[1]>.85*height
        and .25*width<box(n)[2]-box(n)[0]<.4*width]
    return sorted(candidates,key=lambda n:box(n)[0]) if len(candidates)==3 else []
