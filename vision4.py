#!/usr/bin/env python3
import io
import os
import sys
import time
import struct
import subprocess
import cv2
import numpy as np
from PIL import Image

# ─────────────────────────────────────────────
#  COORDINATE AND PARAMETER SETTINGS
# ─────────────────────────────────────────────
SCREEN_W = 2340
SCREEN_H = 1080

# Screen center line and allowed deadzone error
CENTER_X = SCREEN_W // 2  # 1170
DEADZONE_X = 60           # Optimal for maintaining heading accuracy

# Coordinates from fff1.py
OK_TAP_X, OK_TAP_Y = 1500, 1000
HARVEST_TAP_X, HARVEST_TAP_Y = 1200, 570

# OK button color in BGR format (OpenCV uses BGR instead of RGB)
# In fff1.py RGB=(255, 185, 9) -> BGR=(9, 185, 255)
OK_COLOR_TARGET_BGR = (9, 185, 255)
OK_COLOR_TOLERANCE = 25

# Virtual movement joystick
MOVE_CENTER_X = 360
MOVE_CENTER_Y = 800
MOVE_STEP_Y = 720  # Micro-step forward point

# State machine (bot states)
STATE_SEARCHING = "SEARCHING"  # Rotate and search for the template
STATE_AIMING    = "AIMING"     # Center the camera on the text
STATE_WALKING   = "WALKING"    # Move forward with micro-steps
STATE_COLLECTING = "COLLECTING" # Press OK and collect

# ─────────────────────────────────────────────
#  UTILITY FUNCTIONS (ADB AND GRAPHICS)
# ─────────────────────────────────────────────

def check_adb():
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        return any("\tdevice" in l for l in res.stdout.splitlines() if l.strip() and not l.startswith("List"))
    except: return False

def tap(x, y):
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)], capture_output=True)

