"""Serialized Android transactions with fair, paced polling and launch protection."""
from .diagnostics import record, logged
import asyncio
import re
import time
from contextlib import asynccontextmanager
from ppadb.client import Client
from .domain import LayoutError, xml_root, ForegroundDeferred
from .device_lease import DeviceLease


class AndroidAttention(LayoutError):
    """An Android prompt needs the owner's attention; do not hide it."""


class TimedClient(Client):
    def create_connection(self,timeout=None):
        return super().create_connection(timeout=10 if timeout is None else timeout)


class AndroidBridge:
    def __init__(self,settings):
        self.settings=settings
        self.lock=asyncio.Lock()
        self.device=None
        self.active_package=None
        self.selected_package=None
        self.focus_changed=asyncio.Event()
        self.watchers=[]
        self.poll_owner=None
        self.owner_since=0.0
        self.retry_after={}
        self.failures={}
        self.last_launch={}
        self._clock=time.monotonic
        self.lease=DeviceLease(f'{settings.adb_host}:{settings.adb_port}/{settings.adb_device_host}:{settings.adb_device_port}')

    async def blocking(self,fn,*args,**kwargs):
        task=asyncio.create_task(asyncio.to_thread(fn,*args,**kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            finally:
                raise

    @logged('adb.connect')
    async def connect(self):
        async with self.lock:
            if self.device is not None:
                return
            self.lease.acquire()
            try:
                await self.connect_device()
            except BaseException:
                self.lease.close()
                raise

    async def connect_device(self):
        s=self.settings
        client=TimedClient(host=s.adb_host,port=s.adb_port)
        for attempt in range(2):
            await self.blocking(client.remote_connect,s.adb_device_host,s.adb_device_port)
            devices=await self.blocking(client.devices,state='device')
            found=[d for d in devices if not s.adb_serial or d.serial==s.adb_serial]
            if len(found)==1:
                self.device=found[0]
                return
            if len(found)>1:
                raise ValueError('Set adb_serial to exactly one connected BlueStacks device.')
            if attempt==0:
                # Only reconnect this emulator; never reset the shared ADB server.
                await self.blocking(client.remote_disconnect,s.adb_device_host,s.adb_device_port)
                await asyncio.sleep(.4)
        raise ValueError('BlueStacks is not ready. Open the configured instance and enable ADB, then try again.')

    @logged('adb.shell')
    async def shell(self,command):
        operation=command.partition(' ')[0]
        if self.device is None:
            raise ValueError('ADB is not connected.')
        try:
            return await self.blocking(self.device.shell,command,timeout=12)
        except RuntimeError as error:
            if 'device offline' not in str(error).lower():raise
            self.active_package=None
            await self.connect_device()
            # A failed input can be uncertain. Recover transport without replaying it.
            raise LayoutError('ADB reconnected after the emulator went offline. The previous operation was not retried.') from error

    async def foreground(self):
        output=await self.shell('dumpsys activity activities')
        match=re.search(r'(?:mResumedActivity|topResumedActivity|ResumedActivity):\s*ActivityRecord\{[^\n]*?\bu\d+\s+([\w.]+)/',output)
        return match.group(1) if match else None

    async def activate(self,package):
        if not re.fullmatch(r'[a-zA-Z][\w]*(?:\.[\w]+)+',package):
            raise ValueError('Invalid Android package name.')
        activity=self.settings.adb_activities.get(package)
        if activity and not re.fullmatch(r'[a-zA-Z.][\w.$]*',activity):
            raise ValueError('Invalid Android activity name.')
        current=await self.foreground()
        if current in {'com.android.permissioncontroller','com.google.android.permissioncontroller','com.android.packageinstaller'}:
            raise AndroidAttention('Respond to the Android permission window manually; app switching is waiting.')
        if current==package:
            self.active_package=package
            return
        if current is None:
            raise LayoutError('Android foreground is not ready; waiting without relaunching apps.')
        now=self._clock()
        if now-self.last_launch.get(package,float('-inf'))<self.settings.adb_launch_cooldown_seconds:
            raise LayoutError('App launch cooldown is active; waiting before another foreground request.')
        command='am start -W --activity-reorder-to-front --activity-single-top -a android.intent.action.MAIN -c android.intent.category.LAUNCHER'
        command+=(' -n '+package+'/'+activity) if activity else (' -p '+package)
        self.last_launch[package]=now
        result=await self.shell(command)
        if 'Error:' in result or 'Exception' in result:
            raise LayoutError('Android could not open '+package+'. Retrying with backoff.')
        await asyncio.sleep(self.settings.adb_switch_seconds)
        current=await self.foreground()
        if current!=package:
            self.active_package=None
            raise LayoutError('Android has not brought '+package+' to the foreground yet; waiting.')
        self.active_package=package

    def watch(self,package):
        if package not in self.watchers:
            self.watchers.append(package)
        self.failures.pop(package,None)
        self.retry_after.pop(package,None)

    def unwatch(self,package):
        if package in self.watchers:
            self.watchers.remove(package)
        self.failures.pop(package,None)
        self.retry_after.pop(package,None)
        if self.poll_owner==package:
            self.poll_owner=None

    def select_platform(self,package):
        self.selected_package=package
        self.focus_changed.set()

    async def wait_selected(self,package,cancelled=None):
        while self.selected_package not in (None,package):
            if cancelled and cancelled():return False
            self.focus_changed.clear()
            try:
                await asyncio.wait_for(self.focus_changed.wait(),.5)
            except asyncio.TimeoutError:
                pass
        return not (cancelled and cancelled())

    def poll_allowed(self,package):
        if self.selected_package not in (None,package):
            return False
        now=self._clock()
        eligible=[p for p in self.watchers if now>=self.retry_after.get(p,0) and self.selected_package in (None,p)]
        if package not in eligible:
            return False
        if self.poll_owner not in eligible:
            self.poll_owner=eligible[0]
            self.owner_since=now
        elif len(eligible)>1 and now-self.owner_since>=self.settings.adb_focus_seconds:
            self.poll_owner=eligible[(eligible.index(self.poll_owner)+1)%len(eligible)]
            self.owner_since=now
        return self.poll_owner==package

    def poll_failure(self,package,error):
        count=min(self.failures.get(package,0)+1,6)
        self.failures[package]=count
        delay=min(self.settings.adb_error_backoff_seconds*2**(count-1),60)
        if isinstance(error,AndroidAttention):
            # A permission dialog is global. Neither adapter should cover it.
            for watched in self.watchers:
                self.retry_after[watched]=self._clock()+delay
        self.retry_after[package]=self._clock()+delay

    @asynccontextmanager
    async def session(self,package):
        async with self.lock:
            if self.selected_package not in (None,package):
                raise ForegroundDeferred("Select the conversation platform to continue its queued action.")
            await self.activate(package)
            if package in self.watchers:
                self.poll_owner=package
                self.owner_since=self._clock()
            yield

    @asynccontextmanager
    async def poll_session(self,package):
        async with self.lock:
            if not self.poll_allowed(package):
                yield False
                return
            try:
                await self.activate(package)
                yield True
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.poll_failure(package,error)
                raise
            else:
                self.failures.pop(package,None)
                self.retry_after.pop(package,None)

    @logged('adb.dump')
    async def dump(self,package):
        # The Android child itself is bounded, not just the host socket timeout.
        for attempt in range(2):
            result=await self.shell('rm -f /sdcard/rad-ui.xml && toybox timeout -k 1 8 uiautomator dump /sdcard/rad-ui.xml && cat /sdcard/rad-ui.xml')
            try:
                root=xml_root(result)
            except LayoutError:
                if attempt==0:
                    await asyncio.sleep(.5)
                    continue
                raise
            packages={n.get('package') for n in root.iter('node')}
            if packages & {'com.android.permissioncontroller','com.google.android.permissioncontroller','com.android.packageinstaller'}:
                raise AndroidAttention('Respond to the Android permission window manually; app switching is waiting.')
            if package not in packages:
                self.active_package=None
                raise LayoutError('Android is not showing '+package+'; waiting for its UI.')
            return root

    async def background(self,package):
        """Leave only our stopped app; never dismiss another app or a system prompt."""
        async with self.lock:
            if self.device is None or not package or await self.foreground()!=package:
                return False
            await self.shell('input keyevent KEYCODE_HOME')
            self.active_package=None
            return True

    async def close(self):
        async with self.lock:
            self.watchers.clear()
            self.device=None
            self.active_package=None
            self.lease.close()
