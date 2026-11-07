from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rad.domain import xml_root
root=xml_root(Path('runtime/anon-chat.xml').read_text(encoding='utf-8'))
def walk(node,depth=0):
    print('  '*depth+str({k:node.get(k) for k in ['class','text','content-desc','bounds','clickable']}))
    for child in node:
        walk(child,depth+1)
walk(root)
