import asyncio,time
from ayarlar import load
from rad.engine import Engine
async def main():
 def emit(event):
  if event['type']=='status':print(event['text'],flush=True)
 e=Engine(load(),emit)
 launches=[]
 original=e.android.shell
 async def shell(command):
  if command.startswith('am start'):
   launches.append((round(time.monotonic(),1),command))
   print('Foreground request:',command.split(' -n ')[-1],flush=True)
  return await original(command)
 e.android.shell=shell
 try:
  await e.android.connect()
  key=await e.telegram.open_existing('theurgist')
  print('Verified local test chat:',e.chats[key].title,flush=True)
  await e.connect('anonchat')
  await e.connect('telegram')
  started=time.monotonic()
  await asyncio.sleep(43)
  print('Observation seconds:',round(time.monotonic()-started),flush=True)
  print('Foreground request count:',len(launches),flush=True)
  print('Intervals:',[round(launches[i][0]-launches[i-1][0],1) for i in range(1,len(launches))],flush=True)
  print('Auto-reply:',e.auto,'watched:',len(e.android.watchers),flush=True)
  async with e.android.lock:
   print('App processes:',(await e.android.shell('pidof io.anonchat org.vidogram.messenger')).strip(),flush=True)
 finally:await e.close()
asyncio.run(main())