def swipe(x1, y1, x2, y2, duration_ms):
    subprocess.run(["adb", "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)], capture_output=True)

def take_screenshot_cv():
    """Captures a screenshot via adb exec-out and returns an OpenCV BGR image."""
    try:
        raw = subprocess.run(["adb", "exec-out", "screencap"], capture_output=True, timeout=3).stdout
        if not raw or len(raw) < 12: return None
        width = int.from_bytes(raw[0:4], "little")
        height = int.from_bytes(raw[4:8], "little")
        pixel_data = raw[12:]
        
        if len(pixel_data) >= width * height * 4:
            img = np.frombuffer(pixel_data, dtype=np.uint8).reshape((height, width, 4))
            return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        else:
            # Fallback to a slower decode if the byte array is corrupt
            return cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    except:
        return None

def find_ore_template(scene_img, template_img, threshold=0.75):
    """Searches for the ore_template.png template on the game screen."""
    if scene_img is None or template_img is None:
        return None
    
    res = cv2.matchTemplate(scene_img, template_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= threshold:
        # Compute the center X coordinate of the found template
        template_w = template_img.shape[1]
        center_text_x = max_loc[0] + (template_w // 2)
        return center_text_x
    return None

def is_ok_button_visible(scene_img):
    """Checks whether the yellow OK button pixel is present with tolerance."""
    if scene_img is None: return False
    try:
        # Get the color at the fixed point (OpenCV indexes as Y, X)
        pixel_bgr = scene_img[OK_TAP_Y, OK_TAP_X]
        return all(abs(int(p) - int(t)) <= OK_COLOR_TOLERANCE for p, t in zip(pixel_bgr, OK_COLOR_TARGET_BGR))
    except:
        return False

# ─────────────────────────────────────────────
#  CAMERA AND MOVEMENT CONTROL
# ─────────────────────────────────────────────

def camera_rotate_search():
    """Rotate camera right to scan the environment (swipe left)."""
    swipe(1600, 500, 1400, 500, duration_ms=250)

def camera_correct_left():
    """Micro-adjust camera left (swipe right)."""
    swipe(1400, 500, 1460, 500, duration_ms=100)

def camera_correct_right():
    """Micro-adjust camera right (swipe left)."""
    swipe(1600, 500, 1540, 500, duration_ms=100)

def make_micro_step():
    """Take a micro-step forward using the joystick."""
    swipe(MOVE_CENTER_X, MOVE_CENTER_Y, MOVE_CENTER_X, MOVE_STEP_Y, duration_ms=350)

# ─────────────────────────────────────────────
#  MAIN BOT LOOP
# ─────────────────────────────────────────────

def main():
    print("[INIT] Starting in 5 seconds. Switch to the game window!")
    time.sleep(5)
    
    if not check_adb():
        print("[ERR] ADB device not found. Check cable or emulator.")
        sys.exit(1)
        
    # Load the template
    template_img = cv2.imread('ore_template.png', cv2.IMREAD_COLOR)
    if template_img is None:
        print("[ERR] Failed to load 'ore_template.png'. Place the file next to the script.")
        sys.exit(1)
        
    print("[INIT] Ready. Starting ore hunt!")
    
    state = STATE_SEARCHING
    search_rotation_count = 0
    blind_steps_count = 0
    
    while True:
        img = take_screenshot_cv()
        if img is None:
            time.sleep(0.1)
            continue
            
        # PRIORITY: OK button check is available in any movement state
        if is_ok_button_visible(img):
            state = STATE_COLLECTING
            
        # State machine logic implementation
        if state == STATE_SEARCHING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is not None:
                print(f"[SEARCH] Ore silhouette found! Switching to aiming.")
                state = STATE_AIMING
                search_rotation_count = 0
                blind_steps_count = 0
            else:
                if search_rotation_count < 12:
                    print(f"[SEARCH] No ore found. Scanning ({search_rotation_count + 1}/12)...")
                    camera_rotate_search()
                    search_rotation_count += 1
                    time.sleep(0.4)  # Time for camera stabilization after turning
                else:
                    print("[SEARCH] Full circle scanned, nothing found. Taking blind steps.")
                    for _ in range(3): make_micro_step()
                    search_rotation_count = 0
                    
        elif state == STATE_AIMING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is None:
                print("[AIM] Target lost while aiming. Returning to search.")
                state = STATE_SEARCHING
                continue
                
            # Check position relative to the screen center
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound:
                print(f"[AIM] Ore left of center ({ore_x} < {left_bound}). Adjusting left.")
                camera_correct_left()
                time.sleep(0.15)
            elif ore_x > right_bound:
                print(f"[AIM] Ore right of center ({ore_x} > {right_bound}). Adjusting right.")
                camera_correct_right()
                time.sleep(0.15)
            else:
                print("[AIM] Target centered! Starting approach.")
                state = STATE_WALKING

        elif state == STATE_WALKING:
            ore_x = find_ore_template(img, template_img)
            
            if ore_x is None:
                # The text disappeared. If we were approaching correctly, we may be very close
                print("[WALK] Text disappeared. Maybe we're close. Taking final steps...")
                make_micro_step()
                time.sleep(0.2)
                
                # Check again if the OK button appeared
                img_check = take_screenshot_cv()
                if is_ok_button_visible(img_check):
                    state = STATE_COLLECTING
                else:
                    blind_steps_count += 1
                    if blind_steps_count > 4: # Prevent endless walking into a wall
                        print("[WALK] OK button did not appear, ore lost. Resetting.")
                        state = STATE_SEARCHING
                continue
                
            # Check if the course drifted during movement
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound or ore_x > right_bound:
                print("[WALK] Course drifted during walk. Returning to camera correction.")
                state = STATE_AIMING
                continue
                
            # If all is well, step forward
            print("[WALK] Text centered. Step forward...")
            make_micro_step()
            time.sleep(0.1)

        elif state == STATE_COLLECTING:
            print("[HARVEST] Yellow OK button on screen! Stopping to collect.")
            # Tap OK
            tap(OK_TAP_X, OK_TAP_Y)
            time.sleep(0.3)
            
            # 15 quick taps to collect ore
            print("[HARVEST] Performing 15 quick harvest taps...")
            for _ in range(15):
                tap(HARVEST_TAP_X, HARVEST_TAP_Y)
                time.sleep(0.05)
                
            print("[HARVEST] Harvest complete. Waiting for animation and searching again.")
            time.sleep(4.5)  # Time for remaining ore graphics to clear
            state = STATE_SEARCHING

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[BOT] Bot stopped by user.")