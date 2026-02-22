# -*- coding: utf-8 -*-
"""
Monitor cen metali szlachetnych - Tavex
Autor: Ty (z małą pomocą AI)
Kopiowanie na Raspberry: scp monitor_cen.py config.json pi@192.168.1.101:/home/pi/python_scripts/
"""

import requests
from bs4 import BeautifulSoup
import json
import smtplib
import os
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email import encoders
import re

# --- USTALENIE ŚCIEŻEK ---
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --- WCZYTYWANIE KONFIGURACJI Z JSON ---
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    print(f"❌ Błąd: Plik {CONFIG_FILE} nie istnieje!")
    print("\nTwórz plik config.json z następującą zawartością:")
    print(json.dumps({
        "email_sender": "twoj_email@gmail.com",
        "email_password": "twoje_haslo_aplikacji",
        "email_receivers": ["dstatnik@protonmail.com"],
        "products": {
            "Złoty Dukat Austriacki 3,44 g": "https://tavex.pl/zlote-monety/zloty-dukat-austriacki-3-44-g"
        }
    }, indent=2, ensure_ascii=False))
    exit(1)

try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except json.JSONDecodeError as e:
    print(f"❌ Błąd w formacie JSON: {e}")
    exit(1)

EMAIL_SENDER = CONFIG.get("email_sender")
EMAIL_PASSWORD = CONFIG.get("email_password")
EMAIL_RECEIVERS = CONFIG.get("email_receivers", [])
PRODUCTS = CONFIG.get("products_inwest", {})

if not EMAIL_SENDER or not EMAIL_PASSWORD:
    print("❌ Błąd: email_sender lub email_password nie ustawione w config.json")
    exit(1)

if not PRODUCTS:
    print("❌ Błąd: Brak produktów w config.json")
    exit(1)

if not EMAIL_RECEIVERS:
    print("❌ Błąd: Brak odbiorców email w config.json")
    exit(1)

DATA_FILE = "price_history_spread.csv"

def clean_filename(name): # Zamienia niedozwolone znaki w nazwie pliku na myślniki
    return re.sub(r'[\\/*?:"<>|]', "-", name)

def get_prices(url): # Pobiera ceny sprzedaży i skupu z podanego URL-a Tavexdef get_prices(url): # Pobiera ceny sprzedaży i skupu z podanego URL-a Tavex
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        tag = soup.find("span", class_="product-poster__price-value")
        if tag and tag.has_attr('data-pricelist'):
            data = json.loads(tag['data-pricelist'])
            sell = float(data['sell'][0]['price']) if data.get('sell') else None
            buy = float(data['buy'][0]['price']) if data.get('buy') else None
            return sell, buy
    except Exception:
        pass
    return None, None

def create_chart(product_name):
    if not os.path.exists(DATA_FILE): return None
    df = pd.read_csv(DATA_FILE, encoding='utf-8')
    product_data = df[df['product'] == product_name].tail(15) # Pobiera ostatnie 15 wpisów dla danego produktu, aby nie robić zbyt zatłoczonego wykresu
    if len(product_data) < 2: return None

    plt.figure(figsize=(8, 4))
    plt.plot(product_data['date'], product_data['sell_price'], color='#d4af37', marker='o', label='Sprzedaż')
    plt.plot(product_data['date'], product_data['buy_price'], color='#707070', linestyle='--', label='Skup')
    plt.title(f"Trend: {product_name}")
    plt.xticks(rotation=35, ha='right')
    plt.legend()
    plt.tight_layout()
    
    path = f"chart_{clean_filename(product_name)}.png" # Tworzy nazwę pliku wykresu na podstawie nazwy produktu, usuwając niedozwolone znaki
    plt.savefig(path) 
    plt.close()
    return path

