import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ayarlar import Settings
from rad.llm import Ollama

async def main():
    model=Ollama(Settings())
    try:
        reply=await model.reply([{'role':'user','content':'Hello, this is a local integration test. Reply briefly.'}])
        print('Local async Ollama integration:',reply)
    finally:
        await model.close()

asyncio.run(main())
