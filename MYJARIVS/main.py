import speech_recognition as sr
import pyttsx3
import webbrowser
import datetime
import os
import re
import sys
import subprocess
import time
import pyautogui

from ai_brain import ask_ai


# ============================================================
# JARVIS SETTINGS
# ============================================================

MICROPHONE_INDEX = 1
WAKE_WORDS = ["jarvis", "hey jarvis"]

# These are the existing non-AI commands that may be used directly.
DIRECT_COMMANDS = {
    "hello",
    "hi",
    "google",
    "youtube",
    "github",
    "chatgpt",
    "shutdown",
    "shut down",
    "exit",
    "quit",
    "goodbye",
}

DIRECT_COMMAND_PREFIXES = (
    "how are you",
    "open google",
    "open youtube",
    "open github",
    "open chatgpt",
    "open chrome",
    "open notepad",
    "open calculator",
    "open calc",
    "open file explorer",
    "open explorer",
    "open files",
    "open vs code",
    "open visual studio code",
    "open whatsapp",
    "open downloads",
    "open desktop",
    "play music",
    "open music",
    "search youtube for",
    "search youtube",
    "search google",
    "search for",
    "what is the time",
    "what's the time",
    "tell me the time",
    "what is the date",
    "what is today's date",
    "tell me the date",
    "increase volume",
    "volume up",
    "turn up volume",
    "decrease volume",
    "volume down",
    "turn down volume",
    "mute",
    "mute volume",
    "take screenshot",
    "take a screenshot",
    "screenshot",
)

QUESTION_PREFIXES = (
    "what ",
    "what's ",
    "who ",
    "when ",
    "where ",
    "why ",
    "how ",
    "can ",
    "could ",
    "would ",
    "should ",
    "is ",
    "are ",
    "do ",
    "does ",
    "did ",
    "will ",
    "define ",
    "explain ",
    "describe ",
    "tell me ",
)


def normalize_chatgpt_command(command):
    """Normalize common speech-recognition variants for ChatGPT."""

    normalized = re.sub(
        r"\bchat[\s-]+gpt\b",
        "chatgpt",
        command,
        flags=re.IGNORECASE
    )

    return re.sub(
        r"\bopen\s+chat\b",
        "open chatgpt",
        normalized,
        flags=re.IGNORECASE
    )


def is_direct_command(command):
    """Return True only for an existing non-AI command pattern."""

    normalized = normalize_chatgpt_command(
        command.lower().strip()
    )

    for wake_word in WAKE_WORDS:
        normalized = normalized.replace(wake_word, " ")

    normalized = normalized.strip(" ,.!?")

    return (
        normalized in DIRECT_COMMANDS
        or any(
            normalized.startswith(prefix)
            for prefix in DIRECT_COMMAND_PREFIXES
        )
    )


def is_ai_question(command):
    """Allow a question-like request without treating random speech as a command."""

    normalized = command.lower().strip()

    for wake_word in WAKE_WORDS:
        normalized = normalized.replace(wake_word, " ")

    if normalized.rstrip().endswith("?"):
        return True

    normalized = normalized.strip(" ,.!?")

    return any(
        normalized.startswith(prefix)
        for prefix in QUESTION_PREFIXES
    )


# ============================================================
# VOICE ENGINE
# ============================================================

def speak(text):
    """Print a response and speak it using pyttsx3."""

    if text is None:
        return

    text = str(text).strip()
    if not text:
        return

    print("JARVIS:", text)

    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        engine.setProperty("volume", 1.0)

        engine.say(text)
        engine.runAndWait()
        engine.stop()

    except Exception as error:
        print("Voice output error:", error)


# ============================================================
# SPEECH RECOGNITION
# ============================================================

recognizer = sr.Recognizer()

recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 1.0
recognizer.non_speaking_duration = 0.5


def listen():

    try:

        with sr.Microphone(
            device_index=MICROPHONE_INDEX
        ) as source:

            print()
            speak("Listening...")

            try:

                audio = recognizer.listen(
                    source,
                    timeout=10,
                    phrase_time_limit=60
                )

            except sr.WaitTimeoutError:

                speak("No speech detected.")
                return ""

        speak("Processing your voice...")

        command = recognizer.recognize_google(
            audio,
            language="en-IN"
        )

        command = command.lower().strip()

        print("You:", command)

        return command

    except sr.UnknownValueError:

        speak("Sorry, I couldn't understand that.")
        return ""

    except sr.RequestError:

        speak("Sorry sir, speech recognition is unavailable.")
        return ""

    except Exception as e:

        speak(f"Microphone error: {e}")
        return ""


# ============================================================
# GOOGLE
# ============================================================

def open_google():

    webbrowser.open("https://www.google.com")
    speak("Opening Google, sir.")


# ============================================================
# YOUTUBE
# ============================================================

