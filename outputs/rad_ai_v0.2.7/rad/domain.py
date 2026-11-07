"""Pure context, message identity and XML operations."""

from dataclasses import dataclass, field
from collections import deque
import re
import shlex
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Message:
    id: str
    role: str
    text: str


@dataclass
class Chat:
    key: str
    title: str
    messages: deque = field(default_factory=lambda: deque(maxlen=200))
    seen: set = field(default_factory=set)
    revision: int = 0
    paused: bool = False
    uncertain: bool = False
    received: int = 0
    handled: int = 0
    busy: bool = False
    category: str = "Chats"

    def append(self, message):
        if message.id in self.seen:
            return False
        self.messages.append(message)
        self.seen.add(message.id)
        if len(self.seen) > 2000:
            self.seen = {m.id for m in self.messages}
        self.revision += 1
        return True

    def context(self):
        return [{"role":m.role,"content":m.text} for m in list(self.messages)[-5:]]


class LayoutError(ValueError):
    pass


def xml_root(text):
    start = text.find("<?xml")
    if start < 0:
        start = text.find("<hierarchy")
    if start < 0:
        raise LayoutError("Android did not return a UI XML hierarchy.")
    try:
        root = ET.fromstring(text[start:].strip())
    except ET.ParseError as error:
        raise LayoutError("Android returned incomplete UI XML.") from error
    if root.tag != "hierarchy":
        raise LayoutError("Unexpected UI XML root.")
    return root


def nodes(root, selector):
    if not selector:
        return []
    if 'tg-role' in selector:
        from .telegram_xml import elements
        return elements(root,selector['tg-role'])
    if 'rad-role' in selector:
        from .anon_xml import elements
        return elements(root,selector['rad-role'])
    return [n for n in root.iter("node") if all(n.get(k)==str(v) for k,v in selector.items())]


def unique(root, selector, label):
    found = nodes(root,selector)
    if len(found)!=1:
        raise LayoutError(f"Expected one {label} XML node; found {len(found)}. Check selectors.")
    return found[0]


def center(node):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",node.get("bounds",""))
    if not match:
        raise LayoutError("Control has invalid XML bounds.")
    x1,y1,x2,y2=map(int,match.groups())
    if x2<=x1 or y2<=y1:
        raise LayoutError("Control has empty XML bounds.")
    return (x1+x2)//2,(y1+y2)//2


def input_command(text):
    # Android input text is not a Unicode input method. Reject unsupported text
    # before tapping or typing, rather than silently corrupting a message.
    if not text or len(text)>1500 or any(ord(c)<32 or ord(c)>126 for c in text) or "%s" in text:
        raise ValueError("ADB input supports printable ASCII only (no literal %s). Edit this reply.")
    return "input text " + shlex.quote(text.replace(" ","%s"))


def tail_delta(previous, current):
    """Match ordered suffixes, preserving repeated equal messages by occurrence."""
    if not previous:
        return current
    for count in range(min(len(previous),len(current)),0,-1):
        if previous[-count:]==current[:count]:
            return current[count:]
    if current==previous:
        return []
    raise LayoutError("Message list no longer overlaps the last XML snapshot. Reconnect to resync; no reply was sent.")


def snapshot(root, selectors):
    package=selectors.get("package")
    if not package or not any(n.get("package")==package for n in root.iter("node")):
        raise LayoutError("The configured AnonChat package is not active inside Android.")
    identity=unique(root,selectors.get("identity"),"chat identity").get("text","").strip()
    if not identity:
        raise LayoutError("Chat identity is empty.")
    records=[]
    for role,name in (("user","incoming"),("assistant","outgoing")):
        if not selectors.get(name):
            raise LayoutError(f"Configure the {name} XML selector first.")
        for node in nodes(root,selectors[name]):
            text=node.get("text","").strip()
            if text:
                x,y=center(node)
                records.append((y,x,role,text))
    records.sort()
    if len({(y,x) for y,x,_,_ in records}) != len(records):
        raise LayoutError("Incoming/outgoing XML selectors overlap.")
    return identity,[(role,text) for _,_,role,text in records]