def send_combined_report(changes_list): # Wysyła jeden email z raportem dla wszystkich produktów, które zmieniły cenę
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = ", ".join(EMAIL_RECEIVERS)
    msg['Subject'] = f"📊 RAPORT ZMIAN CEN ({len(changes_list)} produktów)"

    full_body = "Wykryto zmiany cen dla Twoich produktów:\n\n"
    attachments = []

    for c in changes_list:
        trend = "📈 WZROST" if c['diff'] > 0 else "📉 SPADEK"
        spread_pct = round((c['spread'] / c['new']) * 100, 2)
        diff_pct = round(((c['new'] - c['old']) / c['old']) * 100, 2) if c['old'] > 0 else 0
        
        full_body += (
            f"--- ALERT CENOWY: {c['name']} ---\n"
            f"Trend: {trend} o {c['diff']} PLN ({diff_pct}%)\n"
            f"🛒 Cena zakupu: {c['new']} PLN\n"
            f"💰 Cena skupu: {c['buy']} PLN\n"
            f"⚖️ Spread: {c['spread']} PLN ({spread_pct}%)\n"
            f"Poprzednia cena: {c['old']} PLN\n"
            f"--------------------------------------------\n\n"
        )
        chart = create_chart(c['name'])
        if chart: attachments.append(chart)

    msg.attach(MIMEText(full_body, 'plain'))
    for cp in attachments:
        with open(cp, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(cp))
            msg.attach(img)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
        print("✅ Wysłano raport zbiorczy.")
    finally:
        for p in attachments: # Usuwa tymczasowe pliki wykresów po wysłaniu emaila
            if os.path.exists(p): os.remove(p)

