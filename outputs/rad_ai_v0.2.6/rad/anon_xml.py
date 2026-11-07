"""Structural selectors verified against io.anonchat's React Native UI XML."""

import re


def box(node):
    values=re.findall(r"\d+",node.get("bounds",""))
    return tuple(map(int,values)) if len(values)==4 else (0,0,0,0)


def elements(root,role):
    all_nodes=[n for n in root.iter('node') if n.get('package')=='io.anonchat']
    parents={child:parent for parent in root.iter() for child in parent}
    inputs=[n for n in all_nodes if n.get('class')=='android.widget.EditText']
    if role=='next':
        width=max((box(n)[2] for n in all_nodes),default=0)
        return [n for n in all_nodes if n.get('content-desc')=='New partner'
                and n.get('clickable')=='true' and box(n)[2]-box(n)[0]>width*.5]
    if len(inputs)!=1:
        return []
    entry=inputs[0]
    ex1,ey1,ex2,ey2=box(entry)
    if role=='input':
        return [entry]
    panes=[n for n in all_nodes if n.get('class')=='android.widget.ScrollView'
           and 0<box(n)[3]<=ey1 and box(n)[2]>ex2]
    if not panes:
        return []
    pane=min(panes,key=lambda n:(box(n)[2]-box(n)[0])*(box(n)[3]-box(n)[1]))
    px1,py1,px2,py2=box(pane)
    if role=='identity':
        candidates=[n for n in all_nodes if n.get('class')=='android.widget.TextView'
            and n.get('text') and box(n)[3]<=py1
            and n.get('text').lower() not in {'online','offline','typing...'}]
        return sorted(candidates,key=lambda n:box(n)[1])[:1]
    if role=='bio':
        return [n for n in pane.iter('node') if n.get('content-desc','').startswith('About partner,')]
    if role=='send':
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
        if len(texts)!=1 or not timestamps:
            continue
        left,_,right,_=box(node)
        left_gap,right_gap=left-px1,px2-right
        if abs(left_gap-right_gap)<(px2-px1)*.05:
            raise ValueError('Message alignment is ambiguous in AnonChat XML.')
        direction='incoming' if left_gap<right_gap else 'outgoing'
        if direction==role:
            result.append(texts[0])
    return result
