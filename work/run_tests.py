"""Run regressions with isolated logs; injected failures never pollute owner logs."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rad import diagnostics

with tempfile.TemporaryDirectory(prefix='rad-regression-') as folder:
    diagnostics.configure(Path(folder)/'rad_error.log')
    try:
        suite=unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1]/'tests'))
        result=unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        for handler in list(diagnostics.LOGGER.handlers):
            diagnostics.LOGGER.removeHandler(handler);handler.close()
sys.exit(0 if result.wasSuccessful() else 1)
