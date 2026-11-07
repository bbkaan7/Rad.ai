"""Single-device arbitration for every Android read/gesture/app switch."""
import asyncio
import re
from contextlib import asynccontextmanager
from ppadb.client import Client
from .domain import LayoutError, xml_root


class TimedClient(Client):
    def create_connection(self,timeout=None):
        return super().create_connection(timeout=10 if timeout is None else timeout)


class AndroidBridge:
    def __init__(self,settings):
        self.settings=settings
        self.lock=asyncio.Lock()
        self.device=None
        self.active_package=None

    async def blocking(self,fn,*args,**kwargs):
        # Cancellation cannot release the device while a shell command is still running.
        task=asyncio.create_task(asyncio.to_thread(fn,*args,**kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            finally:
                raise

    async def connect(self):
        async with self.lock:
            if self.device is not None:
                return
            s=self.settings
            client=TimedClient(host=s.adb_host,port=s.adb_port)
            await self.blocking(client.remote_connect,s.adb_device_host,s.adb_device_port)
            devices=await self.blocking(client.devices)
            found=[d for d in devices if not s.adb_serial or d.serial==s.adb_serial]
            if len(found)!=1:
                raise ValueError("Set adb_serial to exactly one connected BlueStacks device.")
            self.device=found[0]

    async def shell(self,command):
        if self.device is None:
            raise ValueError("ADB is not connected.")
        return await self.blocking(self.device.shell,command,timeout=12)

    async def activate(self,package):
        if not re.fullmatch(r'[a-zA-Z][\w]*(?:\.[\w]+)+',package):
            raise ValueError("Invalid Android package name.")
        if self.active_package==package:
            return
        activity=self.settings.adb_activities.get(package)
        if activity:
            if not re.fullmatch(r'[a-zA-Z.][\w.$]*',activity):
                raise ValueError("Invalid Android activity name.")
            command="am start -W -n "+package+"/"+activity
        else:
            command="am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p "+package
        result=await self.shell(command)
        if "Error:" in result or "Exception" in result:
            raise ValueError("Android could not open "+package+". Check that it is installed.")
        self.active_package=package
        await asyncio.sleep(self.settings.adb_switch_seconds)

    @asynccontextmanager
    async def session(self,package):
        async with self.lock:
            await self.activate(package)
            yield

    async def dump(self,package):
        for attempt in range(2):
            result=await self.shell("rm -f /sdcard/rad-ui.xml && uiautomator dump /sdcard/rad-ui.xml && cat /sdcard/rad-ui.xml")
            try:
                root=xml_root(result)
            except LayoutError:
                if attempt==0:
                    await asyncio.sleep(.25)
                    continue
                raise
            if not any(n.get('package')==package for n in root.iter('node')):
                self.active_package=None
                raise LayoutError("Android is not showing "+package+"; waiting for its UI.")
            return root
