# Scraper Telegram Bot

This is a Telegram bot that scrapes [ss.com](https://ss.com) for classified ads based on user-defined search criteria. Users can interact with the bot directly via Telegram and receive updates when new relevant listings appear.

## Features

- Scrapes ads from ss.com based on search filters
- Sends updates to users through Telegram
- Stores and tracks previous search results in SQLite database
- Runs as a systemd service on a server (e.g., Hetzner)

## Requirements

- Python 3.8+
- SQLite3
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

## Installation

1. **Clone the repository:**

```bash
git clone https://github.com/RoSciPer/Scraping.git
cd Scraping


2. Create and activate a virtual environment:

bash
python3 -m venv venv
source venv/bin/activate



3. Install dependencies:

bash
pip install -r requirements.txt
Configure the bot:



4. Edit your environment variables or config to include your Telegram Bot Token.

Run the bot manually:

bash
python bot.py

4.1. Or set it up as a systemd service (optional for server use).

Example in Action
You can test the bot live on Telegram. Once it's deployed, interact with it via Telegram (Contact @DalgoSI or @CoinToken777).

Users can:

Start the bot

Submit a search request

Receive new listings when they appear

Notes
ss_tracker.db keeps track of previous searches and found ads.

The bot uses requests, beautifulsoup4, and sqlite3.

License
MIT License

Author
RoSciPer
