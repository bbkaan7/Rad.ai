"""Notification previews are separate from verified messages and reply context."""
import asyncio
import time
from collections import OrderedDict
from .diagnostics import record
from .domain import nodes, LayoutError


class NotificationInbox:
    def __init__(self,engine):
        self.engine=engine
        self.pending=OrderedDict();self.seen=OrderedDict()
        self.changed=asyncio.Event();self.task=None

    async def receive(self,event):
        if event.get('group') or not event.get('title') or not event.get('text'):return
        if event.get('title') in {'Telegram','System chat'}:return
        identity=(event.get('id'),event.get('posted_at'),event.get('text'))
        if identity in self.seen:return
        self.seen[identity]=True
        while len(self.seen)>256:self.seen.popitem(last=False)
        event=dict(event)
        event['received_at']=time.monotonic();event['attempts']=0
        self.pending[event['id']]=event
        while len(self.pending)>100:self.pending.popitem(last=False)
        self.engine.emit({'type':'notification','id':event['id'],'package':event['package'],
                          'title':event['title'],'text':event['text'],'verified':False})
        self.changed.set()
        if self.task is None or self.task.done():self.task=asyncio.create_task(self.run())

    async def verify(self,event):
        e=self.engine;bridge=e.android
        adapter=e.anon if event['package']==e.anon.package else e.telegram
        # Do not hide a pending draft or split an in-flight conversation action.
        if any(a.blocked for a in (e.anon,e.telegram)):return False
        if any(lock.locked() for lock in e.locks.values()):return False
        if any(not task.done() for task in e.jobs.values()):return False
        async with bridge.lock:
            # Recheck after acquiring the global device transaction.
            if adapter.blocked or event['package'] not in bridge.watchers:return False
            snapshot=await bridge.accessibility.request('/snapshot')
            current_package=snapshot.get('package')
            if snapshot.get('available') and current_package in (e.anon.package,e.telegram.package):
                from .accessibility import hierarchy
                current=e.anon if current_package==e.anon.package else e.telegram
                selectors=e.settings.selectors if current is e.anon else current.selectors
                entries=nodes(hierarchy(snapshot,current_package),selectors.get('input'))
                if any(n.get('text','').strip() not in ('',selectors.get('input_placeholder','Message')) for n in entries):return False
            await bridge.accessibility.open_notification(event['id'])
            await asyncio.sleep(.25)
            root=await adapter.dump()
            # The notification title is a routing hint, never an account identifier.
            # Each adapter verifies history before adding deltas or allowing a send.
            if adapter is e.anon:
                headers=nodes(root,e.settings.selectors.get('identity'))
                if len(headers)!=1 or headers[0].get('text','').casefold()!=event['title'].casefold():
                    raise LayoutError('Notification title and opened AnonChat header do not match.')
                await adapter.process(root,allow_actions=False)
                key=adapter.key
                if adapter.identity_ambiguous:raise LayoutError('Friend history could not be verified.')
            else:
                if adapter.identity(root).casefold()!=event['title'].casefold():
                    raise LayoutError('Notification title and opened Telegram header do not match.')
                key=await adapter.process(root)
                if key in adapter.quarantined:raise LayoutError('Telegram history could not be verified.')
            bridge.active_package=adapter.package
            bridge.poll_owner=adapter.package;bridge.owner_since=bridge._clock()
            e.emit({'type':'notification_verified','id':event['id'],'key':key})
            return True

    async def run(self):
        while not self.engine.closed:
            self.changed.clear()
            for ident,event in list(self.pending.items()):
                if self.pending.get(ident) is not event:continue
                if event['package'] not in self.engine.android.watchers:continue
                if time.monotonic()-event['received_at']>180:
                    self.pending.pop(ident,None);continue
                try:
                    done=await self.verify(event)
                except asyncio.CancelledError:raise
                except Exception as error:
                    event['attempts']+=1
                    record('inbox.verify',error,package=event['package'],attempt=event['attempts'])
                    done=event['attempts']>=3
                    if done:self.engine.status('Notification preview is available; open its conversation to verify the full history.')
                if done and self.pending.get(ident) is event:self.pending.pop(ident,None)
            try:await asyncio.wait_for(self.changed.wait(),1.0)
            except asyncio.TimeoutError:pass

    async def close(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.pending.clear();self.seen.clear()
