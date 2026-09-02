import sounddevice as sd

print("Microphone test started.")
print("Speak for 5 seconds...")

recording = sd.rec(
    int(5 * 16000),
    samplerate=16000,
    channels=1,
    dtype="int16"
)

sd.wait()

print("Recording finished.")
print("JARVIS can access your microphone!")