def open_youtube():

    webbrowser.open("https://www.youtube.com")
    speak("Opening YouTube, sir.")


# ============================================================
# GITHUB
# ============================================================

def open_github():

    webbrowser.open("https://github.com")
    speak("Opening GitHub, sir.")


# ============================================================
# CHATGPT
# ============================================================

def _extract_chatgpt_message(command):
    """Return the text after the first write/type/ask trigger."""

    match = re.search(
        r"\b(?:write|type|ask)\b\s*(.*)$",
        command,
        re.IGNORECASE
    )

    if match is None:
        return ""

    return match.group(1).strip()


def _activate_chatgpt_window():
    """Activate a visible browser window whose title identifies ChatGPT."""

    try:
        windows = pyautogui.getWindowsWithTitle("ChatGPT")
    except Exception:
        return None

    for window in windows:
        try:
            if window.isMinimized:
                window.restore()

            window.activate()
            time.sleep(0.2)

            active_window = pyautogui.getActiveWindow()
            active_title = str(
                getattr(active_window, "title", "")
            ).lower()

            if "chatgpt" in active_title:
                return window

        except Exception:
            continue

    return None


def _focus_chatgpt_input(window):
    """Click the ChatGPT composer using the active window's current bounds."""

    try:
        window_left = int(window.left)
        window_top = int(window.top)
        window_width = int(window.width)
        window_height = int(window.height)

        input_x = window_left + window_width // 2
        input_y = window_top + int(window_height * 0.88)
        pyautogui.click(input_x, input_y)
        time.sleep(0.2)

        active_window = pyautogui.getActiveWindow()
        active_title = str(
            getattr(active_window, "title", "")
        ).lower()

        return "chatgpt" in active_title

    except Exception:
        return False


def open_chatgpt_and_send(command):
    """Open ChatGPT, focus its composer, and send the requested message."""

    message = _extract_chatgpt_message(command)
    failure_message = (
        "Sorry sir, I couldn't send the message to ChatGPT."
    )

    if not message:
        speak(failure_message)
        return

    try:
        opened = webbrowser.open("https://chatgpt.com/")

        if opened is False:
            speak(failure_message)
            return

        time.sleep(3)

        chatgpt_window = _activate_chatgpt_window()
        if (
            chatgpt_window is None
            or not _focus_chatgpt_input(chatgpt_window)
        ):
            speak(failure_message)
            return

        try:
            pyautogui.write(message, interval=0.01)
        except Exception:
            speak(failure_message)
            return

        try:
            pyautogui.press("enter")
        except Exception:
            speak(failure_message)
            return

        speak("Opening ChatGPT and sending your message, sir.")

    except Exception as error:
        speak(f"ChatGPT error: {error}")
        speak(failure_message)


def open_chatgpt():

    speak("Opening ChatGPT, sir.")
    webbrowser.open("https://chatgpt.com/")


# ============================================================
# CHROME
# ============================================================

def open_chrome():

    try:

        subprocess.Popen(
            "start chrome",
            shell=True
        )

        speak("Opening Chrome, sir.")

    except Exception as e:

        speak(f"Chrome error: {e}")
        speak("Sorry sir, I couldn't open Chrome.")


# ============================================================
# NOTEPAD
# ============================================================

def open_notepad():

    subprocess.Popen("notepad.exe")
    speak("Opening Notepad, sir.")


# ============================================================
# CALCULATOR
# ============================================================

def open_calculator():

    subprocess.Popen("calc.exe")
    speak("Opening Calculator, sir.")


# ============================================================
# FILE EXPLORER
# ============================================================

def open_file_explorer():

    subprocess.Popen("explorer.exe")
    speak("Opening File Explorer, sir.")


# ============================================================
# VS CODE
# ============================================================

def open_vs_code():

    try:

        subprocess.Popen(
            "code",
            shell=True
        )

        speak("Opening VS Code, sir.")

    except Exception as e:

        speak(f"VS Code error: {e}")
        speak("Sorry sir, I couldn't open VS Code.")


# ============================================================
# WHATSAPP
# ============================================================

def open_whatsapp():

    try:

        subprocess.Popen(
            "start whatsapp:",
            shell=True
        )

        speak("Opening WhatsApp, sir.")

    except Exception as e:

        speak(f"WhatsApp error: {e}")
        speak("Sorry sir, I couldn't open WhatsApp.")


# ============================================================
# DOWNLOADS
# ============================================================

def open_downloads():

    downloads = os.path.join(
        os.path.expanduser("~"),
        "Downloads"
    )

    try:

        os.startfile(downloads)
        speak("Opening Downloads folder, sir.")

    except Exception as e:

        speak(f"Downloads error: {e}")
        speak("Sorry sir, I couldn't open the Downloads folder.")


# ============================================================
# DESKTOP
# ============================================================

