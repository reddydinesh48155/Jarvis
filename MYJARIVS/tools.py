import subprocess
import webbrowser
import urllib.parse


def open_application(command):
    command = command.lower()

    # Chrome
    if "open chrome" in command:
        subprocess.Popen("start chrome", shell=True)
        return "Opening Chrome, sir."

    # Notepad
    elif "open notepad" in command:
        subprocess.Popen("notepad.exe")
        return "Opening Notepad, sir."

    # Calculator
    elif "open calculator" in command:
        subprocess.Popen("calc.exe")
        return "Opening Calculator, sir."

    # VS Code
    elif "open vs code" in command or "open visual studio code" in command:
        subprocess.Popen("code", shell=True)
        return "Opening Visual Studio Code, sir."

    # YouTube
    elif "open youtube" in command:
        webbrowser.open("https://www.youtube.com")
        return "Opening YouTube, sir."

    # Google
    elif "open google" in command:
        webbrowser.open("https://www.google.com")
        return "Opening Google, sir."

    return None


def search_google(command):
    search_text = command

    for phrase in [
        "search google for",
        "search google",
        "google search for",
        "search for"
    ]:
        search_text = search_text.replace(phrase, "").strip()

    if search_text:
        url = "https://www.google.com/search?q=" + urllib.parse.quote(search_text)
        webbrowser.open(url)
        return f"Searching Google for {search_text}, sir."

    return "What would you like me to search for, sir?"


def play_youtube(command):
    search_text = command

    for phrase in [
        "play youtube",
        "play on youtube",
        "youtube play",
        "play"
    ]:
        search_text = search_text.replace(phrase, "").strip()

    if search_text:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(search_text)
        webbrowser.open(url)
        return f"Searching YouTube for {search_text}, sir."

    return "What would you like me to play, sir?"