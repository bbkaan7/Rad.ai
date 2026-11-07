"""Bounded hotfix diagnostics with traceback frames and non-content local summaries."""
import asyncio
from contextvars import ContextVar
import hashlib
from functools import wraps
import json
import logging
import os
import re
import platform
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading
import traceback
from uuid import uuid4
from ayarlar import ROOT, VERSION

LOGGER=logging.getLogger('rad.errors')
LOGGER.propagate=False
LOGGER.setLevel(logging.ERROR)
_lock=threading.RLock()
LOG_PATH=ROOT/'runtime'/'rad_error.log'
OPERATION=ContextVar('rad_operation',default=None)
STEPS=ContextVar('rad_steps',default=())
RUN_ID=uuid4().hex[:12]
BUILD_ID=None
SETTINGS_ID=None
SENSITIVE=re.compile(r'password|secret|token|api.?key|api.?hash|phone|code|credential|^pin$',re.I)
CONTENT=re.compile(r'text|message|prompt|content|reply|bio|title|identity|command|xml',re.I)


def configure(path=None):
    global LOG_PATH, BUILD_ID, SETTINGS_ID
    with _lock:
        target=Path(path) if path else LOG_PATH
        if LOGGER.handlers and target==LOG_PATH:return LOG_PATH
        if BUILD_ID is None:
            try:
                digest=hashlib.sha256()
                sources=sorted((ROOT/'rad').glob('*.py'))+[ROOT/'main.py',ROOT/'ayarlar.py']
                sources+=sorted((ROOT/'android-helper').rglob('*.java'))+sorted((ROOT/'android-helper').rglob('*.xml'))
                for source in sources:
                    digest.update(source.name.encode());digest.update(source.read_bytes())
                BUILD_ID=digest.hexdigest()[:16]
                SETTINGS_ID=hashlib.sha256((ROOT/'settings.json').read_bytes()).hexdigest()[:16]
            except OSError:BUILD_ID='unavailable'
        target.parent.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(target,maxBytes=5_000_000,backupCount=3,encoding='utf-8')
        formatter=logging.Formatter('%(asctime)sZ %(message)s',datefmt='%Y-%m-%dT%H:%M:%S')
        formatter.converter=time.gmtime
        handler.setFormatter(formatter)
        for old in list(LOGGER.handlers):
            LOGGER.removeHandler(old);old.close()
        LOGGER.addHandler(handler)
        LOG_PATH=target
        return target


def summary(value):
    if value is None or type(value) in (bool,int,float):return value
    if isinstance(value,str):return {'type':'str','length':len(value)}
    if isinstance(value,(list,tuple,dict,set,bytes)):
        return {'type':type(value).__name__,'length':len(value)}
    return {'type':type(value).__name__}


def redact(text,values=()):
    for value in sorted(set(values),key=len,reverse=True):
        if len(value)>=3:text=text.replace(value,'[redacted]')
    text=re.sub(r'(?i)(bearer\s+)[\w.\-]+',r'\1[redacted]',text)
    text=re.sub(r'(?i)((?:password|token|api[_-]?key|api[_-]?hash|secret)\s*[=:]\s*)[^\s,;&]+',r'\1[redacted]',text)
    text=re.sub(r'(https?://[^\s?]+)\?[^\s]+',r'\1?[redacted]',text)
    return text[:2000]


def state_value(name,value):
    if SENSITIVE.search(name):return '[redacted]'
    if name in {'key','chat_key','person_id'} and isinstance(value,str):
        return 'sha256:'+hashlib.sha256(value.encode()).hexdigest()[:12]
    if name in {'package','action','operation','selector','phase','request_state'} and isinstance(value,str):
        return redact(value)
    return summary(value)


def step(stage,**state):
    """Keep the last 30 non-content steps of this async operation for its error record."""
    item={'stage':stage,'time':round(time.monotonic(),3),
          'state':{name:state_value(name,value) for name,value in state.items()}}
    STEPS.set((STEPS.get()+(item,))[-30:])


