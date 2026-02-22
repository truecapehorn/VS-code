# 📷 Monitor cen obiektywów Fuji X — `monitor_cen_foto.py`

Program monitoruje ceny i dostępność obiektywów systemu **Fuji X** (aparat XT-30 II)
na stronie [fotoforma.pl](https://fotoforma.pl). Przy każdym uruchomieniu pobiera aktualne
dane, zapisuje historię i wysyła email jeśli coś się zmieniło.

---

## Wymagania

- Python 3.9+
- Zainstalowane biblioteki:

```bash
pip install requests beautifulsoup4 pandas matplotlib
```

---

## Konfiguracja (`config.json`)

Program czyta konfigurację z pliku `config.json` w tym samym folderze.
Wymagane klucze:

```json
{
  "email_sender": "twoj_email@gmail.com",
  "email_password": "haslo_aplikacji_gmail",
  "email_receivers_foto": [
    "odbiorca1@gmail.com",
    "odbiorca2@o2.pl"
  ],
  "products_foto": {
    "Fujifilm XF 70-300mm F4-5.6 R LM OIS WR": "https://fotoforma.pl/obiektyw-fujifilm-fujinon-xf-70-300mm-f4-5.6-r-lm-ois-wr",
    "Fujifilm XF 55-200mm f/3.5-4.8 R LM OIS": "https://fotoforma.pl/obiektyw-fujifilm-fujinon-xf-55-200-mm-f-3-5-4-8-r-lm-ois.html",
    "Fujifilm XF 16-55mm f/2.8 R LM WR II": "https://fotoforma.pl/obiektyw-fujifilm-xf-16-55mm-f-2.8-r-lm-wr-ii"
  }
}
```

> **Hasło Gmail** — użyj [hasła do aplikacji](https://myaccount.google.com/apppasswords),
> nie zwykłego hasła do konta (wymaga włączonej weryfikacji dwuetapowej).

> **Uwaga:** Klucz `email_receivers_foto` jest dedykowany tylko dla tego programu.
> Możesz tu wpisać innych odbiorców niż dla monitora metali szlachetnych (`email_receivers_inwest`).

### Dodawanie nowych obiektywów

W sekcji `products_foto` dodaj nowy wpis w formacie:

```json
"Nazwa wyświetlana": "https://fotoforma.pl/adres-strony-produktu"
```

---

## Uruchamianie

### Ręcznie

```bash
python3 monitor_cen_foto.py
```

### Na Raspberry Pi — cron (codziennie o 10:00)

```bash
crontab -e
```

Dodaj linię:

```
0 10 * * * /usr/bin/python3 /home/pi/python_scripts/monitor_cen_foto.py >> /home/pi/python_scripts/foto.log 2>&1
```

### Kopiowanie plików na Raspberry Pi (z Windows)

```bash
scp monitor_cen_foto.py config.json pi@192.168.1.101:/home/pi/python_scripts/
```

---

## Co program robi przy każdym uruchomieniu

```
1. Wczytuje konfigurację z config.json
2. Dla każdego obiektywu z listy products_foto:
   - Pobiera aktualną cenę z fotoforma.pl
   - Pobiera status dostępności
   - Porównuje z ostatnim zapisem w historii
3. Zapisuje nowe dane do price_history_foto.csv
4. Jeśli wykryto zmiany → wysyła email z raportem
5. W poniedziałek o 10:00 → wysyła raport tygodniowy
6. 1. dnia miesiąca o 10:00 → wysyła raport miesięczny
```

---

## Wysyłane emaile

### 🚨 Alert zmiany ceny

Wysyłany natychmiast gdy cena produktu ulegnie zmianie. Zawiera:
- Kierunek zmiany (📈 wzrost / 📉 spadek) z wartością w PLN i procentach
- Nową i poprzednią cenę
- Aktualny status dostępności
- Wykres trendu cen (załącznik PNG, ostatnie 20 pomiarów)

### 🔔 Alert zmiany dostępności

Wysyłany gdy zmieni się status dostępności (np. obiektyw wraca na stan).
Zawiera poprzedni i nowy status oraz aktualną cenę.

### 📆 Raport tygodniowy

Wysyłany automatycznie w **każdy poniedziałek o 10:00**. Zawiera dla każdego obiektywu:
- Cenę sprzed 7 dni vs cena aktualna
- Zmianę w PLN i procentach
- Min/Max cena w ciągu tygodnia
- Aktualny status dostępności

### 📅 Raport miesięczny

Wysyłany automatycznie **1. dnia każdego miesiąca o 10:00**. Zawiera:
- Cenę sprzed 30 dni vs cena aktualna
- Zmianę w PLN i procentach
- Aktualny status dostępności

---

## Statusy dostępności

| Status na stronie    | Wyświetlany jako         |
|----------------------|--------------------------|
| dostępny             | ✅ dostępny              |
| magazyn dostawcy     | 📦 magazyn dostawcy      |
| na wyczerpaniu       | ⚠️ na wyczerpaniu        |
| niedostępny          | ❌ niedostępny           |
| na zamówienie        | 🕐 na zamówienie         |

---

## Pliki programu

| Plik                      | Opis                                      |
|---------------------------|-------------------------------------------|
| `monitor_cen_foto.py`     | Główny program                            |
| `config.json`             | Konfiguracja (email, lista obiektywów)    |
| `price_history_foto.csv`  | Historia cen (tworzona automatycznie)     |
| `foto.log`                | Logi z uruchomień crona (na Raspberry Pi) |

### Format pliku `price_history_foto.csv`

```
date,product,price,availability
2026-02-22 10:00,Fujifilm XF 70-300mm F4-5.6 R LM OIS WR,3899.0,dostępny
2026-02-22 10:00,Fujifilm XF 55-200mm f/3.5-4.8 R LM OIS,2899.0,magazyn dostawcy
```

---

## Rozwiązywanie problemów

**Program nie wysyła emaila mimo zmian**
→ Sprawdź hasło aplikacji Gmail w `config.json` i czy 2FA jest włączone na koncie.

**`❌ Błąd: Plik config.json nie istnieje`**
→ Uruchom program z folderu `monitor_cen/` lub upewnij się, że `config.json` jest w tym samym miejscu co skrypt.

**`⚠️ Nie udało się pobrać ceny`**
→ Sprawdź połączenie z internetem lub czy URL produktu w `config.json` jest poprawny.

**Podgląd logów na Raspberry Pi**
```bash
tail -f /home/pi/python_scripts/foto.log
```
