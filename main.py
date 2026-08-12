import cv2
import mediapipe as mp
import math
import subprocess
import time
import numpy as np

# -----------------------------
# Configuration & Setup
# -----------------------------
# MediaPipe Setup
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)
mp_draw = mp.solutions.drawing_utils

# -----------------------------
# Mac OS Control Functions
# -----------------------------
def set_volume(volume):
    volume = max(0, min(100, volume))
    subprocess.run(["osascript", "-e", f"set volume output volume {volume}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def media_action(action):
    """Controls media via AppleScript. Targets standard Mac media keys behavior."""
    if action == "playpause":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 100'], stdout=subprocess.DEVNULL)
    elif action == "next":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 101'], stdout=subprocess.DEVNULL)
    elif action == "prev":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 98'], stdout=subprocess.DEVNULL)

# -----------------------------
# Helper Functions
# -----------------------------
def get_fingers_up(hand_landmarks):
    """Returns a list of 5 elements [Thumb, Index, Middle, Ring, Pinky] (1 if up, 0 if down)"""
    fingers = []
    # Thumb (Checking if it's extended to the side)
    if hand_landmarks.landmark[4].x < hand_landmarks.landmark[3].x:
        fingers.append(1)
    else:
        fingers.append(0)
    
    # 4 Fingers (Checking if tip is higher than lower joint)
    for id in [8, 12, 16, 20]:
        if hand_landmarks.landmark[id].y < hand_landmarks.landmark[id - 2].y:
            fingers.append(1)
        else:
            fingers.append(0)
    return fingers

def draw_transparent_ui(frame, text, position, width, height):
    """Draws a sleek dark translucent background behind text for a professional look."""
    overlay = frame.copy()
    x, y = position
    cv2.rectangle(overlay, (x, y), (x + width, y + height), (0, 0, 0), cv2.FILLED)
    frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)
    cv2.putText(frame, text, (x + 15, y + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return frame

# -----------------------------
# State Variables
# -----------------------------
camera = cv2.VideoCapture(0)
cam_w, cam_h = 640, 480
camera.set(3, cam_w)
camera.set(4, cam_h)

volume = 50
previous_volume = -1
active_gesture = "None"

# Cooldown timers to prevent spamming commands
last_media_time = 0
last_swipe_time = 0
swipe_start_x = None

while True:
    success, frame = camera.read()
    if not success:
        break

    frame = cv2.flip(frame, 1) # Mirror display
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)

    active_gesture = "None"

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            fingers = get_fingers_up(hand_landmarks)
            
            # --- EXTRACT KEY LANDMARKS ---
            thumb_tip = hand_landmarks.landmark[4]
            thumb_mcp = hand_landmarks.landmark[2]
            index_tip = hand_landmarks.landmark[8]
            palm_center = hand_landmarks.landmark[9]

            ix, iy = int(index_tip.x * cam_w), int(index_tip.y * cam_h)
            tx, ty = int(thumb_tip.x * cam_w), int(thumb_tip.y * cam_h)
            px = int(palm_center.x * cam_w)

            # ========================================
            # MEDIA & VOLUME CONTROL LOGIC
            # ========================================
            
            # 1. Volume Control (Thumb & Index pinched)
            if fingers == [1, 1, 0, 0, 0] or fingers == [0, 1, 0, 0, 0]:
                distance = math.hypot(ix - tx, iy - ty)
                if distance < 200: # Ensure they are actively pinching
                    active_gesture = "Adjusting Volume"
                    volume = int(np.interp(distance, [20, 200], [0, 100]))
                    if abs(volume - previous_volume) >= 2:
                        set_volume(volume)
                        previous_volume = volume
                    
                    cv2.circle(frame, (ix, iy), 10, (255, 0, 255), cv2.FILLED)
                    cv2.circle(frame, (tx, ty), 10, (255, 0, 255), cv2.FILLED)
                    cv2.line(frame, (ix, iy), (tx, ty), (0, 255, 0), 3)

            # 2. Max Volume (Thumbs Up)
            elif fingers == [1, 0, 0, 0, 0] and thumb_tip.y < thumb_mcp.y:
                active_gesture = "Thumbs Up: Max Vol"
                if time.time() - last_media_time > 1:
                    set_volume(100)
                    volume = 100
                    last_media_time = time.time()

            # 3. Mute/Zero Volume (Thumbs Down)
            elif fingers == [1, 0, 0, 0, 0] and thumb_tip.y > thumb_mcp.y:
                active_gesture = "Thumbs Down: Mute"
                if time.time() - last_media_time > 1:
                    set_volume(0)
                    volume = 0
                    last_media_time = time.time()

            # 4. Play/Pause (V-Sign / Two Fingers)
            elif fingers == [0, 1, 1, 0, 0]:
                active_gesture = "V-Sign: Play/Pause"
                if time.time() - last_media_time > 1.5:
                    media_action("playpause")
                    last_media_time = time.time()

            # 5. Swipe (Previous / Next Song) - Open Palm
            elif fingers == [1, 1, 1, 1, 1] or fingers == [0, 1, 1, 1, 1]:
                if swipe_start_x is None:
                    swipe_start_x = px
                else:
                    dx = px - swipe_start_x
                    if time.time() - last_swipe_time > 1.5:
                        if dx > 150:
                            active_gesture = "Swipe Right -> Next Song"
                            media_action("next")
                            last_swipe_time = time.time()
                            swipe_start_x = px
                        elif dx < -150:
                            active_gesture = "Swipe Left <- Prev Song"
                            media_action("prev")
                            last_swipe_time = time.time()
                            swipe_start_x = px
            else:
                swipe_start_x = None # Reset swipe if hand closes

    # -----------------------------
    # Professional UI Rendering
    # -----------------------------
    
    # Top Status Bar
    frame = draw_transparent_ui(frame, "MEDIA CONTROL ACTIVE", (10, 10), 350, 50)
    
    # Action Status Bar
    if active_gesture != "None":
        frame = draw_transparent_ui(frame, f"Action: {active_gesture}", (10, 70), 450, 50)

    # Volume Bar
    bar_top, bar_bottom, bar_left, bar_right = 150, 400, 20, 40
    # Draw outline
    cv2.rectangle(frame, (bar_left, bar_top), (bar_right, bar_bottom), (200, 200, 200), 2)
    # Draw filled portion
    filled = int(bar_bottom - (volume / 100) * (bar_bottom - bar_top))
    cv2.rectangle(frame, (bar_left, filled), (bar_right, bar_bottom), (0, 215, 255), cv2.FILLED)
    cv2.putText(frame, f"{volume}%", (15, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 2)

    # Render Frame
    cv2.imshow("Advanced Media Gesture Control", frame)
    
    # -----------------------------
    # Keyboard Controls
    # -----------------------------
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
camera.release()
cv2.destroyAllWindows()