def record(stage,error,**state):
    """Log variable names, types and safe scalar values, never arbitrary object reprs."""
    try:
        configure()
        frames=[];sensitive=[];causes=[];cause=error;seen=set()
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause));causes.append(cause)
            tb=cause.__traceback__
            while tb:
                frame=tb.tb_frame
                variables=dict(frame.f_locals)
                sensitive.extend(str(v) for k,v in variables.items() if
                    (SENSITIVE.search(k) or CONTENT.search(k)) and isinstance(v,(str,int)))
                frames.append({'file':frame.f_code.co_filename,'line':tb.tb_lineno,
                    'function':frame.f_code.co_name,'cause_type':type(cause).__name__,
                    'variables':{k:state_value(k,v) for k,v in variables.items()}})
                tb=tb.tb_next
            cause=cause.__cause__ or cause.__context__
        # Stack locations are sufficient for a hotfix without copying exception text
        # that a server could populate with credentials or customer content.
        chain=[]
        for cause in causes:
            chain.append({'type':type(cause).__name__,
                'stack':[{'file':f.filename,'line':f.lineno,'function':f.name}
                         for f in traceback.extract_tb(cause.__traceback__)],
                'message':redact(str(cause),sensitive)})
        event={'schema':1,'id':uuid4().hex[:12],'run_id':RUN_ID,'pid':os.getpid(),
            'version':VERSION,'build_id':BUILD_ID,'settings_id':SETTINGS_ID,'stage':stage,
            'operation_id':getattr(error,'rad_operation_id',None) or OPERATION.get() or uuid4().hex[:12],
            'error_type':type(error).__name__,'thread':threading.current_thread().name,
            'python':platform.python_version(),'os':platform.system(),
            'state':{k:state_value(k,v) for k,v in state.items()},'frames':frames,'chain':chain,
            'recent_steps':getattr(error,'rad_steps',None) or STEPS.get()}
        android_frames=getattr(error,'android_frames',None)
        if isinstance(android_frames,list):
            event['android_frames']=[{key:redact(str(frame.get(key,'')))[:200]
                for key in ('file','line','function')} for frame in android_frames[:20] if isinstance(frame,dict)]
        LOGGER.error(json.dumps(event,ensure_ascii=True))
        return event['id']
    except Exception:
        # A full/unwritable disk must not crash a polling or GUI callback.
        try:sys.stderr.write('Rad.ai could not write its error log. Check runtime directory permissions.\n')
        except Exception:pass
        return None


def logged(stage):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args,**kwargs):
            root_operation=OPERATION.get() is None
            trace_token=STEPS.set(()) if root_operation else None
            token=OPERATION.set(OPERATION.get() or uuid4().hex[:12])
            step(stage+'.start')
            try:
                result=await function(*args,**kwargs)
                step(stage+'.complete')
                return result
            except Exception as error:
                if type(error).__name__!='ForegroundDeferred':
                    error.rad_operation_id=OPERATION.get()
                    error.rad_steps=STEPS.get()
                    record(stage,error)
                raise
            finally:
                OPERATION.reset(token)
                if trace_token is not None:STEPS.reset(trace_token)
        return wrapped
    return decorate


def install(loop=None):
    try:configure()
    except Exception as error:record('logging.setup',error)
    def unhandled(kind,error,tb):
        record('python.unhandled',error.with_traceback(tb))
        sys.__excepthook__(kind,error,tb)
    sys.excepthook=unhandled
    threading.excepthook=lambda args:record('thread.unhandled',args.exc_value.with_traceback(args.exc_traceback))
    if loop is not None:
        loop.set_exception_handler(lambda loop,context:record('asyncio.unhandled',
            context.get('exception') or RuntimeError('Async task failed'),task=context.get('task')))
