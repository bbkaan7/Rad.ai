"""Synthetic calibration checks; no desktop, account or model access."""

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from assistant.autocalibration import (anon_viewport, reference_match, header_region,
    telegram_left, infer_colors, labelled_control, CalibrationError, AutoCalibrator)


class AutomaticCalibrationTests(unittest.TestCase):
    def control_data(self, duplicate=False):
        return {'text':['Start searching']*(2 if duplicate else 1),
                'conf':[95,95], 'block_num':[1,2], 'par_num':[1,1],
                'line_num':[1,1], 'left':[20,20], 'top':[30,90],
                'width':[100,100], 'height':[20,20]}

    def test_label_fallback_excludes_header_and_returns_frame_coordinates(self):
        frame=np.zeros((600,400,3),dtype=np.uint8)
        with patch('assistant.autocalibration.pytesseract.image_to_data',
                   return_value=self.control_data()) as reader:
            self.assertEqual(labelled_control(frame,'search',[10,50,300,500]),
                             [30,280,100,20])
        self.assertEqual(reader.call_args.args[0].shape,(300,300,3))

    def test_duplicate_labels_stop(self):
        with patch('assistant.autocalibration.pytesseract.image_to_data',
                   return_value=self.control_data(True)):
            with self.assertRaises(CalibrationError):
                labelled_control(np.zeros((600,400,3),dtype=np.uint8),'search')

    def test_wrong_label_does_not_match(self):
        with patch('assistant.autocalibration.pytesseract.image_to_data',
                   return_value=self.control_data()):
            with self.assertRaises(CalibrationError):
                labelled_control(np.zeros((600,400,3),dtype=np.uint8),'next')

    def test_ambiguous_reference_never_falls_back_to_text(self):
        scanner=AutoCalibrator({'templates':{'search':'unused.png'}})
        with patch('assistant.autocalibration.reference_match',
                   side_effect=CalibrationError('More than one control matches.')):
            with patch('assistant.autocalibration.labelled_control') as fallback:
                with self.assertRaises(CalibrationError):
                    scanner.locate(np.zeros((600,400,3),dtype=np.uint8),'search',96)
                fallback.assert_not_called()

    def test_emulator_advertisement_is_excluded(self):
        frame=np.zeros((600,800,3),dtype=np.uint8)
        frame[40:590,300:700]=250
        frame[100:300,20:250]=255
        self.assertEqual(anon_viewport(frame),[300,40,400,550])

    def test_missing_application_surface_stops(self):
        with self.assertRaises(CalibrationError):
            anon_viewport(np.zeros((600,800,3),dtype=np.uint8))

    def test_moving_content_needs_no_saved_coordinates(self):
        frame=np.zeros((600,800,3),dtype=np.uint8)
        frame[40:590,20:420]=250
        self.assertEqual(anon_viewport(frame),[20,40,400,550])

    def test_template_scale_is_discovered(self):
        template=np.random.default_rng(17).integers(0,256,(28,30),dtype=np.uint8)
        scaled=cv2.resize(template,(36,34),interpolation=cv2.INTER_CUBIC)
        frame=np.zeros((240,320,3),dtype=np.uint8)
        frame[130:164,80:116]=scaled[:,:,None]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ref.png'
            cv2.imencode('.png',template)[1].tofile(path)
            box=reference_match(frame,path,96,96)
        self.assertEqual(box,[80,130,36,34])

    def test_competing_controls_are_not_clicked(self):
        template=np.random.default_rng(17).integers(0,256,(28,30),dtype=np.uint8)
        frame=np.zeros((240,320,3),dtype=np.uint8)
        frame[20:48,40:70]=template[:,:,None]
        frame[150:178,200:230]=template[:,:,None]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ref.png'
            cv2.imencode('.png',template)[1].tofile(path)
            with self.assertRaisesRegex(CalibrationError,'More than one'):
                reference_match(frame,path,96,96)

    def test_chat_list_divider_uses_anchor_center(self):
        frame=np.full((600,800,3),20,dtype=np.uint8)
        frame[:,261:]=40
        self.assertEqual(telegram_left(frame,[270,550,29,29],120),261)

    def test_no_divider_means_single_pane(self):
        frame=np.full((600,800,3),20,dtype=np.uint8)
        self.assertEqual(telegram_left(frame,[10,550,29,29],120),0)

    def test_header_ignores_online_status(self):
        data={'text':['Alice','online'],'conf':[95,96],'block_num':[1,1],
              'par_num':[1,1],'line_num':[1,2],'left':[10,10],'top':[5,25],
              'width':[45,50],'height':[12,12]}
        result=header_region(np.zeros((100,200,3),dtype=np.uint8),[20,20,150,60],96,
                             data_reader=lambda *a,**kw:data)
        self.assertEqual(result,[28,23,49,16])

    def test_unreadable_header_does_not_guess_recipient(self):
        data={'text':[]}
        with self.assertRaisesRegex(CalibrationError,'header is unreadable'):
            header_region(np.zeros((100,200,3),dtype=np.uint8),[0,0,200,80],96,
                          data_reader=lambda *a,**kw:data)

    def test_colors_are_learned_without_saved_palette(self):
        pane=np.full((400,400,3),[10,15,20],dtype=np.uint8)
        pane[220:255,8:190]=[51,38,22]
        pane[300:340,210:390]=[121,82,43]
        colors=infer_colors(pane)
        self.assertEqual(colors['incoming_color'],[51,38,22])
        self.assertEqual(colors['outgoing_color'],[121,82,43])

    def test_empty_pane_does_not_invent_messages(self):
        self.assertEqual(infer_colors(np.full((400,400,3),250,dtype=np.uint8)),{})

    def test_home_scan_does_not_reuse_previous_chat_identity(self):
        profile={'process_name':'HD-Player.exe','regions':{'identity':[1,2,3,4]},'templates':{}}
        scanner=AutoCalibrator(profile)
        def locate(frame,name,dpi,area=None):
            if name=='search': return [40,200,200,40]
            raise CalibrationError('missing')
        frame=np.full((600,400,3),250,dtype=np.uint8)
        with patch.object(scanner,'locate',side_effect=locate):
            result=scanner.analyze(frame,96)
        self.assertEqual(result['regions'],{})
        self.assertEqual(result['auto_state'],'home')
        self.assertIn('identity',profile['regions'])
