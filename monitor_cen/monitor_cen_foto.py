# -*- coding: utf-8 -*-
"""
Monitor cen obiektywów Fuji X - Fotoforma.pl
Śledzi ceny i dostępność obiektywów systemu Fuji X dla aparatu XT-30 II.
Wykrywa zmiany cen oraz zmiany dostępności (np. pojawienie się na stanie).

Konfiguracja w pliku config.json (klucz 'products_foto').
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
import re
from typing import Optional

# --- USTALENIE ŚCIEŻEK ---
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --- WCZYTYWANIE KONFIGURACJI Z JSON ---
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    print(f"❌ Błąd: Plik {CONFIG_FILE} nie istnieje!")
    exit(1)

try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except json.JSONDecodeError as e:
    print(f"❌ Błąd w formacie JSON: {e}")
    exit(1)

EMAIL_SENDER    = CONFIG.get("email_sender")
EMAIL_PASSWORD  = CONFIG.get("email_password")
EMAIL_RECEIVERS = CONFIG.get("email_receivers", [])
PRODUCTS        = CONFIG.get("products_foto", {})

if not EMAIL_SENDER or not EMAIL_PASSWORD:
    print("❌ Błąd: email_sender lub email_password nie ustawione w config.json")
    exit(1)

if not PRODUCTS:
    print("❌ Błąd: Brak produktów w sekcji 'products_foto' w config.json")
    exit(1)

if not EMAIL_RECEIVERS:
    print("❌ Błąd: Brak odbiorców email w config.json")
    exit(1)

DATA_FILE = "price_history_foto.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8",
}

# Słownik opisów dostępności do wyświetlania w emailach
AVAIL_LABELS = {
    "dostępny":           "✅ dostępny",
    "magazyn dostawcy":   "📦 magazyn dostawcy",
    "na wyczerpaniu":     "⚠️ na wyczerpaniu",
    "niedostępny":        "❌ niedostępny",
    "zamówienie":         "🕐 na zamówienie",
}


def clean_filename(name: str) -> str:
    """Zamienia niedozwolone znaki w nazwie pliku na myślniki."""
    return re.sub(r'[\\/*?:"<>|]', "-", name)


def parse_price(text: str) -> Optional[float]:
    """Konwertuje tekst ceny np. '3 899,00 zł' → 3899.0."""
    if not text:
        return None
    cleaned = re.sub(r'[^\d,]', '', text.replace('\xa0', '').replace(' ', ''))
    cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def avail_label(raw: str) -> str:
    """Zwraca czytelną etykietę dostępności."""
    lower = raw.lower().strip()
    for key, label in AVAIL_LABELS.items():
        if key in lower:
            return label
    return raw.strip()


def get_product_info(url: str) -> tuple:
    """
    Pobiera cenę i dostępność produktu z fotoforma.pl.
    Zwraca (cena_float, tekst_dostepnosci).
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # --- CENA ---
        price_em = soup.find('em', class_='main-price')
        price = parse_price(price_em.get_text(strip=True)) if price_em else None

        # --- DOSTĘPNOŚĆ ---
        avail_div = soup.find('div', class_='availability__availability')
        availability = "nieznana"
        if avail_div:
            status_span = avail_div.find('span', class_='second')
            if status_span:
                availability = status_span.get_text(strip=True)

        return price, availability

    except requests.RequestException as e:
        print(f"    ⚠️ Błąd pobierania: {e}")
        return None, "błąd połączenia"
    except Exception as e:
        print(f"    ⚠️ Nieoczekiwany błąd: {e}")
        return None, "błąd parsowania"


