import sounddevice as sd
import speech_recognition as sr


SAMPLE_RATE = 16000
RECORD_SECONDS = 5


print("JARVIS microphone is ready.")
print("Speak now...")

audio_data = sd.rec(
    int(RECORD_SECONDS * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16"
)

sd.wait()

print("Recording finished.")
print("Converting speech to text...")

recognizer = sr.Recognizer()

audio = sr.AudioData(
    audio_data.tobytes(),
    SAMPLE_RATE,
    2
)

try:
    text = recognizer.recognize_google(audio)

    print("You said:", text)

except sr.UnknownValueError:
    print("JARVIS: I couldn't understand what you said.")

except sr.RequestError as error:
    print("JARVIS: Speech recognition service is unavailable.")
    print("Error:", error)