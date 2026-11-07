from pathlib import Path
import json
root=Path(__file__).resolve().parent.parent/'outputs/rad_ai_v0.2.4'
cfg=json.loads((root/'profiles.json').read_text())
vision={}
for name,p in cfg['profiles'].items():
    vision[name]={key:p[key] for key in ('process_name','templates','template_dpi')}
    vision[name].update(window_title='',size=None,regions={},auto_calibration=True,read_mode='bubbles',send_method='button')
    if name=='telegram':
        vision[name].update(text_source='clipboard',timestamp_inside=True)
cfg['profiles']=vision
cfg['debug_capture']=False
(root/'vision_profiles.json').write_text(json.dumps(vision,indent=2),encoding='utf-8')
(root/'profiles.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
