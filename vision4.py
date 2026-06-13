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
#  НАЛАШТУВАННЯ КООРДИНАТ ТА ПАРАМЕТРІВ
# ─────────────────────────────────────────────
SCREEN_W = 2340
SCREEN_H = 1080

# Центральна лінія екрана та дозволена зона похибки (Deadzone)
CENTER_X = SCREEN_W // 2  # 1170
DEADZONE_X = 60           # Оптимально для збереження точности курсу

# Координати з fff1.py
OK_TAP_X, OK_TAP_Y = 1500, 1000
HARVEST_TAP_X, HARVEST_TAP_Y = 1200, 570

# Колір кнопки ОК в форматі BGR (OpenCV використовує BGR замість RGB)
# У fff1.py RGB=(255, 185, 9) -> BGR=(9, 185, 255)
OK_COLOR_TARGET_BGR = (9, 185, 255)
OK_COLOR_TOLERANCE = 25

# Віртуальний джойстик рушію
MOVE_CENTER_X = 360
MOVE_CENTER_Y = 800
MOVE_STEP_Y = 720  # Точка для мікро-кроку вперед

# Стейт-машина (Стани бота)
STATE_SEARCHING = "SEARCHING"  # Крутимося і шукаємо шаблон
STATE_AIMING    = "AIMING"     # Центруємо камеру на напис
STATE_WALKING   = "WALKING"    # Йдемо мікро-кроками вперед
STATE_COLLECTING = "COLLECTING" # Натискаємо ОК та збираємо

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
    """Забирає скріншот через adb exec-out і повертає OpenCV BGR зображення."""
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
            # Фолбек на повільніший варіант, якщо масив байтів бітий
            return cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    except:
        return None