def create_chart(product_name: str) -> Optional[str]:
    """Tworzy wykres historii cen dla danego produktu (ostatnie 20 wpisów)."""
    if not os.path.exists(DATA_FILE):
        return None
    df = pd.read_csv(DATA_FILE, encoding='utf-8')
    product_data = df[df['product'] == product_name].tail(20)
    if len(product_data) < 2:
        return None

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(product_data['date'], product_data['price'], color='#e07c24',
            marker='o', linewidth=2, label='Cena (PLN)')
    ax.set_title(f"Historia cen: {product_name}", fontsize=11)
    ax.set_ylabel("Cena (PLN)")
    ax.tick_params(axis='x', rotation=35)
    ax.legend()
    fig.tight_layout()

    path = f"chart_foto_{clean_filename(product_name)}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def send_combined_report(changes_list: list):
    """Wysyła jeden email z raportem dla wszystkich produktów, które zmieniły cenę lub dostępność."""
    msg = MIMEMultipart()
    msg['From']    = EMAIL_SENDER
    msg['To']      = ", ".join(EMAIL_RECEIVERS)

    price_changes = [c for c in changes_list if c['type'] == 'price']
    avail_changes = [c for c in changes_list if c['type'] == 'availability']

    parts = []
    if price_changes:
        parts.append(f"💰 {len(price_changes)} zmian cen")
    if avail_changes:
        parts.append(f"📦 {len(avail_changes)} zmian dostępności")
    msg['Subject'] = f"📷 FUJI X: {', '.join(parts)}"

    body = "Wykryto zmiany dla obiektywów Fuji X (fotoforma.pl):\n\n"
    attachments = []

    # --- Zmiany cen ---
    if price_changes:
        body += "═══ ZMIANY CEN ═══════════════════════════════\n"
        for c in price_changes:
            trend    = "📈 WZROST" if c['diff'] > 0 else "📉 SPADEK"
            diff_pct = round(((c['new_price'] - c['old_price']) / c['old_price']) * 100, 2) if c['old_price'] > 0 else 0
            body += (
                f"\n🔹 {c['name']}\n"
                f"   Trend:           {trend} o {c['diff']:+.2f} PLN ({diff_pct:+.2f}%)\n"
                f"   Nowa cena:       {c['new_price']:.2f} PLN\n"
                f"   Poprzednia cena: {c['old_price']:.2f} PLN\n"
                f"   Dostępność:      {avail_label(c['availability'])}\n"
                f"   Link: {c['url']}\n"
            )
            chart = create_chart(c['name'])
            if chart:
                attachments.append(chart)

    # --- Zmiany dostępności ---
    if avail_changes:
        body += "\n═══ ZMIANY DOSTĘPNOŚCI ════════════════════════\n"
        for c in avail_changes:
            body += (
                f"\n🔹 {c['name']}\n"
                f"   Poprzednio: {avail_label(c['old_avail'])}\n"
                f"   Teraz:      {avail_label(c['new_avail'])}\n"
                f"   Cena:       {c['price']:.2f} PLN\n"
                f"   Link: {c['url']}\n"
            )

    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    for chart_path in attachments:
        with open(chart_path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-Disposition', 'attachment',
                           filename=os.path.basename(chart_path))
            msg.attach(img)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
        print("✅ Wysłano raport zbiorczy.")
    except smtplib.SMTPAuthenticationError:
        print("❌ Błąd: Nieprawidłowy email lub hasło Gmail.")
    except Exception as e:
        print(f"❌ Błąd wysyłania emaila: {e}")
    finally:
        for p in attachments:
            if os.path.exists(p):
                os.remove(p)


def send_weekly_summary():
    """Wysyła podsumowanie tygodniowe zmian cen."""
    if not os.path.exists(DATA_FILE):
        print("⚠️ Brak pliku z historią cen.")
        return

    try:
        df = pd.read_csv(DATA_FILE, encoding='utf-8')
    except Exception as e:
        print(f"❌ Błąd czytania CSV: {e}")
        return

    df['date'] = pd.to_datetime(df['date'])
    one_week_ago = datetime.now() - timedelta(days=7)
    recent = df[df['date'] > one_week_ago]

    if recent.empty:
        print("⚠️ Brak danych z ostatnich 7 dni.")
        return

    body = "📊 PODSUMOWANIE TYGODNIOWE – Obiektywy Fuji X\n" + "=" * 50 + "\n\n"
    for product in recent['product'].unique():
        p_data = recent[recent['product'] == product].sort_values('date')
        if len(p_data) >= 2:
            start_p = p_data.iloc[0]['price']
            end_p   = p_data.iloc[-1]['price']
            diff    = round(end_p - start_p, 2)
            pct     = round((diff / start_p) * 100, 2)
            emoji   = "📈" if diff > 0 else ("📉" if diff < 0 else "➡️")
            min_p   = p_data['price'].min()
            max_p   = p_data['price'].max()
            last_av = p_data.iloc[-1]['availability']
            body += (
                f"🔹 {product}:\n"
                f"   7 dni temu: {start_p} PLN  →  Dziś: {end_p} PLN\n"
                f"   Wynik:      {emoji} {diff:+.2f} PLN ({pct:+.2f}%)\n"
                f"   Min/Max:    {min_p} / {max_p} PLN\n"
                f"   Dostępność: {avail_label(last_av)}\n"
                f"   {'─' * 44}\n"
            )

    msg = MIMEMultipart()
    msg['From']    = EMAIL_SENDER
    msg['To']      = ", ".join(EMAIL_RECEIVERS)
    msg['Subject'] = f"📆 FUJI X - PODSUMOWANIE TYGODNIOWE: {datetime.now().strftime('%d.%m.%Y')}"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
        print("📆 Wysłano raport tygodniowy.")
    except Exception as e:
        print(f"❌ Błąd wysyłania raportu tygodniowego: {e}")


