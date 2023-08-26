# Telechat

A telegram bot that allows you to chat with HuggingChat (Llama2)

# Requirements

* Python 3.9+

# Installation

* `python -m venv venv`
* `source venv/bin/activate` (different for windows, see [here](https://docs.python.org/3/library/venv.html#creating-virtual-environments))
* `pip install -r requirements.txt`
* `cp config.json.example config.json`
* `cp allowed_users.json.example allowed_users.json`
* `cp admins.json.example admins.json`
* add your telegram bot token to `config.json`
  * you can create a bot and get the token from the [BotFather](https://t.me/botfather)
* add user(s) to `allowed_users.json` and `admins.json`
  * valid entries for `allowed_users.json` and `admins.json` are either the username or the userid of a telegram user
* `cd src`
* `python telechat.py`
