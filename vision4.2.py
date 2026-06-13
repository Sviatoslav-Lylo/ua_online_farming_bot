#!/usr/bin/env python3
import io
import os
import sys
import time
import struct
import subprocess
import cv2
import numpy as np

# ─────────────────────────────────────────────
#  COORDINATE AND PARAMETER SETTINGS
# ─────────────────────────────────────────────
SCREEN_W = 2340
SCREEN_H = 1080

CENTER_X = SCREEN_W // 2  # 1170
DEADZONE_X = 60           # Optimal for maintaining heading accuracy

OK_TAP_X, OK_TAP_Y = 1500, 1000
HARVEST_TAP_X, HARVEST_TAP_Y = 1200, 570

OK_COLOR_TARGET_BGR = (9, 185, 255)
OK_COLOR_TOLERANCE = 25

MOVE_CENTER_X = 360
MOVE_CENTER_Y = 800
MOVE_STEP_Y = 640  # Increased amplitude (was 720) to make steps longer

STATE_SEARCHING = "SEARCHING"  
STATE_AIMING    = "AIMING"     
STATE_WALKING   = "WALKING"    
STATE_COLLECTING = "COLLECTING" 

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
    """Reliable capture of PNG frames via exec-out on Windows."""
    try:
        res = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=3)
        if not res.stdout or len(res.stdout) < 100:
            print("[DEBUG] Error: received empty ADB stream.")
            return None
        
        img_buffer = np.frombuffer(res.stdout, dtype=np.uint8)
        img = cv2.imdecode(img_buffer, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"[DEBUG] Screenshot exception: {e}")
        return None

def find_ore_template(scene_img, template_img, threshold=0.70):
    """Searches for the ore_template.png pattern on the game screen."""
    if scene_img is None or template_img is None:
        return None
    
    res = cv2.matchTemplate(scene_img, template_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= threshold:
        template_w = template_img.shape[1]
        center_text_x = max_loc[0] + (template_w // 2)
        return center_text_x
    return None

def is_ok_button_visible(scene_img):
    """Checks for the presence of the OK button's yellow pixel."""
    if scene_img is None: return False
    try:
        pixel_bgr = scene_img[OK_TAP_Y, OK_TAP_X]
        return all(abs(int(p) - int(t)) <= OK_COLOR_TOLERANCE for p, t in zip(pixel_bgr, OK_COLOR_TARGET_BGR))
    except:
        return False

# ─────────────────────────────────────────────
#  CAMERA AND MOVEMENT CONTROL
# ─────────────────────────────────────────────

def camera_rotate_search():
    swipe(1600, 500, 1400, 500, duration_ms=250)

def camera_correct_left():
    swipe(1400, 500, 1450, 500, duration_ms=100)

def camera_correct_right():
    swipe(1600, 500, 1550, 500, duration_ms=100)

def make_forward_step():
    """Wide forward step using the joystick."""
    swipe(MOVE_CENTER_X, MOVE_CENTER_Y, MOVE_CENTER_X, MOVE_STEP_Y, duration_ms=400)

# ─────────────────────────────────────────────
#  MAIN BOT LOOP
# ─────────────────────────────────────────────

def main():
    print("[INIT] Starting in 5 seconds. Switch to the game window!")
    time.sleep(5)
    
    if not check_adb():
        print("[ERR] ADB device not found. Check connection.")
        sys.exit(1)
        
    template_img = cv2.imread('ore_template.png', cv2.IMREAD_COLOR)
    if template_img is None:
        print("[ERR] Failed to find 'ore_template.png'. Place it next to the script.")
        sys.exit(1)
        
    print("[INIT] Ready. Starting ore hunt!")
    
    state = STATE_SEARCHING
    search_rotation_count = 0
    blind_steps_count = 0
    
    while True:
        img = take_screenshot_cv()
        if img is None:
            print("[DEBUG] Screenshot not obtained, waiting...")
            time.sleep(0.2)
            continue
            
        if is_ok_button_visible(img):
            state = STATE_COLLECTING
            
        if state == STATE_SEARCHING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is not None:
                print(f"[SEARCH] Ore silhouette found (X: {ore_x})! Fixing course.")
                state = STATE_AIMING
                search_rotation_count = 0
                blind_steps_count = 0
            else:
                if search_rotation_count < 12:
                    print(f"[SEARCH] No text found. Scanning around ({search_rotation_count + 1}/12)...")
                    camera_rotate_search()
                    search_rotation_count += 1
                    time.sleep(0.5)  
                else:
                    print("[SEARCH] Full circle complete. No ore found, restarting scan.")
                    search_rotation_count = 0
                    time.sleep(0.5)
                    
        elif state == STATE_AIMING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is None:
                print("[AIM] Target lost during centering. Returning to scan.")
                state = STATE_SEARCHING
                continue
                
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound:
                print(f"[AIM] Ore left of center ({ore_x} < {left_bound}). Turning left.")
                camera_correct_left()
                time.sleep(0.2)
            elif ore_x > right_bound:
                print(f"[AIM] Ore right of center ({ore_x} > {right_bound}). Turning right.")
                camera_correct_right()
                time.sleep(0.2)
            else:
                print("[AIM] Target centered! Starting movement.")
                state = STATE_WALKING

        elif state == STATE_WALKING:
            ore_x = find_ore_template(img, template_img)
            
            if ore_x is None:
                print("[WALK] Text disappeared. Maybe we're close. Taking a final step...")
                make_forward_step()
                time.sleep(0.3)
                
                img_check = take_screenshot_cv()
                if is_ok_button_visible(img_check):
                    state = STATE_COLLECTING
                else:
                    blind_steps_count += 1
                    if blind_steps_count > 4:
                        print("[WALK] Button did not appear, target lost. Resetting.")
                        state = STATE_SEARCHING
                continue
                
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound or ore_x > right_bound:
                print("[WALK] Course drifted during walking. Correcting camera.")
                state = STATE_AIMING
                continue
                
            print("[WALK] Course correct. Step forward...")
            make_forward_step()
            time.sleep(0.1)

        elif state == STATE_COLLECTING:
            print("[HARVEST] Yellow OK button on screen! Starting collection.")
            tap(OK_TAP_X, OK_TAP_Y)
            time.sleep(0.3)
            
            print("[HARVEST] 15 quick harvest taps...")
            for _ in range(15):
                tap(HARVEST_TAP_X, HARVEST_TAP_Y)
                time.sleep(0.05)
                
            print("[HARVEST] Harvest complete. Waiting 4.5 sec for animation.")
            time.sleep(4.5)  
            state = STATE_SEARCHING

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[BOT] Bot stopped by user.")