def find_ore_template(scene_img, template_img, threshold=0.75):
    """Шукає шаблон ore_template.png на екрані гри."""
    if scene_img is None or template_img is None:
        return None
    
    res = cv2.matchTemplate(scene_img, template_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= threshold:
        # Обчислюємо центр знайденого шаблону по осі X
        template_w = template_img.shape[1]
        center_text_x = max_loc[0] + (template_w // 2)
        return center_text_x
    return None

def is_ok_button_visible(scene_img):
    """Перевіряє наявність жовтого пікселя кнопки ОК з урахуванням похибки."""
    if scene_img is None: return False
    try:
        # Отримуємо колір у фіксованій точці (OpenCV індексує: Y, X)
        pixel_bgr = scene_img[OK_TAP_Y, OK_TAP_X]
        return all(abs(int(p) - int(t)) <= OK_COLOR_TOLERANCE for p, t in zip(pixel_bgr, OK_COLOR_TARGET_BGR))
    except:
        return False

# ─────────────────────────────────────────────
#  МАНІПУЛЯЦІЇ КАМЕРОЮ ТА РУХОМ
# ─────────────────────────────────────────────

def camera_rotate_search():
    """Поворот камери праворуч для сканування місцевости (свайп ліворуч)."""
    swipe(1600, 500, 1400, 500, duration_ms=250)

def camera_correct_left():
    """Мікро-поворот камери ліворуч (свайп праворуч)."""
    swipe(1400, 500, 1460, 500, duration_ms=100)

def camera_correct_right():
    """Мікро-поворот камери праворуч (свайп ліворуч)."""
    swipe(1600, 500, 1540, 500, duration_ms=100)

def make_micro_step():
    """Мікро-крок вперед за допомогою джойстика."""
    swipe(MOVE_CENTER_X, MOVE_CENTER_Y, MOVE_CENTER_X, MOVE_STEP_Y, duration_ms=350)

# ─────────────────────────────────────────────
#  ГОЛОВНИЙ ЦИКЛ БОТА
# ─────────────────────────────────────────────

def main():
    print("[INIT] Запуск за 5 секунд. Перейдіть у вікно гри!")
    time.sleep(5)
    
    if not check_adb():
        print("[ERR] ADB пристрій не знайдено. Перевірте кабель чи емулятор.")
        sys.exit(1)
        
    # Завантажуємо шаблон
    template_img = cv2.imread('ore_template.png', cv2.IMREAD_COLOR)
    if template_img is None:
        print("[ERR] Не вдалося завантажити 'ore_template.png'. Покладіть файл поруч зі скриптом.")
        sys.exit(1)
        
    print("[INIT] Усе готово. Починаємо полювання на руду!")
    
    state = STATE_SEARCHING
    search_rotation_count = 0
    blind_steps_count = 0
    
    while True:
        img = take_screenshot_cv()
        if img is None:
            time.sleep(0.1)
            continue
            
        # ПРІОРИТЕТ: Перевірка кнопки ОК доступна в будь-якому стані руху
        if is_ok_button_visible(img):
            state = STATE_COLLECTING
            
        # Реалізація логіки стейт-машини
        if state == STATE_SEARCHING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is not None:
                print(f"[SEARCH] Знайдено силует руди! Переходимо до прицілювання.")
                state = STATE_AIMING
                search_rotation_count = 0
                blind_steps_count = 0
            else:
                if search_rotation_count < 12:
                    print(f"[SEARCH] Руди немає. Оглядаємося ({search_rotation_count + 1}/12)...")
                    camera_rotate_search()
                    search_rotation_count += 1
                    time.sleep(0.4)  # Час на стабілізацію камери після повороту
                else:
                    print("[SEARCH] Повне коло пройдено, нічого не знайдено. Робимо кроки наосліп.")
                    for _ in range(3): make_micro_step()
                    search_rotation_count = 0
                    
        elif state == STATE_AIMING:
            ore_x = find_ore_template(img, template_img)
            if ore_x is None:
                print("[AIM] Ціль втрачено при спробі прицілювання. Повернення до пошуку.")
                state = STATE_SEARCHING
                continue
                
            # Перевіряємо положення щодо центру екрана
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound:
                print(f"[AIM] Руда лівіше ({ore_x} < {left_bound}). Коригуємо ліворуч.")
                camera_correct_left()
                time.sleep(0.15)
            elif ore_x > right_bound:
                print(f"[AIM] Руда правіше ({ore_x} > {right_bound}). Коригуємо праворуч.")
                camera_correct_right()
                time.sleep(0.15)
            else:
                print("[AIM] Ціль чітко по центру! Починаємо зближення.")
                state = STATE_WALKING

        elif state == STATE_WALKING:
            ore_x = find_ore_template(img, template_img)
            
            if ore_x is None:
                # Напис зник. Якщо ми йшли правильно, можливо ми вже впритул
                print("[WALK] Напис зник. Можливо, підійшли впритул. Робимо фінальні кроки...")
                make_micro_step()
                time.sleep(0.2)
                
                # Перевіряємо ще раз, чи з'явилася кнопка ОК
                img_check = take_screenshot_cv()
                if is_ok_button_visible(img_check):
                    state = STATE_COLLECTING
                else:
                    blind_steps_count += 1
                    if blind_steps_count > 4: # Захист від вічного бігу в стіну
                        print("[WALK] Кнопка не з'явилася, руда втрачена. Скидання.")
                        state = STATE_SEARCHING
                continue
                
            # Перевіряємо, чи курс не збився під час руху
            left_bound = CENTER_X - DEADZONE_X
            right_bound = CENTER_X + DEADZONE_X
            
            if ore_x < left_bound or ore_x > right_bound:
                print("[WALK] Курс збився під час ходьби. Повернення до коригування камери.")
                state = STATE_AIMING
                continue
                
            # Якщо все добре — робимо крок вперед
            print("[WALK] Напис у центрі. Крок вперед...")
            make_micro_step()
            time.sleep(0.1)

        elif state == STATE_COLLECTING:
            print("[HARVEST] Жовта кнопка ОК на екрані! Зупинка та збір ресурсу.")
            # Натискаємо ОК
            tap(OK_TAP_X, OK_TAP_Y)
            time.sleep(0.3)
            
            # 15 швидких тапів для збору руди
            print("[HARVEST] Виконуємо 15 швидких ударів по кнопці збору...")
            for _ in range(15):
                tap(HARVEST_TAP_X, HARVEST_TAP_Y)
                time.sleep(0.05)
                
            print("[HARVEST] Збір завершено. Очікуємо завершення анімації та шукаємо далі.")
            time.sleep(4.5)  # Час на зникнення залишків руди з екрана
            state = STATE_SEARCHING

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[BOT] Роботу завершено користувачем.")