def send_weekly_summary():
    if not os.path.exists(DATA_FILE):
        print("⚠️ Brak pliku z historią cen.")
        return
    
    try:
        df = pd.read_csv(DATA_FILE, encoding='utf-8')
    except Exception as e:
        print(f"❌ Błąd czytania pliku CSV: {e}")
        return
    
    df['date'] = pd.to_datetime(df['date'])
    one_week_ago = datetime.now() - timedelta(days=7)
    recent_data = df[df['date'] > one_week_ago]
    
    if recent_data.empty:
        print("⚠️ Brak danych z ostatnich 7 dni - raport nie zostanie wysłany.")
        return

    summary_body = "📊 PODSUMOWANIE TYGODNIOWE\n==========================\n\n"
    for product in recent_data['product'].unique():
        p_data = recent_data[recent_data['product'] == product].sort_values('date')
        if len(p_data) >= 2:
            start_p = p_data.iloc[0]['sell_price']
            end_p = p_data.iloc[-1]['sell_price']
            diff = round(end_p - start_p, 2)
            pct = round((diff / start_p) * 100, 2)
            emoji = "📈" if diff > 0 else "📉"
            min_price = p_data['sell_price'].min()
            max_price = p_data['sell_price'].max()
            summary_body += f"🔹 {product}:\n   Cena 7 dni temu: {start_p} PLN | Dziś: {end_p} PLN\n   Wynik: {emoji} {diff} PLN ({pct}%)\n   Min/Max: {min_price} - {max_price} PLN\n   --------------------------\n"

    msg = MIMEMultipart() 
    msg['From'] = EMAIL_SENDER
    msg['To'] = ", ".join(EMAIL_RECEIVERS)
    msg['Subject'] = f"📆 PODSUMOWANIE TYGODNIOWE: {datetime.now().strftime('%d.%m.%Y')}"
    msg.attach(MIMEText(summary_body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
        print("📆 Wysłano raport tygodniowy.")
    except smtplib.SMTPAuthenticationError:
        print("❌ Błąd: Nieprawidłowy email lub hasło Gmail.")
    except Exception as e:
        print(f"❌ Błąd wysyłania raportu tygodniowego: {e}")

def send_monthly_summary():
    if not os.path.exists(DATA_FILE):
        print("⚠️ Brak pliku z historią cen.")
        return
    
    try:
        df = pd.read_csv(DATA_FILE, encoding='utf-8')
    except Exception as e:
        print(f"❌ Błąd czytania pliku CSV: {e}")
        return
    
    df['date'] = pd.to_datetime(df['date'])
    one_month_ago = datetime.now() - timedelta(days=30)
    recent_data = df[df['date'] > one_month_ago]
    
    if recent_data.empty:
        print("⚠️ Brak danych z ostatnich 30 dni - raport nie zostanie wysłany.")
        return

    summary_body = "📊 PODSUMOWANIE MIESIĘCZNE\n==========================\n\n"
    for product in recent_data['product'].unique():
        p_data = recent_data[recent_data['product'] == product].sort_values('date')
        if len(p_data) >= 2:
            start_p = p_data.iloc[0]['sell_price']
            end_p = p_data.iloc[-1]['sell_price']
            diff = round(end_p - start_p, 2)
            pct = round((diff / start_p) * 100, 2)
            emoji = "📈" if diff > 0 else "📉"
            summary_body += f"🔹 {product}:\n   Cena 30 dni temu: {start_p} PLN | Dziś: {end_p} PLN\n   Wynik: {emoji} {diff} PLN ({pct}%)\n   --------------------------\n"

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = ", ".join(EMAIL_RECEIVERS)
    msg['Subject'] = f"📅 PODSUMOWANIE MIESIĘCZNE: {datetime.now().strftime('%B %Y')}"
    msg.attach(MIMEText(summary_body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
        print("📅 Wysłano raport miesięczny.")
    except smtplib.SMTPAuthenticationError:
        print("❌ Błąd: Nieprawidłowy email lub hasło Gmail.")
    except Exception as e:
        print(f"❌ Błąd wysyłania raportu miesięcznego: {e}")


def monitor():
    if not PRODUCTS:
        print("❌ Brak produktów do monitorowania. Sprawdź plik config.json!")
        return

    if not os.path.exists(DATA_FILE):
        pd.DataFrame(columns=['date', 'product', 'sell_price', 'buy_price', 'spread_pln']).to_csv(DATA_FILE, index=False, encoding='utf-8')

    changes_detected = []
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M")
    print(f"⏰ Sprawdzanie cen: {now_str}")

    df = pd.read_csv(DATA_FILE, encoding='utf-8')

    for name, url in PRODUCTS.items():
        sell, buy = get_prices(url)
        if sell is None: 
            print(f"⚠️ Problem z ceną dla: {name}")
            continue

        last_entry = df[df['product'] == name].tail(1)
        last_sell = last_entry['sell_price'].values[0] if not last_entry.empty else None

        new_row = pd.DataFrame([{'date': now_str, 'product': name, 'sell_price': sell, 'buy_price': buy, 'spread_pln': round(sell - buy, 2)}])
        df = pd.concat([df, new_row], ignore_index=True)

        if last_sell is not None:
            if sell != last_sell:
                changes_detected.append({
                    'name': name, 'old': last_sell, 'new': sell,
                    'buy': buy, 'diff': round(sell - last_sell, 2),
                    'spread': round(sell - buy, 2)
                })
            else:
                print(f"😴 {name}: stabilnie ({sell} PLN)")
        else:
            print(f"🆕 Zainicjowano: {name}")

    df.to_csv(DATA_FILE, index=False, encoding='utf-8')

    if changes_detected:
        print(f"🚨 Wykryto {len(changes_detected)} zmian. Wysyłanie raportu...")
        for c in changes_detected:
            trend = "📈 WZROST" if c['diff'] > 0 else "📉 SPADEK"
            # print(f"   {c['name']}: {trend} o {c['diff']} PLN (nowa cena: {c['new']} PLN)")
        send_combined_report(changes_detected)
    else:
        print("✅ Brak zmian cen. Nie wysyłamy raportu.")   
    
    # Raport tygodniowy - każdy poniedziałek (godzina 7:00)
    if now_dt.weekday() == 0 and 7 <= now_dt.hour < 8:
        print("📆 Generowanie raportu tygodniowego...")
        send_weekly_summary()
    
    # Raport miesięczny - 1-szego dnia miesiąca (godzina 7:00)
    if now_dt.day == 1 and 7 <= now_dt.hour < 8:
        print("📅 Generowanie raportu miesięcznego...")
        send_monthly_summary()

if __name__ == "__main__":
    monitor()