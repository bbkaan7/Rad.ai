"""A cross-process lease prevents two panels from driving one emulator."""
import hashlib
import os
from pathlib import Path
import tempfile


class DeviceLease:
    def __init__(self,identity):
        name=hashlib.sha256(identity.encode()).hexdigest()[:24]
        self.path=Path(tempfile.gettempdir())/('rad-ai-device-'+name+'.lock')
        self.file=None

    def acquire(self):
        if self.file:
            return
        handle=open(self.path,'a+b')
        handle.seek(0,os.SEEK_END)
        if handle.tell()==0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,BlockingIOError) as error:
            handle.close()
            raise ValueError('Another Rad.ai process is controlling this emulator. Close its connections first.') from error
        self.file=handle

    def close(self):
        if not self.file:
            return
        try:
            self.file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file=None
