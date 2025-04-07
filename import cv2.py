import cv2
import mediapipe as mp
import numpy as np
import time
import threading
from pynput.keyboard import Controller, Key

# Initialize MediaPipe Hands with lighter settings
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,  # Track only one hand to reduce processing
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)
mp_draw = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Initialize Keyboard Controller
keyboard = Controller()

# Create a separate thread for key presses to avoid blocking the main loop
class KeyPressThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True  # Thread will exit when main program exits
        self.command = "NONE"
        self.tilt_strength = 0.0
        self.running = True
        self.last_key_press = time.time()
    def run(self):
        
        while self.running:
            current_time = time.time()
            
            # Calculate the adjusted interval based on tilt strength
            if self.tilt_strength > 0:
                adjusted_interval = 0.1 * (1.0 - 0.7 * self.tilt_strength)
            else:
                adjusted_interval = 0.1
                
            if current_time - self.last_key_press >= adjusted_interval:
                self.press_keys()
                self.last_key_press = current_time
                
            # Sleep a short time to reduce CPU usage
            time.sleep(0.01)
    
    def press_keys(self):
        # Release all keys first
        keyboard.release(Key.up)
        keyboard.release(Key.down)
        keyboard.release(Key.left)
        keyboard.release(Key.right)
        keyboard.release(Key.backspace)
        
        # Press the appropriate keys based on the current command
        if self.command == "UP":
            keyboard.press(Key.up)
        elif self.command == "UP_LEFT":
            keyboard.press(Key.up)
            keyboard.press(Key.left)
        elif self.command == "UP_RIGHT":
            keyboard.press(Key.up)
            keyboard.press(Key.right)
        elif self.command == "DOWN":
            keyboard.press(Key.down)
        elif self.command == "DOWN_LEFT":
            keyboard.press(Key.backspace)
            keyboard.press(Key.left)
        elif self.command == "DOWN_RIGHT":
            keyboard.press(Key.down)
            keyboard.press(Key.right)
        elif self.command == "SPACE":
            keyboard.press(Key.space)
            keyboard.release(Key.space)
            
    def update_command(self, command, tilt_strength):
        self.command = command
        self.tilt_strength = tilt_strength
        
    def stop(self):
        self.running = False

# Create a simpler gesture detection function
def detect_gesture(landmarks):
    # Extract key points
    index_tip = np.array([landmarks[8].x, landmarks[8].y])
    wrist = np.array([landmarks[0].x, landmarks[0].y])
    
    # Check if only index finger is raised (for space key)
    index_raised = landmarks[8].y < landmarks[5].y - 0.1
    other_fingers_down = (
        landmarks[12].y > landmarks[9].y and
        landmarks[16].y > landmarks[13].y and
        landmarks[20].y > landmarks[17].y
    )
    index_only = index_raised and other_fingers_down
    
    # Calculate palm center
    palm_center = np.mean([
        [landmarks[0].x, landmarks[0].y],
        [landmarks[5].x, landmarks[5].y],
        [landmarks[17].x, landmarks[17].y]
    ], axis=0)
    
    # Calculate hand openness
    distance_wrist_index = np.linalg.norm(index_tip - wrist)
    
    # Detect tilt
    hand_tilt = palm_center[0] - wrist[0]
    
    # Thresholds
    open_threshold = 0.2
    tilt_threshold = 0.05
    
    # Calculate tilt strength (0.0 to 1.0)
    tilt_strength = 0.0
    tilt_direction = "NONE"
    
    if hand_tilt < -tilt_threshold:  # Left tilt
        tilt_strength = min(abs(hand_tilt / 0.15), 1.0)
        tilt_direction = "LEFT"
    elif hand_tilt > tilt_threshold:  # Right tilt
        tilt_strength = min(abs(hand_tilt / 0.15), 1.0)
        tilt_direction = "RIGHT"
    
    # Determine gesture
    if index_only:
        return "SPACE", 0.0
    
    if distance_wrist_index > open_threshold:  # Open hand
        if tilt_direction == "LEFT":
            return "UP_LEFT", tilt_strength
        elif tilt_direction == "RIGHT":
            return "UP_RIGHT", tilt_strength
        else:
            return "UP", 0.0
    else:  # Closed hand
        if tilt_direction == "LEFT":
            return "DOWN_LEFT", tilt_strength
        elif tilt_direction == "RIGHT":
            return "DOWN_RIGHT", tilt_strength
        else:
            return "DOWN", 0.0

# Start key press thread
key_thread = KeyPressThread()
key_thread.start()

# Set up camera with lower resolution
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Reduced resolution
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Variables for frame rate calculation
prev_frame_time = 0
new_frame_time = 0

try:
    while cap.isOpened():
        # Calculate FPS
        new_frame_time = time.time()
        fps = 1/(new_frame_time-prev_frame_time) if prev_frame_time > 0 else 0
        prev_frame_time = new_frame_time
        
        # Process only every other frame to reduce load
        ret, frame = cap.read()
        if not ret:
            break
            
        # Flip horizontally for selfie view
        frame = cv2.flip(frame, 1)
        
        # Convert to RGB without creating a copy
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process with MediaPipe
        results = hands.process(rgb_frame)
        
        new_command = "NONE"
        tilt_strength = 0.0
        
        # Draw hand landmarks if detected
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Use simpler drawing style
                mp_draw.draw_landmarks(
                    frame, 
                    hand_landmarks, 
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style()
                )
                
                # Detect gesture
                new_command, tilt_strength = detect_gesture(hand_landmarks.landmark)
                
                # Update the key press thread with the new command
                key_thread.update_command(new_command, tilt_strength)
                break  # Only use the first hand detected
        
        # Display info with simplified text
        cv2.putText(frame, f'FPS: {int(fps)}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f'Command: {new_command}', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f'Tilt: {int(tilt_strength*100)}%', (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Display the frame
        cv2.imshow('Hand Gesture Control', frame)
        
        # Check for exit
        if cv2.waitKey(5) & 0xFF == ord('q'):
            break

finally:
    # Clean up resources
    key_thread.stop()
    cap.release()
    cv2.destroyAllWindows()