from hugchat import hugchat

class UserData:
    def __init__(self, chatbot: hugchat.ChatBot, temperature: float = 0.9):
        self.chatbot = chatbot
        self.temperature = temperature
