import asyncio,sys,time,json
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ayarlar import load
from rad.adb import AndroidBridge
from rad.anonchat import AnonChat
async def noop(*args):pass
async def main():
 b=AndroidBridge(load());await b.connect()
 out=Path('runtime/handshake_0210');out.mkdir(parents=True,exist_ok=True)
 a=AnonChat(load(),noop,lambda s:None,noop)
 try:
  for i in range(30):
   try:
    r=await b.dump('io.anonchat')
    ET.ElementTree(r).write(out/f'{int(time.time())}.xml',encoding='unicode')
    labels=a.system_labels(r)
    signals=sorted(x for x in labels if any(word in x.lower() for word in ['friend request','became friends','ended','now friends']))
    print(json.dumps({'sample':i,'signals':signals}),flush=True)
   except Exception as e:print(type(e).__name__,flush=True)
   await asyncio.sleep(2)
 finally:await b.close()
asyncio.run(main())
