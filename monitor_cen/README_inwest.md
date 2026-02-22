# Monitor Cen Metali Szlachetnych - Tavex.pl

## 📋 Opis Programu

**monitor_cen.py** to automatyczny system monitorowania cen metali szlachetnych (złota, srebra) na portalu [Tavex.pl](https://tavex.pl). Program regularnie pobiera ceny, wykrywa zmiany i wysyła powiadomienia e-mail z alert zawierającymi:

- Wykrycie zmian cen w porównaniu do ostatniego pomiaru
- Grafikę spadków/wzrostów cen
- Tygodniowe i miesięczne raporty podsumowujące trendy
- Informacje o spreadzie (różnicy między ceną sprzedaży a skupu)

## 🎯 Główne Funkcjonalności

- ✅ **Automatyczne pobieranie cen** z witryny Tavex.pl
- ✅ **Alerty emailowe** przy zmianach cen (sprzedaż/skup)
- ✅ **Wykresy trendów** dołączane do emailów
- ✅ **Raport tygodniowy** (każdy poniedziałek o 7:00)
- ✅ **Raport miesięczny** (1. dzień miesiąca o 7:00)
- ✅ **Historia danych** zapisywana w CSV
- ✅ **CLI do analizy danych** (cli_price_tool.py)

## 📦 Wymagania Systemowe

- Python 3.7+
- Biblioteki: `requests`, `beautifulsoup4`, `pandas`, `matplotlib`
- Konto Gmail z włączonym dostępem dla "aplikacji mniej bezpiecznych" lub hasłem aplikacji
- Dostęp do internetu

### Instalacja Bibliotek

```bash
pip install requests beautifulsoup4 pandas matplotlib
```

## ⚙️ Konfiguracja

### 1. Plik `config.json`

Program wymaga pliku konfiguracyjnego `config.json` w tym samym katalogu:

```json
{
  "email_sender": "twoj_email@gmail.com",
  "email_password": "twoje_haslo_aplikacji_gmail",
  "email_receivers_inwest": [
    "odbiorca1@example.com",
    "odbiorca2@example.com"
  ],
  "products_inwest": {
    "Złoty Dukat Austriacki 3,44 g": "https://tavex.pl/zloto/austriacki-zloty-dukat/",
    "Srebrna moneta Kanadyjski Liść Klonu 1 oz": "https://tavex.pl/srebro/srebrny-kanadyjski-lisc-klonu-1-oz/"
  }
}
```

**Pola wymagane:**

| Pole | Opis |
|------|------|
| `email_sender` | Email nadawcy (konto Gmail) |
| `email_password` | Hasło aplikacji Gmail |
| `email_receivers_inwest` | Lista emaili odbiorców alertów dla metali szlachetnych |
| `products_inwest` | Słownik: `"Nazwa produktu": "URL do produktu na Tavex.pl"` |

> **Uwaga:** Klucz `email_receivers_inwest` jest dedykowany tylko dla tego programu.
> Możesz tu wpisać innych odbiorców niż dla monitora obiektywów (`email_receivers_foto`).

### 2. Ustawienie Hasła Aplikacji Gmail

1. Włącz **2-Step Verification** na koncie Google
2. Przejdź do [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Utwórz hasło aplikacji dla "Mail" i urządzenia "Windows, Mac, Linux"
4. Skopiuj wygenerowane hasło do `email_password` w `config.json`

## 🚀 Użycie

### Uruchomienie Jednorazowe

```bash
python monitor_cen.py
```

Program automatycznie:
- Pobierze ceny dla wszystkich produktów z `config.json`
- Porówna z ostatnim pomiarem (jeśli istnieje)
- Wyśle email z alertem jeśli cena się zmieniła
- Zapisze dane do `price_history_spread.csv`

### Planowanie Automatyczne (Cron)

Aby program uruchamiał się automatycznie:

#### Linux / macOS:

```bash
crontab -e
```

Dodaj linię (sprawdzanie co 30 minut):

```cron
*/30 * * * * cd /ścieżka/do/monitor_cen && python monitor_cen.py
```

Sprawdzanie co godzinę:

```cron
0 * * * * cd /ścieżka/do/monitor_cen && python monitor_cen.py
```

#### Windows (Task Scheduler):

1. Otwórz **Task Scheduler**
2. Utwórz nowe zadanie
3. Akcja: `C:\path\to\python.exe monitor_cen.py`
4. Katalog roboczy: `C:\path\to\monitor_cen\`
5. Ustaw wyzwalacz (np. co 30 minut)

#### Raspberry Pi:

```bash
scp monitor_cen.py config.json pi@192.168.1.101:/home/pi/python_scripts/
ssh pi@192.168.1.101
crontab -e
```

## 📊 CLI Tool - Analiza Danych

Plik `cli_price_tool.py` umożliwia przeglądanie i analizę historii cen.

### Dostępne Komendy

#### 1. Wyświetl Wszystkie Produkty (Ostatnie Ceny):

```bash
python cli_price_tool.py list
```

**Wyjście:**
```
- Złoty Dukat Austriacki 3,44 g: sell=400.50 PLN, buy=390.25 PLN, spread=10.25 PLN
- Srebrna moneta Kanadyjski Liść Klonu 1 oz: sell=85.20 PLN, buy=82.10 PLN, spread=3.10 PLN
```

#### 2. Pokaż Historię Produktu:

```bash
python cli_price_tool.py show "Złoty Dukat Austriacki 3,44 g"
```

**Wyjście:**
```
Historia dla: Złoty Dukat Austriacki 3,44 g (5 wpisów)

2024-02-15 09:00  sell=398.50	buy=388.25	spread=10.25
2024-02-15 14:30  sell=400.50	buy=390.25	spread=10.25
```

#### 3. Utwórz Wykres Trendu:

```bash
python cli_price_tool.py plot "Złoty Dukat Austriacki 3,44 g"
```

Możliwe opcje:

```bash
# Ostatnie 30 dni
python cli_price_tool.py plot "Nazwa produktu" --last 30

# Zapisz do konkretnego pliku
python cli_price_tool.py plot "Nazwa produktu" --out moj_wykres.png

# Kombinacja
python cli_price_tool.py plot "Nazwa produktu" --last 15 --out trend15dni.png
```

## 📈 Struktura Plików Danych

### price_history_spread.csv

Program automatycznie tworzy plik CSV z historią cen:

```csv
date,product,sell_price,buy_price,spread_pln
2024-02-15 09:00,Złoty Dukat Austriacki 3,44 g,400.50,390.25,10.25
2024-02-15 14:30,Złoty Dukat Austriacki 3,44 g,401.00,390.75,10.25
```

**Kolumny:**
- `date` - Data i godzina pomiaru
- `product` - Nazwa produktu
- `sell_price` - Cena sprzedaży (PLN)
- `buy_price` - Cena skupu (PLN)
- `spread_pln` - Różnica między ceną sprzedaży a skupu

## 📧 Format Emaili

### Alert o Zmianie Ceny

**Przedmiot:** `📊 RAPORT ZMIAN CEN (X produktów)`

**Zawartość:**
```
Wykryto zmiany cen dla Twoich produktów:

--- ALERT CENOWY: Złoty Dukat Austriacki 3,44 g ---
Trend: 📈 WZROST o 2.50 PLN (0.63%)
🛒 Cena zakupu: 401.00 PLN
💰 Cena skupu: 390.75 PLN
⚖️ Spread: 10.25 PLN (2.56%)
Poprzednia cena: 398.50 PLN
```

Do maila dołączony jest wykres ostatnich 15 pomiarów.

### Raport Tygodniowy

**Wysyłany:** Poniedziałek o 7:00

**Przedmiot:** `📆 PODSUMOWANIE TYGODNIOWE: DD.MM.YYYY`

### Raport Miesięczny

**Wysyłany:** 1. dzień miesiąca o 7:00

**Przedmiot:** `📅 PODSUMOWANIE MIESIĘCZNE: MMMM YYYY`

## 🐛 Rozwiązywanie Problemów

### ❌ "Błąd: Plik config.json nie istnieje"

**Rozwiązanie:** Utwórz plik `config.json` w tym samym katalogu co `monitor_cen.py` z wymaganymi polami.

### ❌ "Błąd: Nieprawidłowy email lub hasło Gmail"

**Przyczyny:**
- Zły email lub hasło aplikacji
- Brak dostępu do aplikacji mniej bezpiecznych na subie Google
- **Rozwiązanie:** Generuj hasło aplikacji wg instrukcji w sekcji "Konfiguracja"

### ❌ "Problem z ceną dla: [Produkt]"

**Przyczyny:**
- URL produktu w config.json jest nieaktualny/nieprawidłowy
- Struktura HTML na Tavex.pl się zmieniła
- Brak połączenia internetowego

**Sprawdź:**
```bash
curl -I "https://tavex.pl/zloto/austriacki-zloty-dukat/"
```

### ⚠️ "Brak danych z ostatnich 7/30 dni - raport nie zostanie wysłany"

**Przyczyna:** Program nie miał wystarczająco pomiarów

**Rozwiązanie:** Uruchamiaj program regularnie przez kilka dni, aby zebrać dane do raportów.

### 📊 Program nie wysyła emaila despite zmian ceny

**Sprawdź:**
1. Czy email_sender i email_password są poprawne w config.json
2. Czy `email_receivers_inwest` jest niepusty
3. Czy istnieje połączenie internetowe
4. Sprawdź logi (dodaj `print()` w kodzie lub sprawdź output programu)

## 🔄 Integracja z Systemem

### Logowanie wyników

Aby zapisywać wyniki do pliku log:

```bash
python monitor_cen.py >> monitor.log 2>&1
```

### Wysyłanie powiadomień systemowych (Linux)

Możesz zintegrować z powiadomieniami systemowymi:

```bash
python monitor_cen.py && notify-send "Monitor Cen" "Sprawdzanie cen zakończone"
```

## 📝 Najczęściaj Pytania

**P: Czy mogę monitorować produkty spoza Tavex.pl?**

O: Nie, program jest dostosowany do struktury HTML Tavex.pl. Zmiana innego źródła wymagałaby modyfikacji funkcji `get_prices()`.

**P: Jak zmienić częstotliwość sprawdzania?**

O: Edytuj wpis cron'a w systemie. Na Raspberry Pi: `crontab -e`

**P: Czy mogę dodać/usunąć produkty bez restartu?**

O: Nie trzeba restartować - wystarczy edytować `config.json` i uruchomić program ponownie.

**P: Czy program zużywa wiele zasobów?**

O: Nie, program jest lekki i szybki. Każdy pomiar trwa ok. 2-3 sekund.

## 📄 Licencja i Autoautora

Program został utworzony do śledzenia cen metali szlachetnych na portalu Tavex.pl.

## 🔗 Źródła

- [Tavex.pl](https://tavex.pl) - Strona monitorowana
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) - Web scraping
- [Pandas](https://pandas.pydata.org/) - Analiza danych
- [Matplotlib](https://matplotlib.org/) - Wykresy
