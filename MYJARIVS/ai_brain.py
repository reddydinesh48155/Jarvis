import requests


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:3b"
SYSTEM_PROMPT = (
    "You are JARVIS, a helpful personal AI assistant. "
    "Answer directly, concisely, and in plain English."
)


class AIBrain:

    def __init__(self):
        self.conversation = []

    def ask(self, question):

        self.conversation.append({
            "role": "user",
            "content": question
        })

        prompt = SYSTEM_PROMPT + "\n\nConversation:\n"

        for message in self.conversation:
            prompt += (
                f"{message['role']}: "
                f"{message['content']}\n"
            )

        prompt += "\nJARVIS:"

        try:

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": "5m",
                    "options": {
                        "temperature": 0.2,
                        "num_ctx": 4096,
                        "num_predict": 128
                    }
                },
                timeout=60
            )

            response.raise_for_status()

            data = response.json()

            answer = data.get(
                "response",
                "Sorry sir, I couldn't generate a response."
            ).strip()

            self.conversation.append({
                "role": "assistant",
                "content": answer
            })

            return answer

        except requests.exceptions.ConnectionError:

            return "Sorry sir, Ollama is not running."

        except Exception as e:

            return f"Sorry sir, I encountered an error: {e}"


# Simple function for main.py
brain = AIBrain()


def ask_ai(question):
    return brain.ask(question)
