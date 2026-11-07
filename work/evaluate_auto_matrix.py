exec(compile(open(__file__.replace('evaluate_auto_matrix.py','evaluate_auto.py'),encoding='utf-8').read(), 'evaluate_auto.py','exec'))
for platform,filename in cases:
    original=cv2.imdecode(np.fromfile(workspace/'work/resume-backup/diagnostics'/filename,dtype=np.uint8),cv2.IMREAD_COLOR)
    for factor,dpi in ((.8,96),(1.2,144),(1.5,180)):
        frame=cv2.resize(original,None,fx=factor,fy=factor,interpolation=cv2.INTER_CUBIC)
        try:
            result=AutoCalibrator(cfg['profiles'][platform]).analyze(frame,dpi)
            print('SCALED',filename,factor,result['auto_state'],result['regions'],flush=True)
        except Exception as error:
            print('FAILED',filename,factor,str(error),flush=True)
    if platform=='anonchat':
        frame=original[:,282:].copy()
        result=AutoCalibrator(cfg['profiles'][platform]).analyze(frame,120)
        print('NO DOCK',filename,result['auto_state'],result['auto_viewport'],flush=True)
