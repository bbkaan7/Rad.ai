"""Local model smoke test; does not read or control the desktop."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent / 'outputs' / 'chat_assistant_v0.2.0'
sys.path.insert(0, str(root))
from assistant.config import load
from assistant.core import Conversation, Observation
from assistant.model import Ollama
from assistant.diagnostics import check_installation
cfg=load()
print(check_installation(cfg))
session=Conversation('test', 'local-smoke-test')
print('Greeting:', session.prepare_greeting(Observation('local-smoke-test',''), Ollama(cfg)))
assert not session.history and not session.uncertain
print('No send performed; history remains empty.')
