"""Locate actual request controls, excluding transcript and biography content."""
import re
from .domain import nodes, LayoutError


def acceptance_control(root,selectors):
    package=selectors.get('package','io.anonchat')
    parents={child:parent for parent in root.iter() for child in parent}
    excluded=set()
    for role in ('incoming','outgoing','bio'):
        for node in nodes(root,selectors.get(role)):
            group=parents.get(node,node) if role!='bio' else node
            excluded.update(group.iter())
    visible=[n for n in root.iter('node') if n not in excluded and n.get('package')==package
             and n.get('visible-to-user')!='false']
    labels={n:(n.get('text') or n.get('content-desc') or '').strip() for n in visible}
    notices=[text for text in labels.values()
             if re.search(r'friend(?:ship)? request|wants to (?:be|become|add).*friend',text,re.I)
             and not re.search(r'you (?:have )?sent|^send (?:a )?friend|request sent|accepted|became friends',text,re.I)]
    config=selectors.get('friend_requests',{})
    exact=set(config.get('explicit_accept_labels',['Accept friend request','Accept friendship request']))
    generic=set(config.get('accept_labels',['Accept','Confirm']))
    candidates=[]
    for node,text in labels.items():
        if text not in exact and not (notices and text in generic):continue
        control=node
        while control is not None and control.get('clickable')!='true':control=parents.get(control)
        if control is None or control in excluded or control.get('package')!=package:continue
        if control.get('enabled')=='false':continue
        if control not in candidates:candidates.append(control)
    if len(candidates)>1:raise LayoutError('Multiple friend request acceptance controls are visible; no request was accepted.')
    if not candidates:return None
    return candidates[0],tuple(sorted(set(notices)))
