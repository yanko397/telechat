from hugchat import hugchat

class UserData:
    def __init__(self, chatbot: hugchat.ChatBot, filename: str, temperature: float = 0.9):
        self.chatbot = chatbot
        self.filename = filename
        self.temperature = temperature
