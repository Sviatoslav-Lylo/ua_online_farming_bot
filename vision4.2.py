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
#  НАЛАШТУВАННЯ КООРДИНАТ ТА ПАРАМЕТРІВ
# ─────────────────────────────────────────────
SCREEN_W = 2340
SCREEN_H = 1080

CENTER_X = SCREEN_W // 2  # 1170
DEADZONE_X = 60           # Оптимально для збереження точности курсу

OK_TAP_X, OK_TAP_Y = 1500, 1000
HARVEST_TAP_X, HARVEST_TAP_Y = 1200, 570

OK_COLOR_TARGET_BGR = (9, 185, 255)
OK_COLOR_TOLERANCE = 25

MOVE_CENTER_X = 360
MOVE_CENTER_Y = 800
MOVE_STEP_Y = 640  # Збільшено амплітуду (було 720), щоб кроки були довшими

STATE_SEARCHING = "SEARCHING"  
STATE_AIMING    = "AIMING"     
STATE_WALKING   = "WALKING"    
STATE_COLLECTING = "COLLECTING" 

# ─────────────────────────────────────────────
#  ТЕХНІЧНІ ФУНКЦІЇ (ADB ТА ГРАФІКА)
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
    """Надійне отримання PNG-кадру через exec-out для Windows."""
    try:
        res = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=3)
        if not res.stdout or len(res.stdout) < 100:
            print("[DEBUG] Помилка: Отримано пустий потік даних від ADB.")
            return None
        
        img_buffer = np.frombuffer(res.stdout, dtype=np.uint8)
        img = cv2.imdecode(img_buffer, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"[DEBUG] Виняток при знятті скріншоту: {e}")
        return None

def find_ore_template(scene_img, template_img, threshold=0.70):
    """Шукає шаблон ore_template.png на екрані гри."""
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
    """Перевіряє наявність жовтого пікселя кнопки ОК."""
    if scene_img is None: return False
    try:
        pixel_bgr = scene_img[OK_TAP_Y, OK_TAP_X]
        return all(abs(int(p) - int(t)) <= OK_COLOR_TOLERANCE for p, t in zip(pixel_bgr, OK_COLOR_TARGET_BGR))
    except:
        return False

# ─────────────────────────────────────────────
#  МАНІПУЛЯЦІЇ КАМЕРОЮ ТА РУХОМ
# ─────────────────────────────────────────────

def camera_rotate_search():
    swipe(1600, 500, 1400, 500, duration_ms=250)

def camera_correct_left():
    swipe(1400, 500, 1450, 500, duration_ms=100)

def camera_correct_right():
    swipe(1600, 500, 1550, 500, duration_ms=100)

def make_forward_step():
    """Широкий крок вперед за допомогою джойстика."""
    swipe(MOVE_CENTER_X, MOVE_CENTER_Y, MOVE_CENTER_X, MOVE_STEP_Y, duration_ms=400)

# ─────────────────────────────────────────────
#  ГОЛОВНИЙ ЦИКЛ БОТА
# ─────────────────────────────────────────────

def main():
    print("[INIT] Запуск за 5 секунд. Перейдіть у вікно гри!")
    time.sleep(5)
    
    if not check_adb():
        print("[ERR] ADB пристрій не знайдено. Перевірте підключення.")
        sys.exit(1)
        
    template_img = cv2.imread('ore_template.png', cv2.IMREAD_COLOR)
    if template_img is None:
        print("[ERR] Не вдалося знайти файл 'ore_template.png'. Покладіть його поруч зі скриптом.")
        sys.exit(1)
        
    print("[INIT] Усе готово. Починаємо полювання на руду!")
    
    state = STATE_SEARCHING
    search_rotation_count = 0
    blind_steps_count = 0
    
    while True:
        img = take_screenshot_cv()
        if img is None:
            print("[DEBUG] Скріншот не отримано, чекаємо...")
            time.sleep(0.2)
            continue
            
        if is_ok_button_visible(img):
            state = STATE_COLLECTING
            
        if state == STATE_SEARCHING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is not None:
                print(f"[SEARCH] Знайдено силует руди (X: {ore_x})! Фіксуємо курс.")
                state = STATE_AIMING
                search_rotation_count = 0
                blind_steps_count = 0
            else:
                if search_rotation_count < 12:
                    print(f"[SEARCH] Тексту немає. Оглядаємося навколо ({search_rotation_count + 1}/12)...")
                    camera_rotate_search()
                    search_rotation_count += 1
                    time.sleep(0.5)  
                else:
                    print("[SEARCH] Повне коло пройдено. Руди не виявлено, починаємо нове коло сканування...")
                    search_rotation_count = 0
                    time.sleep(0.5)
                    
        elif state == STATE_AIMING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is None:
                print("[AIM] Ціль втрачено при центруванні. Повернення до сканування.")
                state = STATE_SEARCHING
                continue
                
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound:
                print(f"[AIM] Руда лівіше центру ({ore_x} < {left_bound}). Поворот ліворуч.")
                camera_correct_left()
                time.sleep(0.2)
            elif ore_x > right_bound:
                print(f"[AIM] Руда правіше центру ({ore_x} > {right_bound}). Поворот праворуч.")
                camera_correct_right()
                time.sleep(0.2)
            else:
                print("[AIM] Ціль відцентрована! Починаємо рух.")
                state = STATE_WALKING

        elif state == STATE_WALKING:
            ore_x = find_ore_template(img, template_img)
            
            if ore_x is None:
                print("[WALK] Напис зник. Можливо, ми підійшли впритул. Робимо фінальний крок...")
                make_forward_step()
                time.sleep(0.3)
                
                img_check = take_screenshot_cv()
                if is_ok_button_visible(img_check):
                    state = STATE_COLLECTING
                else:
                    blind_steps_count += 1
                    if blind_steps_count > 4:
                        print("[WALK] Кнопка не з'явилася, ціль остаточно втрачено. Скидання.")
                        state = STATE_SEARCHING
                continue
                
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound or ore_x > right_bound:
                print("[WALK] Збилися з курсу під час ходьби. Коригуємо камеру.")
                state = STATE_AIMING
                continue
                
            print("[WALK] Курс вірний. Великий крок вперед...")
            make_forward_step()
            time.sleep(0.1)

        elif state == STATE_COLLECTING:
            print("[HARVEST] Жовта кнопка ОК на екрані! Починаємо збір.")
            tap(OK_TAP_X, OK_TAP_Y)
            time.sleep(0.3)
            
            print("[HARVEST] 15 швидких ударів по кнопці збору...")
            for _ in range(15):
                tap(HARVEST_TAP_X, HARVEST_TAP_Y)
                time.sleep(0.05)
                
            print("[HARVEST] Збір завершено. Очікуємо 4.5 сек анімації.")
            time.sleep(4.5)  
            state = STATE_SEARCHING

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[BOT] Роботу завершено користувачем.")