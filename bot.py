import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
from datetime import datetime
import os
from dotenv import load_dotenv

# Ielādēt vides mainīgos
load_dotenv()

# Initialize bot
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))

# Database setup
conn = sqlite3.connect('ss_tracker.db', check_same_thread=False)
cursor = conn.cursor()

# Create tables

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    subscription_type TEXT DEFAULT 'free',
    subscription_expiry DATE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS searches (
    search_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    make TEXT,
    model TEXT,
    year_from INTEGER,
    year_to INTEGER,
    price_from INTEGER,
    price_to INTEGER,
    last_checked TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS ads (
    ad_id TEXT PRIMARY KEY,
    search_id INTEGER,
    title TEXT,
    price TEXT,
    url TEXT,
    date_posted TEXT,
    is_new BOOLEAN DEFAULT 1,
    FOREIGN KEY(search_id) REFERENCES searches(search_id)
)
''')

conn.commit()

# SS.com scraping function
def scrape_ss(category, make, model, year_from=None, year_to=None, price_from=None, price_to=None):
    base_url = "https://www.ss.com/lv/transport/cars/"
    url = f"{base_url}{make}/{model}/"
    
    # Add filters to URL
    params = []
    if year_from:
        params.append(f"year_from={year_from}")
    if year_to:
        params.append(f"year_to={year_to}")
    if price_from:
        params.append(f"price_from={price_from}")
    if price_to:
        params.append(f"price_to={price_to}")
    
    if params:
        url += "sell/" + "&".join(params) + "/"
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        ads = []
        for row in soup.select('tr[id^="tr_"]:not(.head_line)'):
            # Izlaižam reklāmas rindas
            if 'bnr' in row.get('id', ''):
                continue
                
            ad_id = row.get('id').replace('tr_', '')
            
            # Iegūstam nosaukumu
            title_elem = row.select_one('a.am')
            title = title_elem.text.strip() if title_elem else "No title"
            
            # Iegūstam visas datu šūnas
            tds = row.select('td.msga2-o')
            
            # Inicializējam datu vārdnīcu
            ad_data = {
                'ad_id': ad_id,
                'title': title,
                'price': "Nav norādīta",
                'year': "Nav norādīts",
                'engine': "Nav norādīts",
                'transmission': "Nav norādīta",
                'date': "Nav norādīts",
                'url': "https://www.ss.com" + title_elem['href'] if title_elem else ""
            }
            
            # Mēģinam identificēt kolonnas pēc to indeksa un satura
            col_index = 0
            for td in tds:
                text = td.text.strip()
                # Cena parasti ir pēdējā kolonna un satur € simbolu
                if '€' in text:
                    ad_data['price'] = text
                # Gads parasti ir skaitlis no 1900-2099
                elif text.isdigit() and 1900 <= int(text) <= 2099:
                    ad_data['year'] = text
                # Dzinēja tips parasti satur "D" vai "B" vai "benzīns" vai "dīzelis"
                elif any(fuel in text.lower() for fuel in ['d', 'b', 'benzīns', 'dīzelis', 'benzins', 'dizelis', 'гибрид', 'hybrid']):
                    ad_data['engine'] = text
                # Ātrumkārba parasti satur "A" vai "M" vai "automāts" vai "manuāla"
                elif any(trans in text.lower() for trans in ['a', 'm', 'automāts', 'manuāla', 'automats', 'manuala', 'автомат', 'механика']):
                    ad_data['transmission'] = text
                # Datums parasti ir formātā dd.mm.yyyy vai līdzīgā
                elif '.' in text and len(text) >= 8:
                    ad_data['date'] = text
                
                col_index += 1
            
            ads.append(ad_data)
        
        return ads
    
    except Exception as e:
        print(f"Error scraping SS.com: {e}")
        return []

# Check for new ads periodically
def check_new_ads():
    while True:
        cursor.execute("SELECT * FROM searches")
        searches = cursor.fetchall()
        
        for search in searches:
            search_id, user_id, category, make, model, year_from, year_to, price_from, price_to, last_checked = search
            
            # Get current ads from SS.com
            current_ads = scrape_ss(category, make, model, year_from, year_to, price_from, price_to)
            
            # Get stored ads from DB
            cursor.execute("SELECT ad_id FROM ads WHERE search_id = ?", (search_id,))
            stored_ads = [row[0] for row in cursor.fetchall()]
            
            # Find new ads
            new_ads = [ad for ad in current_ads if ad['ad_id'] not in stored_ads]
            
            # Save all current ads to DB
            for ad in current_ads:
                is_new = ad['ad_id'] in [new_ad['ad_id'] for new_ad in new_ads]
                cursor.execute('''
                INSERT OR REPLACE INTO ads (ad_id, search_id, title, price, url, date_posted, is_new)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (ad['ad_id'], search_id, ad['title'], ad['price'], ad['url'], ad['date'], is_new))
            
            # Notificē lietotāju par jauniem sludinājumiem
            for ad in new_ads:
                # Pārbaudām, vai sludinājumā ir derīgi dati
                if ad['title'] == "No title" and ad['price'] == "No price" and ad['date'] == "No date":
                # Izlaižam "tukšos" sludinājumus
                    continue
        
                # Pārbaudām, vai ir vismaz nosaukums un URL
                if ad['title'] != "No title" and ad['url']:
                    emoji = "🟢"  # Zaļš aplis jauniem sludinājumiem
        
                    # Veidojam ziņu tikai ar tiem datiem, kas ir pieejami
                    message = f"{emoji} Jauns sludinājums!\n\n{ad['title']}"
                    
                    if ad['year'] != "Nav norādīts":
                        message += f"\nGads: {ad['year']}"

                    if ad['engine'] != "Nav norādīts":
                        message += f"\nDzinējs: {ad['engine']}"    

                    if ad['transmission'] != "Nav norādīta":
                        message += f"\nĀtrumkārba: {ad['transmission']}"
                        
                    if ad['price'] != "No price":
                        message += f"\nCena: {ad['price']}"
                    
                    if ad['url']:
                        message += f"\n\n{ad['url']}"
            
                    bot.send_message(user_id, message)
                     
            # Update last checked time
            cursor.execute("UPDATE searches SET last_checked = ? WHERE search_id = ?", (datetime.now(), search_id))
            conn.commit()
        
        time.sleep(30)  # Sekundes pēc cik tiek pārbaudīts

