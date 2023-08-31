from typing import Optional
from hugchat.hugchat import ChatBot
from deepl import Translator

class UserData:
    def __init__(self, chatbot: ChatBot, filename: str, temperature: float = 0.9):
        self.chatbot: ChatBot = chatbot
        self.filename: str = filename
        self.temperature: float = temperature
        self.language: Optional[str] = None
        self.translator: Optional[Translator] = None