def open_desktop():

    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

        if not os.path.exists(desktop):
            desktop = os.path.join(
                os.environ["USERPROFILE"],
                "OneDrive",
                "Desktop"
            )

        if os.path.exists(desktop):
            os.startfile(desktop)
            speak("Opening Desktop, sir.")
        else:
            speak("Sorry sir, I couldn't find the Desktop folder.")

    except Exception as e:
        speak(f"Desktop error: {e}")
        speak("Sorry sir, I couldn't open Desktop.")


# ============================================================
# MUSIC
# ============================================================

def play_music():

    webbrowser.open("https://music.youtube.com")
    speak("Opening YouTube Music, sir.")


# ============================================================
# YOUTUBE SEARCH
# ============================================================

def youtube_search(command):

    query = command

    query = query.replace(
        "search youtube for",
        ""
    ).strip()

    query = query.replace(
        "search youtube",
        ""
    ).strip()

    if not query:

        speak("What should I search for?")
        return

    url = (
        "https://www.youtube.com/results?search_query="
        + query.replace(" ", "+")
    )

    webbrowser.open(url)

    speak(f"Searching YouTube for {query}, sir.")


# ============================================================
# GOOGLE SEARCH
# ============================================================

def google_search(command):

    query = command

    query = query.replace(
        "search google for",
        ""
    ).strip()

    query = query.replace(
        "search google",
        ""
    ).strip()

    query = query.replace(
        "search for",
        ""
    ).strip()

    if not query:

        speak("What should I search for?")
        return

    url = (
        "https://www.google.com/search?q="
        + query.replace(" ", "+")
    )

    webbrowser.open(url)

    speak(f"Searching Google for {query}, sir.")


# ============================================================
# TIME
# ============================================================

def tell_time():

    current_time = datetime.datetime.now().strftime(
        "%I:%M %p"
    )

    speak(f"The time is {current_time}, sir.")


# ============================================================
# DATE
# ============================================================

def tell_date():

    current_date = datetime.datetime.now().strftime(
        "%d %B %Y"
    )

    speak(f"Today's date is {current_date}, sir.")


# ============================================================
# VOLUME UP
# ============================================================

def increase_volume():

    pyautogui.press(
        "volumeup",
        presses=3
    )

    speak("Volume increased, sir.")


# ============================================================
# VOLUME DOWN
# ============================================================

def decrease_volume():

    pyautogui.press(
        "volumedown",
        presses=3
    )

    speak("Volume decreased, sir.")


# ============================================================
# MUTE
# ============================================================

def mute_volume():

    pyautogui.press("volumemute")

    speak("Volume muted, sir.")


# ============================================================
# SCREENSHOT
# ============================================================

def take_screenshot():

    try:

        filename = "jarvis_screenshot.png"

        screenshot = pyautogui.screenshot()
        screenshot.save(filename)

        full_path = os.path.abspath(filename)

        speak(f"Screenshot saved as {full_path}")
        speak("Screenshot taken, sir.")

    except Exception as e:

        speak(f"Screenshot error: {e}")
        speak("Sorry sir, I couldn't take the screenshot.")


# ============================================================
# GREETING
# ============================================================

def greeting():

    speak("Hello sir. How can I help you?")


# ============================================================
# PROCESS COMMAND
# ============================================================

