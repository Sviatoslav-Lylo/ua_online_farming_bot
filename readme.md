# Miner Bot v4.3

A lightweight, headless State Machine bot for automated resource gathering in a 3D first-person mobile game environment.
It operates externally via ADB (Android Debug Bridge) and uses OpenCV template matching for camera alignment.

---

## Overview & Tech Specs

- **Game Resolution:** 2340 x 1080 (Landscape orientation)
- **Target Detection:** Uses templates/ore_template.png (detects the on-screen ore label). Additional per-ore templates used for classification: templates/gold_template.png, templates/silver_template.png, templates/bronze_template.png.
- **Execution Modes:**
  - **PC Mode:** Run from a computer connected over USB using ADB.
  - **Autonomous Mode:** Run on-device (Termux + local ADB).

### Virtual Controls & Coordinates
- **Joystick Center:** (360, 800) — forward swipe vector ends at (360, 640).
- **Interaction Button (OK):** (1500, 1000)
- **Harvest Button (Mine):** (1200, 570)
- **Notification dismiss (anti-block):** (1285, 720) — tapped periodically to clear popups.

---

## Core Algorithm (State Machine)

The bot continuously captures raw frames via `adb exec-out screencap -p` and transitions between four primary states: `STATE_SEARCHING`, `STATE_AIMING`, `STATE_WALKING`, and `STATE_COLLECTING`. The logic in `vision4.py` implements multi-template matching, center-priority selection, micro camera corrections, blind final steps, and harvest automation.

Key behaviors:
- When multiple matches exist, the bot chooses the match closest to the screen center (X = 1170).
- Classification after harvest uses per-ore templates and a red-background check to detect already-mined ("stolen") nodes.
- Statistics are accumulated in-memory and appended to timestamped CSV files in the `statistics/` folder.

---

## Data & Templates

- Templates directory: `templates/` — required files:
  - `ore_template.png` (silhouette/text search)
  - `gold_template.png`, `silver_template.png`, `bronze_template.png` (classification)
- Statistics directory: `statistics/` — the bot appends harvest events to `statistics/stats_<YYYYMMDD_HHMMSS>.csv` containing columns: `timestamp`, `ore_type`, and `runtime_minutes`.

---

## Prerequisites & Installation

### For PC Setup (Windows/Linux/Mac):
Make sure you have Python 3 and the required Python dependencies installed:
```bash
pip install opencv-python numpy pandas
```

- Ensure `adb` is installed and available on your PATH.
- Ensure the `templates/` and `statistics/` folders exist in the repository root and contain the required templates.

### Running
```bash
python vision4.py
```

- The script waits 5 seconds on start to allow you to switch to the target device window.
- Stop the bot with Ctrl+C.

---

## Notes

- The script writes per-run CSV logs to the `statistics/` folder. Keep an eye on disk usage if running long sessions.
- Adjust coordinates at the top of `vision4.py` if your device resolution or UI layout differs.

If you'd like, I can replace the original `readme.md` with this updated copy, or try the patch again.
