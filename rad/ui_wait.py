"""Wait for an observed UI condition, without replaying an input action."""
import asyncio
from .domain import LayoutError


async def read_until(reader,predicate,description,enabled=True,timeout=3):
    deadline=asyncio.get_running_loop().time()+timeout
    while True:
        root=await reader()
        if predicate(root):return root
        if not enabled:return root
        if asyncio.get_running_loop().time()>=deadline:
            raise LayoutError('Android did not finish '+description+'; no action was repeated.')
        await asyncio.sleep(.1)
