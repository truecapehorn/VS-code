import yfinance as yf

# Złoto (Gold Futures)
gold = yf.Ticker("GC=F")
print(f"Cena złota: {gold.history(period='1d')['Close'].iloc[-1]}")

# Srebro (Silver Futures)
silver = yf.Ticker("SI=F")
print(f"Cena srebra: {silver.history(period='1d')['Close'].iloc[-1]}")

cena_usd_oz = gold.history(period='1d')['Close'].iloc[-1]
kurs_usd_pln = yf.Ticker("PLN=X").history(period='1d')['Close'].iloc[-1]

cena_pln_gram = (cena_usd_oz * kurs_usd_pln) / 31.1035

print(f"Cena złota w PLN za gram: {cena_pln_gram:.2f}")
print(f"Cena srebra w PLN za gram: {(silver.history(period='1d')['Close'].iloc[-1] * kurs_usd_pln) / 31.1035:.2f}")

# AKTUALNE CENY METALI SZLACHETNYCH
# =================================
# 📈 Złoto: 285.50 PLN/g (zmiana: +2.50 / +0.88%)
# 📉 Srebro: 42.30 PLN/g (zmiana: -0.70 / -1.63%)