# Start the checking thread
import threading
thread = threading.Thread(target=check_new_ads)
thread.daemon = True
thread.start()

# Bot commands
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    # Check if user exists
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    
    bot.reply_to(message, "👋 Sveiki! Šis bots palīdz sekot līdzi jaunajiem sludinājumiem SS.com.\n\nIzmantojiet komandu /search, lai sāktu jaunu meklēšanu.")

@bot.message_handler(commands=['search'])
def start_search(message):
    user_id = message.from_user.id
    
    # Check user's subscription status
    cursor.execute("SELECT subscription_type FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if user and user[0] == 'free':
        # Check how many searches user already has
        cursor.execute("SELECT COUNT(*) FROM searches WHERE user_id = ?", (user_id,))
        search_count = cursor.fetchone()[0]
        
        if search_count >= 1:  # Free users can have only 1 search
            bot.send_message(user_id, "⚠️ Jūsu bezmaksas konts atļauj tikai vienu meklēšanu. Ja vēlaties pievienot vairāk meklēšanu, iegādājieties Premium vai VIP versiju.",
                           reply_markup=get_subscription_keyboard())
            return
    
    # Start search process
    msg = bot.send_message(user_id, "Lūdzu, ievadiet automašīnas marku (piemēram, Audi, BMW):")
    bot.register_next_step_handler(msg, process_make_step)

def process_make_step(message):
    try:
        make = message.text.strip()
        user_id = message.from_user.id
        
        msg = bot.send_message(user_id, f"Lūdzu, ievadiet modeli markai {make} (piemēram, A4, X5):")
        bot.register_next_step_handler(msg, process_model_step, make)
    except Exception as e:
        bot.reply_to(message, f"Kļūda: {e}")

def process_model_step(message, make):
    try:
        model = message.text.strip()
        user_id = message.from_user.id
        
        # Ask if user wants to add year filter
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Jā", callback_data=f"year_yes_{make}_{model}"),
            InlineKeyboardButton("Nē", callback_data=f"year_no_{make}_{model}")
        )
        
        bot.send_message(user_id, "Vai vēlaties norādīt gada diapazonu?", reply_markup=markup)
    except Exception as e:
        bot.reply_to(message, f"Kļūda: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('year_'))
def handle_year_choice(call):
    try:
        print(f"Callback received: {call.data}")  # Atkļūdošana
        user_id = call.from_user.id
        parts = call.data.split('_')
        print(f"Parts: {parts}")  # Atkļūdošana
        
        if len(parts) < 4:
            raise ValueError("Nepilni callback dati")
            
        action = parts[1]
        make = parts[2]
        model = parts[3]
        
        if action == 'yes':
            msg = bot.send_message(user_id, "Lūdzu, ievadiet gada diapazonu formātā 'no līdz' (piemēram, 2010 2020):")
            bot.register_next_step_handler(msg, process_year_step, make, model)
        else:
            ask_price_filter(user_id, make, model, None, None)
    except Exception as e:
        error_msg = f"Kļūda: {str(e)}\nCallback data: {call.data}"
        print(error_msg)  # Konsoles log
        bot.send_message(user_id, error_msg)

def process_year_step(message, make, model):
    try:
        year_input = message.text.strip().split()
        year_from = int(year_input[0]) if len(year_input) > 0 else None
        year_to = int(year_input[1]) if len(year_input) > 1 else None
        user_id = message.from_user.id
        
        ask_price_filter(user_id, make, model, year_from, year_to)
    except Exception as e:
        bot.reply_to(message, f"Kļūda: {e}. Lūdzu, ievadiet gada diapazonu formātā 'no līdz' (piemēram, 2010 2020)")

def ask_price_filter(user_id, make, model, year_from, year_to):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Jā", callback_data=f"price_yes_{make}_{model}_{year_from or ''}_{year_to or ''}"),
        InlineKeyboardButton("Nē", callback_data=f"price_no_{make}_{model}_{year_from or ''}_{year_to or ''}")
    )
    
    bot.send_message(user_id, "Vai vēlaties norādīt cenas diapazonu?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('price_'))
def handle_price_choice(call):
    try:
        user_id = call.from_user.id
        parts = call.data.split('_')
        print(f"Debug: {parts}")  # Atkļūdošanai
        
        # Pārbaudām, vai ir pietiekami daudz daļu
        if len(parts) < 6:
            raise ValueError(f"Nepilni callback dati: {call.data}")
            
        action = parts[1]
        make = parts[2]
        model = parts[3]
        
        # Apstrādājam gada diapazonu
        year_from = None if parts[4] in ('', 'null', 'None') else int(parts[4])
        year_to = None if parts[5] in ('', 'null', 'None') else int(parts[5])
        
        if action == 'yes':
            msg = bot.send_message(user_id, 
                "Lūdzu, ievadiet cenas diapazonu EUR formātā 'no līdz' (piemēram: 5000 15000):")
            bot.register_next_step_handler(msg, process_price_step, make, model, year_from, year_to)
        else:
            # Saglabājam meklēšanu bez cenas filtra
            save_search(user_id, 'cars', make, model, year_from, year_to, None, None)
            
            # Sastādām skaidru atbildi
            year_info = f"{year_from}-{year_to}" if year_from or year_to else "nav norādīts"
            response = (
                f"✅ Meklēšana saglabāta!\n\n"
                f"🔹 Marka: {make}\n"
                f"🔹 Modelis: {model}\n"
                f"🔹 Gadu diapazons: {year_info}\n"
                f"🔹 Cenas diapazons: nav filtra\n\n"
                f"Jūs saņemsit paziņojumus par jauniem sludinājumiem!"
            )
            bot.send_message(user_id, response)
            
    except Exception as e:
        print(f"Kļūda handle_price_choice: {e}\nDati: {call.data}")
        bot.send_message(user_id, "⚠️ Radās kļūda. Lūdzu, mēģiniet vēlreiz ar /search")

def process_price_step(message, make, model, year_from, year_to):
    try:
        price_input = message.text.strip().split()
        price_from = int(price_input[0]) if len(price_input) > 0 else None
        price_to = int(price_input[1]) if len(price_input) > 1 else None
        user_id = message.from_user.id
        
        save_search(user_id, 'cars', make, model, year_from, year_to, price_from, price_to)
    except Exception as e:
        bot.reply_to(message, f"Kļūda: {e}. Lūdzu, ievadiet cenas diapazonu formātā 'no līdz' (piemēram, 5000 15000)")

def save_search(user_id, category, make, model, year_from, year_to, price_from, price_to):
    cursor.execute('''
    INSERT INTO searches (user_id, category, make, model, year_from, year_to, price_from, price_to, last_checked)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, category, make, model, year_from, year_to, price_from, price_to, datetime.now()))
    conn.commit()
    
    # Get the search details for confirmation message
    search_details = f"Marka: {make}\nModelis: {model}"
    if year_from or year_to:
        search_details += f"\nGadi: {year_from or '?'} - {year_to or '?'}"
    if price_from or price_to:
        search_details += f"\nCena: {price_from or '?'} - {price_to or '?'} EUR"
    
    bot.send_message(user_id, f"🔍 Meklēšana saglabāta!\n\n{search_details}\n\nJūs saņemsiet paziņojumus par jauniem sludinājumiem.")

def get_subscription_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Premium (3 meklēšanas) - 5€/mēnesī", callback_data="subscribe_premium")
    )
    markup.row(
        InlineKeyboardButton("VIP (neierobežoti) - 10€/mēnesī", callback_data="subscribe_vip")
    )
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('subscribe_'))
def handle_subscription(call):
    user_id = call.from_user.id
    plan = call.data.split('_')[1]
    
    # In a real implementation, you would integrate with a payment provider here
    # For demonstration, we'll just update the user's subscription status
    
    if plan == 'premium':
        cursor.execute("UPDATE users SET subscription_type = 'premium' WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(user_id, "Paldies par Premium abonementa iegādi! Tagad varat pievienot līdz 3 meklēšanām.")
    elif plan == 'vip':
        cursor.execute("UPDATE users SET subscription_type = 'vip' WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(user_id, "Paldies par VIP abonementa iegādi! Tagad varat pievienot neierobežotu skaitu meklēšanu.")

# Izmainītā funkcija kas parāda meklēšanas ar dzēšanas pogām
@bot.message_handler(commands=['mysearches'])
def show_searches(message):
    user_id = message.from_user.id
    
    cursor.execute("SELECT * FROM searches WHERE user_id = ?", (user_id,))
    searches = cursor.fetchall()
    
    if not searches:
        bot.send_message(user_id, "Jums nav saglabātu meklēšanu. Izmantojiet /search, lai sāktu jaunu meklēšanu.")
        return
    
    for search in searches:
        search_id, _, category, make, model, year_from, year_to, price_from, price_to, last_checked = search
        
        # Izveido aprakstu ar visiem saglabātajiem parametriem
        search_info = f"🔍 {make} {model}"
        year_info = ""
        if year_from or year_to:
            year_info = f"Gadi: {year_from or 'jebkurš'}-{year_to or 'jebkurš'}"
        
        price_info = ""
        if price_from or price_to:
            price_info = f"Cena: {price_from or 'jebkura'}-{price_to or 'jebkura'}€"
        
        # Sagatavo pilnu tekstu par meklēšanu
        details = f"{search_info}\n"
        if year_info:
            details += f"{year_info}\n"
        if price_info:
            details += f"{price_info}\n"
        
        # Pievienojam pēdējās pārbaudes laiku
        if last_checked:
            details += f"Pēdējā pārbaude: {last_checked}\n"
        
        # Izveido pogu dzēšanai
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🗑️ Dzēst šo meklēšanu", callback_data=f"delete_search_{search_id}"))
        
        bot.send_message(user_id, details, reply_markup=markup)

# Jauna funkcija kas apstrādā dzēšanas pogas nospiešanu
@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_search_'))
def handle_delete_search(call):
    try:
        user_id = call.from_user.id
        search_id = int(call.data.split('_')[2])
        
        # Pārbaudām, vai šī meklēšana pieder lietotājam (drošībai)
        cursor.execute("SELECT user_id FROM searches WHERE search_id = ?", (search_id,))
        result = cursor.fetchone()
        
        if result and result[0] == user_id:
            # Vispirms dzēšam visus sludinājumus, kas saistīti ar šo meklēšanu
            cursor.execute("DELETE FROM ads WHERE search_id = ?", (search_id,))
            
            # Tad dzēšam pašu meklēšanu
            cursor.execute("DELETE FROM searches WHERE search_id = ?", (search_id,))
            conn.commit()
            
            # Atjaunojam ziņojumu, lai parādītu, ka dzēšana ir veiksmīga
            bot.edit_message_text(
                "✅ Meklēšana veiksmīgi dzēsta!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
            
            # Piedāvājam izveidot jaunu meklēšanu
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔍 Izveidot jaunu meklēšanu", callback_data="start_new_search"))
            bot.send_message(user_id, "Vai vēlaties izveidot jaunu meklēšanu?", reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "Kļūda: Meklēšana netika atrasta vai nav jūsu!")
    except Exception as e:
        print(f"Kļūda dzēšot meklēšanu: {e}")
        bot.answer_callback_query(call.id, "Notika kļūda. Lūdzu, mēģiniet vēlreiz.")

# Papildu funkcija jaunas meklēšanas sākšanai no pogas
@bot.callback_query_handler(func=lambda call: call.data == "start_new_search")
def start_new_search_callback(call):
    # Tā vietā, lai izsauktu start_search() ar ziņas objektu,
    # mēs vienkārši turpinām procesu ar jaunu ziņu
    user_id = call.from_user.id
    msg = bot.send_message(user_id, "Lūdzu, ievadiet automašīnas marku (piemēram, Audi, BMW):")
    bot.register_next_step_handler(msg, process_make_step)
    
    # Atbildam uz callback, lai pazustu "pulkstenis"
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
🆘 SS.com Tracker - Palīdzība

Komandas:
/start - Sākt darbu ar botu
/search - Pievienot jaunu meklēšanu
/mysearches - Apskatīt savas meklēšanas
/help - Šī palīdzība

Abonementi:
- Bezmaksas: 1 meklēšana
- Premium (5€/mēnesī): 3 meklēšanas
- VIP (10€/mēnesī): Neierobežotas meklēšanas

Jaunie sludinājumi tiks atzīmēti ar 🟢 (zaļu bumbiņu)
"""
    bot.send_message(message.chat.id, help_text)

# Start the bot
bot.polling()
