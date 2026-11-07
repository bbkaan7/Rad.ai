"""Local event bridge to the owner-enabled Android accessibility companion."""
import asyncio
import json
import re
from xml.etree import ElementTree as ET
import aiohttp
from .domain import LayoutError
from .diagnostics import record, logged

PACKAGES={'io.anonchat','org.vidogram.messenger','org.telegram.messenger'}


def hierarchy(payload,package):
    """Reuse selectors in memory; never invoke Android's XML dump process."""
    if not payload.get('available') or payload.get('package')!=package:
        raise LayoutError('The requested app is not the current accessible Android window.')
    root=ET.Element('hierarchy'); count=0
    def add(parent,value,depth):
        nonlocal count
        count+=1
        if count>6000 or depth>40 or not isinstance(value,dict):
            raise LayoutError('Accessibility tree exceeds supported limits.')
        attrs=value.get('attributes',{})
        if not isinstance(attrs,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in attrs.items()):
            raise LayoutError('Invalid accessibility node attributes.')
        node=ET.SubElement(parent,'node',attrs)
        children=value.get('children',[])
        if not isinstance(children,list):raise LayoutError('Invalid accessibility children.')
        for child in children:add(node,child,depth+1)
    add(root,payload.get('tree'),0)
    return root


class AccessibilityClient:
    def __init__(self,bridge):
        self.bridge=bridge
        self.http=None; self.task=None; self.token=None
        self.base=f'http://127.0.0.1:{bridge.settings.accessibility_port}'
        self.forward=f'tcp:{bridge.settings.accessibility_port}'
        self.owned=False; self.session=None; self.cursor=0
        self.wake={p:asyncio.Event() for p in PACKAGES}
        self.on_notification=None
        self.notifications=False
        self.draft_edit=False

    @logged('accessibility.connect')
    async def connect(self):
        pairing_response=await self.bridge.blocking(self.bridge.device.shell,'content call --uri content://ai.rad.bridge.pairing --method token',timeout=10)
        match=re.search(r'token=([0-9a-f]{64})',pairing_response)
        token=match.group(1) if match else ''
        if not re.fullmatch('[0-9a-f]{64}',token):
            raise LayoutError('Install/open Rad.ai Bridge, then enable its Accessibility service in Android Settings.')
        self.token=token
        mappings=await self.bridge.blocking(self.bridge.device.list_forward)
        if self.forward in mappings:
            if mappings[self.forward]!='tcp:8765':raise LayoutError('The configured local bridge port is used by another forward.')
            # A prior crashed controller can leave this exact mapping behind.
            # The device lease ensures it is safe to reuse, without rebinding it.
        else:
            await self.bridge.blocking(self.bridge.device.forward,self.forward,'tcp:8765',norebind=True)
        self.owned=True
        self.http=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12),headers={'Authorization':'Bearer '+token},trust_env=False)
        try:
            health=await self.request('/health')
            if not health.get('accessibility') or health.get('version')!='0.1.15':
                raise LayoutError('Enable Rad.ai Bridge v0.1.15 in Android Accessibility settings.')
            self.notifications=bool(health.get('notifications'))
            self.draft_edit=health.get('draft_edit')==1
            self.session=health['session']
            self.task=asyncio.create_task(self.listen())
        except BaseException:
            await self.close();raise

    async def request(self,path,method='GET',payload=None):
        options={} if payload is None else {'data':json.dumps(payload,ensure_ascii=True).encode('ascii'),
                                           'headers':{'Content-Type':'application/json'}}
        async with self.http.request(method,self.base+path,allow_redirects=False,**options) as response:
            if response.status!=200:
                raise LayoutError(f'Android accessibility bridge returned HTTP {response.status}.')
            data=bytearray()
            async for chunk in response.content.iter_chunked(65536):
                data.extend(chunk)
                if len(data)>8*1024*1024:raise LayoutError('Accessibility response is too large.')
            value=json.loads(data)
            if not isinstance(value,dict):raise LayoutError('Invalid accessibility response.')
            return value

    async def edit_draft(self,package,header,before,after):
        if not self.draft_edit:raise LayoutError('Update Android bridge from Settings to enable waiting drafts.')
        result=await self.request('/draft','POST',{'package':package,'header':header.get('text',''),
            'header_bounds':header.get('bounds',''),'before':before,'after':after})
        self.bridge.read_snapshot=None
        return result.get('changed') is True

    async def snapshot(self,package):
        last=None
        for attempt in range(24):
            try:
                root=hierarchy(await self.request('/snapshot'),package)
                if any(n.get('visible-to-user','true')!='false' and (n.get('text') or n.get('content-desc')) for n in root.iter('node')):return root
                last=LayoutError('Android is still building the application view.')
            except (LayoutError,aiohttp.ServerDisconnectedError) as error:last=error
            if attempt<23:await asyncio.sleep(.2)
        raise last

    async def wait(self,package,timeout):
        event=self.wake[package]
        try:await asyncio.wait_for(event.wait(),timeout)
        except asyncio.TimeoutError:pass
        event.clear()

    async def consume(self,batch):
        session=batch.get('session')
        if session!=self.session:
            self.session=session; self.cursor=0
            for event in self.wake.values():event.set()
        events=batch.get('events',[])
        if events and events[0].get('seq',0)>self.cursor+1:
            for event in self.wake.values():event.set()
        for event in events:
            seq=event.get('seq',0)
            if seq<=self.cursor:continue
            if event.get('type')=='bridge_error':
                error=RuntimeError('Android helper failed; see android_frames for its source location.')
                error.android_frames=event.get('frames',[])[:20]
                record('android.helper',error,phase=event.get('stage'),operation=event.get('error_type'))
            package=event.get('package')
            if package in PACKAGES:
                self.wake[package].set()
                if event.get('type')=='notification' and self.on_notification:
                    self.notifications=True
                    await self.on_notification(event)
            self.cursor=seq

    async def listen(self):
        failures=0
        while True:
            try:
                await self.consume(await self.request('/events?after='+str(self.cursor)))
                failures=0
            except asyncio.CancelledError:raise
            except Exception as error:
                if failures in (0,3):record('accessibility.events',error,attempt=failures)
                failures+=1
                await asyncio.sleep(min(2**min(failures,4),15))

    async def open_notification(self,notification_id):
        if not re.fullmatch('[0-9a-f-]{36}',notification_id):raise LayoutError('Invalid notification reference.')
        result=await self.request('/open-notification?id='+notification_id,'POST')
        if not result.get('opened'):raise LayoutError('Notification conversation could not be opened.')

    async def close(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        if self.http:await self.http.close();self.http=None
        if self.owned and self.bridge.device is not None:
            try:await self.bridge.blocking(self.bridge.device.killforward,self.forward)
            except Exception as error:record('accessibility.close_forward',error)
        self.owned=False;self.token=None