def send_monthly_summary():
    """Wysyła podsumowanie miesięczne zmian cen."""
    if not os.path.exists(DATA_FILE):
        print("⚠️ Brak pliku z historią cen.")
        return

    try:
        df = pd.read_csv(DATA_FILE, encoding='utf-8')
    except Exception as e:
        print(f"❌ Błąd czytania CSV: {e}")
        return

    df['date'] = pd.to_datetime(df['date'])
    one_month_ago = datetime.now() - timedelta(days=30)
    recent = df[df['date'] > one_month_ago]

    if recent.empty:
        print("⚠️ Brak danych z ostatnich 30 dni.")
        return

    body = "📊 PODSUMOWANIE MIESIĘCZNE – Obiektywy Fuji X\n" + "=" * 50 + "\n\n"
    for product in recent['product'].unique():
        p_data = recent[recent['product'] == product].sort_values('date')
        if len(p_data) >= 2:
            start_p = p_data.iloc[0]['price']
            end_p   = p_data.iloc[-1]['price']
            diff    = round(end_p - start_p, 2)
            pct     = round((diff / start_p) * 100, 2)
            emoji   = "📈" if diff > 0 else ("📉" if diff < 0 else "➡️")
            last_av = p_data.iloc[-1]['availability']
            body += (
                f"🔹 {product}:\n"
                f"   30 dni temu: {start_p} PLN  →  Dziś: {end_p} PLN\n"
                f"   Wynik:       {emoji} {diff:+.2f} PLN ({pct:+.2f}%)\n"
                f"   Dostępność:  {avail_label(last_av)}\n"
                f"   {'─' * 44}\n"
            )

    msg = MIMEMultipart()
    msg['From']    = EMAIL_SENDER
    msg['To']      = ", ".join(EMAIL_RECEIVERS)
    msg['Subject'] = f"📅 FUJI X - PODSUMOWANIE MIESIĘCZNE: {datetime.now().strftime('%B %Y')}"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
        print("📅 Wysłano raport miesięczny.")
    except Exception as e:
        print(f"❌ Błąd wysyłania raportu miesięcznego: {e}")


def monitor():
    """Główna pętla monitorowania – sprawdza ceny i dostępność, zapisuje historię."""
    if not PRODUCTS:
        print("❌ Brak produktów do monitorowania. Sprawdź sekcję 'products_foto' w config.json!")
        return

    # Inicjuj plik CSV jeśli nie istnieje
    if not os.path.exists(DATA_FILE):
        pd.DataFrame(columns=['date', 'product', 'price', 'availability']).to_csv(
            DATA_FILE, index=False, encoding='utf-8'
        )

    changes_detected = []
    now_dt  = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M")
    print(f"⏰ Sprawdzanie cen obiektywów Fuji X: {now_str}")
    print(f"   Źródło: fotoforma.pl | Produkty: {len(PRODUCTS)}")
    print()

    df = pd.read_csv(DATA_FILE, encoding='utf-8')

    for name, url in PRODUCTS.items():
        print(f"  🔍 {name}")
        price, availability = get_product_info(url)

        if price is None:
            print(f"    ⚠️ Nie udało się pobrać ceny – pomijam.")
            continue

        print(f"    💰 {price:.2f} PLN  |  📦 {avail_label(availability)}")

        # Pobierz ostatni zapis dla tego produktu
        last_entry = df[df['product'] == name].tail(1)

        if not last_entry.empty:
            last_price = float(last_entry['price'].values[0])
            last_avail = str(last_entry['availability'].values[0])

            # Zmiana ceny
            if price != last_price:
                diff = round(price - last_price, 2)
                trend = "📈 WZROST" if diff > 0 else "📉 SPADEK"
                print(f"    🚨 {trend}: {last_price} → {price} PLN ({diff:+.2f})")
                changes_detected.append({
                    'type': 'price', 'name': name, 'url': url,
                    'old_price': last_price, 'new_price': price,
                    'diff': diff, 'availability': availability,
                })
            else:
                print(f"    😴 Cena stabilna ({price} PLN)")

            # Zmiana dostępności
            if availability.lower() != last_avail.lower():
                print(f"    🔔 Zmiana dostępności: '{last_avail}' → '{availability}'")
                changes_detected.append({
                    'type': 'availability', 'name': name, 'url': url,
                    'old_avail': last_avail, 'new_avail': availability,
                    'price': price,
                })
        else:
            print(f"    🆕 Inicjalizacja wpisu.")

        # Dodaj nowy wiersz do historii
        new_row = pd.DataFrame([{
            'date': now_str, 'product': name,
            'price': price, 'availability': availability,
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        print()

    df.to_csv(DATA_FILE, index=False, encoding='utf-8')
    print(f"💾 Zapisano historię do: {DATA_FILE}")

    # Wyślij alert jeśli są zmiany
    if changes_detected:
        n_price = sum(1 for c in changes_detected if c['type'] == 'price')
        n_avail = sum(1 for c in changes_detected if c['type'] == 'availability')
        print(f"\n🚨 Wykryto zmiany: {n_price} cen, {n_avail} dostępności. Wysyłanie emaila...")
        send_combined_report(changes_detected)
    else:
        print("✅ Brak zmian cen ani dostępności. Email nie jest wysyłany.")

    # Raport tygodniowy – każdy poniedziałek o 7:00
    if now_dt.weekday() == 0 and 7 <= now_dt.hour < 8:
        print("\n📆 Generowanie raportu tygodniowego...")
        send_weekly_summary()

    # Raport miesięczny – 1. dzień miesiąca o 7:00
    if now_dt.day == 1 and 7 <= now_dt.hour < 8:
        print("\n📅 Generowanie raportu miesięcznego...")
        send_monthly_summary()


if __name__ == "__main__":
    monitor()
