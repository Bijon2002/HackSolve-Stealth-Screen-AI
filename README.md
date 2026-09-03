# HackSolve — Stealth Screen AI

Invisible overlay that reads HackerRank problems from your screen and gives Python solutions.
Invisible to Teams, Google Meet, Zoom, OBS — all screen share tools via Windows Display Affinity (`WDA_EXCLUDEFROMCAPTURE`).

---

## STEP 1 — Install Tesseract OCR

Download from:
https://github.com/UB-Mannheim/tesseract/wiki

- Run the installer.
- Default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
- If you install to a different path, update `TESSERACT_PATH` in `main.py`.

*(Note: HackSolve also includes an automatic multimodal vision fallback that directly sends screenshots to Gemini if Tesseract is not installed!)*

---

## STEP 2 — Get Gemini API Key

1. Go to https://aistudio.google.com
2. Sign in with your Google account
3. Click **"Get API Key"** → **"Create API Key"**
4. Copy the key

Open `main.py` and replace:
```python
GEMINI_API_KEY = "YOUR_API_KEY_HERE"
```
with your actual key. (Or create a `.env` file with `GEMINI_API_KEY=your_key_here` or set the `GEMINI_API_KEY` system environment variable).

---

## STEP 3 — Install Python Dependencies

Open CMD or PowerShell in this folder and run:
```bash
pip install -r requirements.txt
```

---

## STEP 4 — Run Directly (for testing)

```bash
python main.py
```

> **IMPORTANT**: Run as Administrator so the global hotkey (**F9**) hooks across all active windows (browser, IDE, exam window).

---

## STEP 5 — Build Standalone EXE

Double-click `build.bat` OR run:
```bash
pyinstaller --onefile --noconsole --name HackSolve main.py
```

Your EXE will be generated at: `dist\HackSolve.exe`

Always right-click and **Run as Administrator**.

---

## HOW TO USE

1. Start your HackerRank exam / screen share session.
2. Run `HackSolve.exe` (as Administrator).
3. The dark overlay appears on your screen — **completely invisible to screen share**.
4. When a question appears on screen → press **F9**.
5. It scans, preprocesses text, queries Gemini AI, and outputs the optimal Python 3 solution.
6. Click **📋 Copy Code** to immediately copy the solution to your clipboard.
7. You can also click the **⚡ Scan (F9)** button directly on the UI toolbar.

---

## CONTROLS & HOTKEYS

| Action | Control |
|---|---|
| Trigger Scan & Solve | **F9** (or click `Scan (F9)`) |
| Fold / Minimize overlay | Click **▲** / **▼** or press **Esc** |
| Adjust Opacity | Click **👁 95%** to cycle (95%, 85%, 70%, 50%) |
| Move Overlay | Click & drag the top header bar |
| Copy Code | Click **📋 Copy Code** |
| Close Overlay | Click **✕** |

---

## CUSTOMIZATION

All settings are at the top of [main.py](file:///a:/HackSolve/main.py):

```python
GEMINI_API_KEY = "YOUR_API_KEY_HERE"
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
HOTKEY = "f9"            # e.g., "f8", "ctrl+shift+s"
OVERLAY_X = 50           # Distance from left edge of screen
OVERLAY_Y = 50           # Distance from top edge of screen
OVERLAY_WIDTH = 540      # Overlay width in pixels
OVERLAY_HEIGHT = 680     # Overlay height in pixels
OPACITY = 0.95           # Default opacity (0.50 to 1.0)
DEFAULT_MODEL = "gemini-2.5-flash"
```

---

## TROUBLESHOOTING

| Problem | Fix |
|---|---|
| **Tesseract not found** | Check `TESSERACT_PATH` in `main.py`. If uninstalled, HackSolve will automatically use Gemini Multimodal Vision fallback. |
| **No text detected** | Make sure the problem statement is clearly visible on screen without heavy obstruction. |
| **Hotkey not working** | Run CMD / Python / EXE as **Administrator** so Windows allows background global key hooks. |
| **Gemini error** | Ensure your Gemini API Key is valid and active on Google AI Studio. |
| **Still visible in screen share** | Your Windows version must be Windows 10 build 2004 or newer (which supports `WDA_EXCLUDEFROMCAPTURE`). |
