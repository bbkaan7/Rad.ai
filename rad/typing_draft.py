"""Never-submitted Android drafts while an LLM job is running."""
import asyncio
import random
from contextlib import asynccontextmanager
from .domain import nodes, unique, LayoutError
from .diagnostics import record


def can_edit(adapter):
    bridge=adapter.bridge
    return bool(bridge and bridge.accessibility and bridge.accessibility.draft_edit)


async def write_reply(adapter,root,text):
    selectors=getattr(adapter,'selectors',adapter.settings.selectors)
    header=unique(root,selectors.get('identity'),'conversation header')
    if not await adapter.bridge.accessibility.edit_draft(adapter.package,header,'',text):
        raise LayoutError('The recipient or input changed before inserting the reply. Nothing was sent.')


class WaitingDraft:
    def __init__(self,adapter,key):
        self.adapter,self.key=adapter,key
        self.owned=''
        self.possible=None
        self.stopped=asyncio.Event()
        self.abandoned=False

    @property
    def selectors(self):
        return getattr(self.adapter,'selectors',self.adapter.settings.selectors)

    async def validate(self,root):
        a=self.adapter
        headers=nodes(root,self.selectors.get('identity'))
        expected=a.titles.get(self.key) if hasattr(a,'titles') else a.identity
        if len(headers)!=1 or headers[0].get('text')!=expected:return None
        if hasattr(a,'titles'):await a.validate_target(root,self.key)
        else:a.validate_target(root,self.key)
        return headers[0]

    def text(self,root):
        value=unique(root,self.selectors.get('input'),'waiting draft input').get('text','')
        return '' if value==self.selectors.get('input_placeholder','Message') else value

    async def change(self,header,before,after):
        # Reserve before the request: a lost response must not discard ownership.
        self.possible=after
        changed=await self.adapter.bridge.accessibility.edit_draft(self.adapter.package,header,before,after)
        if changed:self.owned=after;self.possible=None
        else:self.possible=None;self.abandoned=True
        return changed

    async def advance(self):
        a=self.adapter;b=a.bridge
        async with b.lock:
            if self.abandoned or a.blocked:return
            state=await b.accessibility.request('/snapshot')
            if not state.get('available') or state.get('package')!=a.package:return
            from .accessibility import hierarchy
            root=hierarchy(state,a.package)
            header=await self.validate(root)
            if header is None:return
            current=self.text(root)
            if current!=self.owned:self.abandoned=True;return
            after=self.owned+random.choice('abcdefghijklmnopqrstuvwxyz')
            if len(after)>32:after=self.owned[:-1]
            await self.change(header,current,after)

    async def clear_locked(self,root):
        """Caller owns the device lock and has opened the verified recipient."""
        if not self.owned and self.possible is None:return root
        header=await self.validate(root)
        if header is None:raise LayoutError('Waiting draft belongs to a different conversation; nothing was erased.')
        current=self.text(root)
        if current=='':self.owned='';self.possible=None;return root
        if self.abandoned or current not in (self.owned,self.possible):
            raise LayoutError('The waiting draft was edited manually. It was kept; clear it before resuming.')
        if not await self.change(header,current,''):
            raise LayoutError('The input changed during draft cleanup. Nothing else was erased.')
        from .ui_wait import read_until
        return await read_until(self.adapter.dump,lambda r:self.text(r)=='','clearing the waiting draft')

    async def run(self):
        s=self.adapter.settings
        try:
            await asyncio.wait_for(self.stopped.wait(),s.typing_delay_seconds)
            return
        except asyncio.TimeoutError:pass
        try:
            while not self.stopped.is_set() and not self.abandoned:
                await self.advance()
                try:await asyncio.wait_for(self.stopped.wait(),s.typing_interval_seconds*random.uniform(.8,1.2))
                except asyncio.TimeoutError:pass
        except Exception as error:
            record('typing.draft',error,key=self.key,phase='temporary_text',owned_length=len(self.owned))
            self.adapter.status('Waiting indicator stopped; draft cleanup will be checked before sending.')


async def clear_waiting(adapter,key,root):
    draft=getattr(adapter,'waiting_drafts',{}).get(key)
    if draft:
        root=await draft.clear_locked(root)
        adapter.waiting_drafts.pop(key,None)
    return root


@asynccontextmanager
async def waiting_typing(adapter,key):
    bridge=adapter.bridge
    if not adapter.settings.typing_enabled or not can_edit(adapter):
        yield
        return
    if not hasattr(adapter,'waiting_drafts'):adapter.waiting_drafts={}
    # Recover a previous leftover only if it is still our exact draft.
    if key in adapter.waiting_drafts:
        async with bridge.lock:
            await clear_waiting(adapter,key,await adapter.dump())
    draft=WaitingDraft(adapter,key);adapter.waiting_drafts[key]=draft
    task=asyncio.create_task(draft.run())
    try:yield
    finally:
        draft.stopped.set()
        # Finish an in-flight mutation before attempting cleanup.
        await task
        if not draft.owned and draft.possible is None:
            adapter.waiting_drafts.pop(key,None)
        else:
            try:
                async with bridge.lock:
                    state=await bridge.accessibility.request('/snapshot')
                    if state.get('available') and state.get('package')==adapter.package:
                        from .accessibility import hierarchy
                        root=hierarchy(state,adapter.package)
                        if await draft.validate(root) is not None:await clear_waiting(adapter,key,root)
            except Exception as error:
                record('typing.cleanup',error,key=key,phase='clear_temporary_text')
                adapter.status('Waiting draft cleanup needs inspection. No temporary text was sent.')
