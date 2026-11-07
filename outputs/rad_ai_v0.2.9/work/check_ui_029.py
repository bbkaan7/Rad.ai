import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from rad.gui import Panel
from ayarlar import VERSION
import customtkinter as ctk
p=Panel()
p.deiconify()
p.update()
assert VERSION=='0.2.9'
assert len(p.brand_images)==1
assert ('Telegram','Chats') in p.sections
assert hasattr(p,'window_icon')
for mode in ('Light','Dark','Light'):
 p.set_theme(mode)
 p.feed.canvas.configure(width=750,height=400)
 p.update()
 p.feed.draw()
 paws=p.feed.canvas.find_withtag('paw')
 assert bool(paws)==(mode=='Light'),(mode,len(paws))
 p.feed.set_messages([{'role':'user','text':'This is a local display test.'},{'role':'assistant','text':'A second message in a separate bubble.'}])
 p.update()
 assert len(p.feed.canvas.find_withtag('message'))==4
 assert p.feed.canvas.cget('background')==('#FFFCFB' if mode=='Light' else '#201C27')
 assert len(p.feed.canvas.find_withtag('paw'))>0 if mode=='Light' else not p.feed.canvas.find_withtag('paw')
print('Light/Dark, paw pattern, message rendering, logo and icon checks passed.')
for filename in ('rad-logo.png','rad-paw.png'):
 im=Image.open(Path('assets')/filename)
 assert im.mode=='RGBA' and im.getchannel('A').getextrema()==(0,255)
icon=Image.open('assets/rad-paw.ico')
assert (16,16) in icon.ico.sizes() and (256,256) in icon.ico.sizes()
print('Transparent assets and 7-size Windows ICO validated.')
p.worker.submit(p.worker.engine.close()).result(15)
p.worker.loop.call_soon_threadsafe(p.worker.loop.stop)
p.worker.thread.join(5)
p.destroy()

