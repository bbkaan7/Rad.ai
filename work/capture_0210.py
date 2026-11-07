import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ayarlar import load
from rad.adb import AndroidBridge
import xml.etree.ElementTree as ET
async def main():
 b=AndroidBridge(load());await b.connect()
 try:
  root=await b.dump('io.anonchat')
  path=Path('runtime/anon_0210.xml');path.parent.mkdir(exist_ok=True);ET.ElementTree(root).write(path,encoding='unicode')
  parents={c:p for p in root.iter() for c in p}
  for n in root.iter('node'):
   if n.get('package')=='io.anonchat':
    print(json.dumps({k:n.get(k) for k in ('class','resource-id','text','content-desc','bounds','clickable')}|{'parent':parents.get(n).get('class') if n in parents else None},ensure_ascii=True))
 finally:await b.close()
asyncio.run(main())
