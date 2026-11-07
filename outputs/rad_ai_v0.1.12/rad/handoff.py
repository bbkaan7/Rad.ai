"""One-time, explicit cross-platform handoffs; never match people by display name."""
import secrets
import time
import re

class Handoffs:
    def __init__(self):
        self.pending={}
        self.links={}
        self.snapshots={}
        self.clock=time.monotonic

    def prune(self):
        self.pending={code:item for code,item in self.pending.items() if item[1]>self.clock()}
        active={item[0] for item in self.pending.values()}
        self.snapshots={key:data for key,data in self.snapshots.items() if key in active}

    def remember(self,source,person_id,context):
        self.prune()
        if any(item[0]==source for item in self.pending.values()):
            self.snapshots[source]={"person_id":person_id,"context":list(context)[-5:]}

    def issue(self,source):
        self.prune()
        self.pending={code:item for code,item in self.pending.items() if item[1]>self.clock() and item[0]!=source}
        token='RAD-'+secrets.token_hex(6).upper()
        self.pending[token]=(source,self.clock()+600)
        return token

    def consume(self,text,target):
        self.prune()
        token=text.strip().upper()
        if not re.fullmatch(r'RAD-[0-9A-F]{12}',token):return None
        item=self.pending.get(token)
        if not item:return None
        source,expires=item
        if expires<self.clock():
            self.pending.pop(token,None)
            return None
        if target in self.links or source in self.links.values():
            return None
        self.pending.pop(token)
        self.links[target]=source
        return source
