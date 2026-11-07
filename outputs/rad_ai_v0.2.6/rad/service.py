"""Optional service mode using the same adapters and context engine as the GUI."""

import asyncio
from ayarlar import load
from .engine import Engine


async def run(auto_reply=False):
    async def ask(label,secret):
        raise ValueError("Authenticate in the control panel before headless use.")
    def emit(event):
        if event['type']=='status':
            print(event['text'],flush=True)
    engine=Engine(load(),emit,ask)
    engine.telegram.emit=None  # An unauthenticated service must not wait for an invisible QR.
    try:
        await asyncio.gather(engine.connect('telegram'),engine.connect('anonchat'))
        await engine.set_auto(auto_reply)
        await asyncio.Event().wait()
    finally:
        await engine.close()
