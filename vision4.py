#!/usr/bin/env python3
import csv
from datetime import datetime
import io
import os
import sys
import time
import struct
import subprocess
import cv2
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────
#  COORDINATE AND PARAMETER SETTINGS
# ─────────────────────────────────────────────
SCREEN_W = 2340
SCREEN_H = 1080

CENTER_X = SCREEN_W // 2  # 1170
DEADZONE_X = 100           # Heading accuracy

OK_TAP_X, OK_TAP_Y = 1500, 1000
HARVEST_TAP_X, HARVEST_TAP_Y = 1200, 570

OK_COLOR_TARGET_BGR = (9, 185, 255)
OK_COLOR_TOLERANCE = 25

# ORE CLASSIFICATION 
ROI_X1, ROI_Y1 = 1215, 960 # Range of interest (ROI)
ROI_X2, ROI_Y2 = 1400, 1030

RED_BACKGROUND_TARGET_BGR = (40, 40, 240) # coordinates for red background are the same as for "ok" button
RED_BACKGROUND_TOLERANCE = 25

ORE_TEMPLATES = {
    "gold": cv2.imread("gold_template.png", cv2.IMREAD_COLOR),
    "silver": cv2.imread("silver_template.png", cv2.IMREAD_COLOR),
    "bronze": cv2.imread("bronze_template.png", cv2.IMREAD_COLOR)
}
CSV_FILENAME = "stats.csv"

ORE_PRICES = {
    "gold": 50000,      
    "silver": 15000,
    "bronze": 1000,
    "stolen": 0,
    "unknown": 0
}

MOVE_CENTER_X = 360
MOVE_CENTER_Y = 800
MOVE_STEP_Y = 640  

STATE_SEARCHING = "SEARCHING"  
STATE_AIMING    = "AIMING"     
STATE_WALKING   = "WALKING"    
STATE_COLLECTING = "COLLECTING" 

