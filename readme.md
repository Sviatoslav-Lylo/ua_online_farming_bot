# Miner Bot v4.3

A lightweight, headless State Machine bot for automated resource gathering in a 3D first-person mobile game environment. 
It operates externally via ADB (Android Debug Bridge) and uses OpenCV Template Matching for precise camera alignment.

---

## Overview & Tech Specs

* **Game Resolution:** 2340 x 1080 (Landscape orientation)
* **Target Detection:** Uses ore_template.png (a small crop of the text "Руда"). This completely bypasses standard color-filtering (HSV) failures caused by dynamic day/night light cycles.
* **Execution Environments:**
  * **PC Mode:** Computer-driven automation via USB cable.
  * **Autonomous Mode:** Runs entirely on the Android device via Termux using Local ADB (127.0.0.1).

### Virtual Controls Configuration
* **Joystick Center:** (360, 800) -> Forward Movement Vector: (360, 640)
* **Interaction Button (OK):** (1500, 1000)
* **Harvest Button (Mine):** (1200, 570)

---

## Core Algorithm (State Machine)

The bot operates as a continuous image-processing loop, fetching raw screen frames via adb exec-out screencap -p directly into memory. 
It transitions dynamically between 4 core states:

[ SEARCHING ] ──(ore detected)──> [ AIMING ] ──(centered)──> [ WALKING ]
▲                                                           │
│                                                     (prompt triggers)
│                                                           ▼
[ STATE_RESET ] <────────────────────────────────────────── [ COLLECTING ]

### 1. STATE_SEARCHING
The bot scans the current frame for ore_template.png. 
If no match passes the threshold, it executes a short forward step and a micro-rotation of the camera to scan the horizon. 
Once detected, it locks onto the coordinates and transitions to AIMING.

### 2. STATE_AIMING (Multi-Target Fix)
If multiple "Ore" text elements are present on screen, the bot utilizes numpy to locate all active matches. 
It filters them and selects the one closest to the vertical center of the screen (X = 1170). 
The camera performs micro-adjustments left or right until the target enters the precise deadzone corridor.

### 3. STATE_WALKING
Once the target is perfectly aligned, the bot engages the virtual joystick using long ADB swipe durations (1.75s) to advance rapidly. 
It re-verifies alignment after each step. 
If the text disappears as the player gets too close, it takes a final blind step to trigger the interaction prompt.

### 4. STATE_COLLECTING
This state holds the highest execution priority. 
The moment the targeted pixel on the "OK" button area turns yellow, all movement ceases. 
The bot immediately taps "OK", executes 15 rapid harvesting taps on the action button, tracks real-time efficiency metrics (Ores/Min), and resets back to SEARCHING.

---

## Anti-Stuck Protection

If the target text disappears or the player gets blocked by geometric obstacles during the WALKING phase, a failsafe counter monitors execution. 
If the "OK" prompt fails to appear within 3 consecutive frames, the bot forces a state reset back to STATE_SEARCHING to find another resource node.

---

## Prerequisites & Installation

### For PC Setup (Windows/Linux/Mac):
Make sure you have Python 3 and the required dependencies installed:
```bash
pip install opencv-python numpy pillow