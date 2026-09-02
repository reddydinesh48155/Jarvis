# JARVIS

## Run from the project folder

Double-click `run_jarvis.bat` or run this in PowerShell:

```powershell
cd "C:\Users\reddy\Downloads\jarvis"
.\run_jarvis.bat
```

## Requirements

This project expects a local Python virtual environment at `.venv`.

If it does not exist, create it with:

```powershell
cd "C:\Users\reddy\Downloads\jarvis"
py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

## Notes

- `PyAudio` requires Microsoft C++ Build Tools on Windows.
- If installation fails, use Python 3.12 and ensure the Visual C++ build tools are installed.
- The app also expects Ollama to be running locally at `http://localhost:11434` for AI responses.
- JARVIS speaks every generated terminal message, including listening, processing, confirmations, and errors. The recognized user command shown after `You:` is intentionally not spoken.
- Saying `Jarvis, open ChatGPT` speaks `Opening ChatGPT.` before opening `https://chatgpt.com`.

## Optional configuration

Set these environment variables before starting JARVIS:

- `JARVIS_MICROPHONE_INDEX` selects a specific microphone. The default is the system microphone.
- `JARVIS_STT_LANGUAGE` changes Google recognition language; the default is `en-IN`.
- `JARVIS_STT_PROVIDER` accepts `google` (default), `sphinx`, or `vosk`.
- `JARVIS_REQUIRE_WAKE_WORD=1` makes the main loop require `Jarvis` before each command.

The Google provider needs internet access. Sphinx and Vosk are offline options, but their corresponding SpeechRecognition engine/model packages must be installed separately.

## Adding a command

Add another `router.register(...)` entry inside `create_command_router()` in `MYJARIVS/main.py`, providing trigger phrase(s), a spoken confirmation, and an action function. Triggers use case-insensitive substring matching, so `open youtube please` matches `open youtube`.