UNWANTED_NOTIFICATION_X = 1285
UNWANTED_NOTIFICATION_Y = 720
NOTIFICATION_INTERVAL_SEC = 180

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
    """Reliable capture of PNG frame via exec-out on Windows."""
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
    if scene_img is None or template_img is None:
        return None
    
    res = cv2.matchTemplate(scene_img, template_img, cv2.TM_CCOEFF_NORMED)
    
    # ALL pixels where match is above the threshold
    loc = np.where(res >= threshold)
    x_indices = loc[1] # coordinates on the X axis
    
    if len(x_indices) == 0:
        return None
        
    template_w = template_img.shape[1]
    best_center_x = None
    min_dist = float('inf')
    
    # find the closest match to the center
    for x in x_indices:
        center_text_x = x + (template_w // 2)
        dist = abs(center_text_x - CENTER_X)
        
        if dist < min_dist:
            min_dist = dist
            best_center_x = center_text_x
            
    return best_center_x

def is_ok_button_visible(scene_img):
    if scene_img is None: return False
    try:
        pixel_bgr = scene_img[OK_TAP_Y, OK_TAP_X]
        return all(abs(int(p) - int(t)) <= OK_COLOR_TOLERANCE for p, t in zip(pixel_bgr, OK_COLOR_TARGET_BGR))
    except:
        return False

def classify_and_log_ore(scene_img, start_time, df):
    if scene_img is None:
        return

    # Step 1: Check for stolen state via pixel color first
    pixel_bgr = scene_img[(ROI_Y1 + ROI_Y2) // 2, (ROI_X1 + ROI_X2) // 2]
    is_red = all(abs(int(p) - int(t)) <= RED_BACKGROUND_TOLERANCE for p, t in zip(pixel_bgr, RED_BACKGROUND_TARGET_BGR))
    
    if is_red:
        ore_kind = "stolen"
        print("[ANALYSIS] Ore was already mined by someone else (Red background).")
    else:
        # Step 2: Crop the banner region for text matching
        roi = scene_img[ROI_Y1:ROI_Y2, ROI_X1:ROI_X2]
        
        best_score = 0.0
        ore_kind = "unknown"
        
        # Step 3: Run multi-template comparison loop
        for name, template in ORE_TEMPLATES.items():
            if template is None:
                continue
            res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val > best_score:
                best_score = max_val
                ore_kind = name

        # Enforce threshold verification
        if best_score < 0.75:
            ore_kind = "unknown"
            print(f"[ANALYSIS] Classification failed. Best match was too low: {best_score:.2f}")
        else:
            print(f"[ANALYSIS] Successfully identified ore type: {ore_kind.upper()} (Match: {best_score:.2f})")
        
        df.at[ore_kind, 'QUANTITY'] += 1

    # Step 4: Write metadata to CSV file
    file_exists = os.path.exists(CSV_FILENAME)
    try:
        with open(CSV_FILENAME, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            
            # Write column headers only if creating a new file
            if not file_exists:
                writer.writerow(["timestamp", "ore_type", "runtime_minutes"])
                
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            runtime_mins = (time.perf_counter() - start_time) / 60
            
            writer.writerow([timestamp, ore_kind, f"{runtime_mins:.2f}"])
            print(f"[DATA] Saved entry to {CSV_FILENAME}")
    except Exception as e:
        print(f"[DATA] Error writing to CSV: {e}")

# ─────────────────────────────────────────────
#  CAMERA AND MOVEMENT CONTROL
# ─────────────────────────────────────────────

def camera_rotate_search():
    swipe(1600, 500, 1400, 500, duration_ms=250)

def camera_correct_left():
    swipe(1600, 500, 1550, 500, duration_ms=100)

def camera_correct_right():
    swipe(1400, 500, 1450, 500, duration_ms=100)

def make_forward_step(duration):
    swipe(MOVE_CENTER_X, MOVE_CENTER_Y, MOVE_CENTER_X, MOVE_STEP_Y, duration_ms=duration)

def camera_tilt_down():
    swipe(1500, 450, 1500, 550, duration_ms=150)

# ─────────────────────────────────────────────
#  MAIN BOT LOOP
# ─────────────────────────────────────────────

def main():
    TOTAL_ORES_COUNTER = 0
    ORES_COUNTER_DF = pd.DataFrame({'QUANTITY' : [0, 0, 0, 0, 0]}, 
                                   index=['bronze', 'silver', 'gold', 'unknown', 'stolen'])
    START_TIME = time.perf_counter()

    LAST_NOTIFICATION_CLEAR = time.perf_counter()

    print("[INIT] Starting in 5 seconds.")
    time.sleep(5)
    
    if not check_adb():
        print("[ERR] ADB device not found.")
        sys.exit(1)
        
    template_img = cv2.imread('ore_template.png', cv2.IMREAD_COLOR)
    if template_img is None:
        print("[ERR] Failed to find 'ore_template.png'.")
        sys.exit(1)
        
    print("[INIT] Ready.")
    
    state = STATE_SEARCHING
    
    while True:
        if time.perf_counter() - LAST_NOTIFICATION_CLEAR >= NOTIFICATION_INTERVAL_SEC:
            print("[ANTI-BLOCK] Dismissing potential reward notification.")
            tap(UNWANTED_NOTIFICATION_X, UNWANTED_NOTIFICATION_Y)
            LAST_NOTIFICATION_CLEAR = time.perf_counter()

        img = take_screenshot_cv()
        if img is None:
            print("[DEBUG] Screenshot not obtained, waiting...")
            time.sleep(0.1)
            continue
            
        if is_ok_button_visible(img):
            state = STATE_COLLECTING
            
        if state == STATE_SEARCHING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is not None:
                print(f"[SEARCH] Ore silhouette found (X: {ore_x}).")
                state = STATE_AIMING
            else:
                print(f"[SEARCH] No text found. Rotating camera.")
                make_forward_step(200)
                camera_rotate_search()
                time.sleep(0.1)  
                    
        elif state == STATE_AIMING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is None:
                print("[AIM] Target lost during centering. Returning to scan.")
                state = STATE_SEARCHING
                continue
                
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound:
                print(f"[AIM] Ore left of center ({ore_x} < {left_bound}). Turning L.")
                camera_correct_left()
                time.sleep(0.1)
            elif ore_x > right_bound:
                print(f"[AIM] Ore right of center ({ore_x} > {right_bound}). Turning R.")
                camera_correct_right()
                time.sleep(0.1)
            else:
                print("[AIM] Target centered. Starting movement.")
                state = STATE_WALKING

        elif state == STATE_WALKING:
            ore_x = find_ore_template(img, template_img)
            
            if ore_x is None:
                print("[WALK] Text disappeared. Maybe we're close. Final step...")
                make_forward_step(1000)
                time.sleep(0.3)
                
                img_check = take_screenshot_cv()
                if is_ok_button_visible(img_check):
                    state = STATE_COLLECTING
                else:
                    print("[WALK] Button did not appear, target lost. Resetting.")
                    state = STATE_SEARCHING
                continue
                
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound or ore_x > right_bound:
                print("[WALK] Course drifted during walking. Correcting camera.")
                state = STATE_AIMING
                continue
                
            print("[WALK] Course correct. Large step forward...")
            make_forward_step(1750)
            time.sleep(0.1)

        elif state == STATE_COLLECTING:
            print("[HARVEST] Yellow OK button on screen.")
            tap(OK_TAP_X, OK_TAP_Y)
            time.sleep(0.1)
            
            print("[HARVEST] HARVEST" + '.' * 34)
            for _ in range(15):
                tap(HARVEST_TAP_X, HARVEST_TAP_Y)
                time.sleep(0.1)


            # DATA ANALYSIS INTERSECTION
            time.sleep(0.5)
            post_harvest_img = take_screenshot_cv()
            classify_and_log_ore(post_harvest_img, START_TIME, ORES_COUNTER_DF)

            TOTAL_MONEY = 0
            for kind, price in ORE_PRICES.items():
                TOTAL_MONEY += ORES_COUNTER_DF.at[kind, 'QUANTITY'] * price

            TOTAL_ORES_COUNTER += 1
            EXECUTION_TIME = (time.perf_counter() - START_TIME) / 60
            ORE_COEFFICIENT = TOTAL_ORES_COUNTER / EXECUTION_TIME
            print("*" * 50)
            print("*" * 20 + "STATISTICS" + "*" * 20)
            print(f"TIME: {EXECUTION_TIME:.2f} min.")
            print(f"ORE COUNT: {TOTAL_ORES_COUNTER}")
            print(ORES_COUNTER_DF)
            print(f"TOTAL MONEY EARNED: {TOTAL_MONEY}")
            print(f"RATE: {ORE_COEFFICIENT:.2f} ores/min")
            print("*" * 50 + '\n' + "*" * 50)
            print("[HARVEST] Harvest complete. Searching for next targets.")

            camera_tilt_down()
            state = STATE_SEARCHING

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[BOT] Bot stopped by user.")