def process_command(command):

    if not command:

        return True


    # --------------------------------------------------------
    # REMOVE WAKE WORD
    # --------------------------------------------------------

    if any(
        word in command
        for word in WAKE_WORDS
    ):
        command = command.replace(
            "hey jarvis",
            ""
        ).strip()

        command = command.replace(
            "jarvis",
            ""
        ).lstrip(" ,.!?")
    else:
        command = command.strip()

    command = normalize_chatgpt_command(command)


    # --------------------------------------------------------
    # EMPTY COMMAND
    # --------------------------------------------------------

    if not command:

        speak("Yes sir. How can I help you?")
        return True


    # --------------------------------------------------------
    # GREETING
    # --------------------------------------------------------

    if (
        command == "hello"
        or command == "hi"
        or "hello jarvis" in command
    ):

        greeting()


    # --------------------------------------------------------
    # HOW ARE YOU
    # --------------------------------------------------------

    elif "how are you" in command:

        speak("I am functioning perfectly, sir.")


    # --------------------------------------------------------
    # GOOGLE
    # --------------------------------------------------------

    elif (
        "open google" in command
        or command == "google"
    ):

        open_google()


    # --------------------------------------------------------
    # YOUTUBE
    # --------------------------------------------------------

    elif (
        "open youtube" in command
        or command == "youtube"
    ):

        open_youtube()


    # --------------------------------------------------------
    # GITHUB
    # --------------------------------------------------------

    elif (
        "open github" in command
        or command == "github"
    ):

        open_github()


    # --------------------------------------------------------
    # CHATGPT — with message
    # --------------------------------------------------------

    elif (
        "open chatgpt" in command
        and re.search(
            r"\b(?:write|type|ask)\b",
            command,
            re.IGNORECASE
        )
    ):

        open_chatgpt_and_send(command)


    # --------------------------------------------------------
    # CHATGPT — simple open
    # --------------------------------------------------------

    elif (
        "open chatgpt" in command
        or command == "chatgpt"
    ):

        open_chatgpt()


    # --------------------------------------------------------
    # CHROME
    # --------------------------------------------------------

    elif "open chrome" in command:

        open_chrome()


    # --------------------------------------------------------
    # NOTEPAD
    # --------------------------------------------------------

    elif "open notepad" in command:

        open_notepad()


    # --------------------------------------------------------
    # CALCULATOR
    # --------------------------------------------------------

    elif (
        "open calculator" in command
        or "open calc" in command
    ):

        open_calculator()


    # --------------------------------------------------------
    # FILE EXPLORER
    # --------------------------------------------------------

    elif (
        "open file explorer" in command
        or "open explorer" in command
        or "open files" in command
    ):

        open_file_explorer()


    # --------------------------------------------------------
    # VS CODE
    # --------------------------------------------------------

    elif (
        "open vs code" in command
        or "open visual studio code" in command
    ):

        open_vs_code()


    # --------------------------------------------------------
    # WHATSAPP
    # --------------------------------------------------------

    elif "open whatsapp" in command:

        open_whatsapp()


    # --------------------------------------------------------
    # DOWNLOADS
    # --------------------------------------------------------

    elif "open downloads" in command:

        open_downloads()


    # --------------------------------------------------------
    # DESKTOP
    # --------------------------------------------------------

    elif "open desktop" in command:

        open_desktop()


    # --------------------------------------------------------
    # MUSIC
    # --------------------------------------------------------

    elif (
        "play music" in command
        or "open music" in command
    ):

        play_music()


    # --------------------------------------------------------
    # YOUTUBE SEARCH
    # --------------------------------------------------------

    elif (
        "search youtube for" in command
        or "search youtube" in command
    ):

        youtube_search(command)


    # --------------------------------------------------------
    # GOOGLE SEARCH
    # --------------------------------------------------------

    elif (
        "search google" in command
        or "search for" in command
    ):

        google_search(command)


    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------

    elif (
        "what is the time" in command
        or "what's the time" in command
        or "tell me the time" in command
    ):

        tell_time()


    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    elif (
        "what is the date" in command
        or "what is today's date" in command
        or "tell me the date" in command
    ):

        tell_date()


    # --------------------------------------------------------
    # VOLUME UP
    # --------------------------------------------------------

    elif (
        "increase volume" in command
        or "volume up" in command
        or "turn up volume" in command
    ):

        increase_volume()


    # --------------------------------------------------------
    # VOLUME DOWN
    # --------------------------------------------------------

    elif (
        "decrease volume" in command
        or "volume down" in command
        or "turn down volume" in command
    ):

        decrease_volume()


    # --------------------------------------------------------
    # MUTE
    # --------------------------------------------------------

    elif (
        "mute" in command
        or "mute volume" in command
    ):

        mute_volume()


    # --------------------------------------------------------
    # SCREENSHOT
    # --------------------------------------------------------

    elif (
        "take screenshot" in command
        or "take a screenshot" in command
        or "screenshot" in command
    ):

        take_screenshot()


    # --------------------------------------------------------
    # SHUTDOWN JARVIS
    # --------------------------------------------------------

    elif (
        command == "shutdown"
        or command == "shut down"
        or command == "exit"
        or command == "quit"
        or command == "goodbye"
    ):

        speak("Shutting down. Goodbye sir.")
        return False


    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    else:

        try:

            response = ask_ai(command)
            speak(response)

        except Exception as e:

            speak(f"AI error: {e}")
            speak("Sorry sir, I couldn't connect to the AI.")


    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("                 JARVIS AI")
    print("=" * 60)
    print()

    speak("System initialized.")
    speak("Hello sir. JARVIS is ready.")

    while True:

        command = listen()

        if not command:

            continue


        # ----------------------------------------------------
        # WAKE WORD CHECK
        # ----------------------------------------------------

        has_wake_word = any(
            word in command
            for word in WAKE_WORDS
        )

        if (
            not has_wake_word
            and not is_direct_command(command)
            and not is_ai_question(command)
        ):

            speak("Wake word not detected.")
            continue


        # ----------------------------------------------------
        # PROCESS
        # ----------------------------------------------------

        keep_running = process_command(command)

        if not keep_running:

            break


# ============================================================
# START JARVIS
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        speak("JARVIS stopped by user.")

    except Exception as e:

        print()
        speak(f"Unexpected error: {e}")
