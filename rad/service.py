"""Optional service mode using the same adapters and context engine as the GUI."""

import asyncio
from ayarlar import load
from .engine import Engine


async def run(auto_reply=False):
    from .diagnostics import install
    install(asyncio.get_running_loop())
    def emit(event):
        if event['type']=='status':
            print(event['text'],flush=True)
    engine=Engine(load(),emit)
    try:
        await asyncio.gather(engine.connect('telegram'),engine.connect('anonchat'))
        await engine.set_auto(auto_reply)
        await asyncio.Event().wait()
    finally:
        await engine.close()
