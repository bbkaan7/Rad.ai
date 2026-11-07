# Desktop Chat Alpha 0.5.0

English-only chat automation for Python 3.10+, Windows and the primary monitor.
Each trigger captures a region, reads it with OCR, requests an Ollama reply,
finds the textbox by image matching, types the reply and sends it.

## Setup

Open a terminal in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install Tesseract separately with `eng` language data. Set `TESSERACT_PATH` in
`settings.py` to its executable, for example:

```python
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Tesseract is a command-line tool; it does not need to stay open in another window.
Install and start Ollama, then download the model specified in `settings.py`:

```powershell
ollama pull llama3.2:1b
```

If the service is not running, start `ollama serve` in another terminal.

## Configuration and usage

1. Open the target chat on the primary monitor.
2. Set `CHAT_REGION` to include only the latest incoming message. Coordinates
   are physical screen pixels: left, top, width and height.
3. Add `textbox.png` and `send_btn.png` as described in `templates/README.md`.
4. Optionally restrict `SEARCH_REGION` to the chat window to reduce false matches.
5. Leave the textbox empty and keep the target chat visible while the bot runs.

```powershell
.\.venv\Scripts\python.exe main.py
```

- **F9 / Ctrl+Alt+9:** press and release all keys to run one cycle.
- **F10 / Ctrl+C:** stop. In-progress OCR/API calls must return or time out first.
- Moving the mouse to a primary-screen corner activates the PyAutoGUI fail-safe.
- Set `SEND_METHOD = "enter"` to send using Enter instead of image matching.
- The model prompt requests English-only replies. OCR uses `eng`.

## Diagnostics

Windows polls F9/F10/Ctrl/Alt/9 every 20 ms without installing a keyboard hook.
Presses that begin while busy are ignored. Some keyboards require Fn+F9.
Do not type the word F9 into PowerShell. If the `PS ...>` prompt returns, the bot
has exited and must be restarted.

Stop the running bot with Ctrl+C before running these commands:

```powershell
# Test keys without reading the screen or sending messages.
.\.venv\Scripts\python.exe main.py --key-test

# Run one real cycle after three seconds: this WILL type and send a reply.
.\.venv\Scripts\python.exe main.py --once

.\.venv\Scripts\python.exe main.py --version
.\.venv\Scripts\python.exe main.py --help
```

## Alpha limitations

- OCR does not reliably identify speakers or message bubbles. `MESSAGE_SELECTION = "region"`
  treats the entire region as one message. `"last_paragraph"` uses the last blank-line-separated
  OCR block; this heuristic can split messages or select the wrong text.
- Matching requires the same theme, scale and zoom as the reference images. Missing,
  unreadable, featureless or low-confidence references stop the cycle. Similar elements
  can cause false matches; narrow the search region.
- ASCII uses PyAutoGUI; other characters use Unicode keyboard input. Test your keyboard
  layout and application before regular use.
- The send button is located again after typing. If missing, the reply remains in the
  textbox. Check it after any failure before triggering again. Drafts are not erased.
- Duplicate messages, delivery and window identity are not tracked or verified.
- The full workflow has not been verified end to end against your chat application.
- System or third-party error details can follow the Windows display language.

## Files

- `main.py`: screen capture, OCR, API, matching, typing and hotkey handling.
- `settings.py`: regions, model, prompt, paths, thresholds and timing.
- `requirements.txt`: dependencies without a tested version lock.
- `VERSION` and `CHANGELOG.md`: release information.

## References

- [Ollama API](https://docs.ollama.com/api/generate)
- [PyAutoGUI](https://pyautogui.readthedocs.io/en/latest/keyboard.html)
- [OpenCV](https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html)
- [pytesseract](https://github.com/madmaze/pytesseract)
- [keyboard](https://github.com/boppreh/keyboard)
- [Windows key state](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getasynckeystate)
