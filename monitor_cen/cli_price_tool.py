#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prosty CLI do przeglądu historii cen i tworzenia wykresów.
Użycie:
  python cli_price_tool.py list
  python cli_price_tool.py show "Złoty Dukat Austriacki 3,44 g"
  python cli_price_tool.py plot "Złoty Dukat Austriacki 3,44 g" --last 30 --out chart.png
"""
import argparse
import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

DATA_FILE = Path("price_history_spread.csv")

def load_df():
    if not DATA_FILE.exists():
        print("Brak pliku:", DATA_FILE)
        sys.exit(1)
    df = pd.read_csv(DATA_FILE, encoding='utf-8', parse_dates=['date'])
    return df

def cmd_list(args):
    df = load_df()
    latest = df.sort_values('date').groupby('product').tail(1)
    latest = latest.sort_values('product')
    for _, r in latest.iterrows():
        print(f"- {r['product']}: sell={r['sell_price']} PLN, buy={r['buy_price']} PLN, spread={r['spread_pln']} PLN")

def cmd_show(args):
    df = load_df()
    prod = args.product
    p_df = df[df['product'] == prod].sort_values('date')
    if p_df.empty:
        print("Nie znaleziono produktu:", prod)
        return
    print(f"Historia dla: {prod} ({len(p_df)} wpisów)\n")
    for _, r in p_df.iterrows():
        print(f"{r['date']}  sell={r['sell_price']}\tbuy={r['buy_price']}\tspread={r['spread_pln']}")

def sanitize_fname(s):
    return ''.join(c for c in s if c.isalnum() or c in ' _-').strip().replace(' ', '_')[:120]

def cmd_plot(args):
    df = load_df()
    prod = args.product
    p_df = df[df['product'] == prod].sort_values('date')
    if p_df.empty:
        print("Nie znaleziono produktu:", prod)
        return
    last_n = args.last
    if last_n:
        p_df = p_df.tail(last_n)
    plt.figure(figsize=(10,4))
    plt.plot(p_df['date'], p_df['sell_price'], marker='o', label='sprzedaż')
    plt.plot(p_df['date'], p_df['buy_price'], marker='o', linestyle='--', label='skup')
    plt.title(prod)
    plt.xlabel('data')
    plt.ylabel('PLN')
    plt.legend()
    plt.xticks(rotation=35, ha='right')
    plt.tight_layout()
    out = args.out or f"chart_{sanitize_fname(prod)}.png"
    plt.savefig(out)
    plt.close()
    print("Zapisano wykres:", out)

def main():
    parser = argparse.ArgumentParser(description="CLI do historii cen")
    sub = parser.add_subparsers(dest='cmd')

    p_list = sub.add_parser('list', help='lista produktów i ostatnie ceny')
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser('show', help='pokaż historię produktu')
    p_show.add_argument('product', help='nazwa produktu (dokładnie)')
    p_show.set_defaults(func=cmd_show)

    p_plot = sub.add_parser('plot', help='zapisz wykres trendu produktu')
    p_plot.add_argument('product', help='nazwa produktu (dokładnie)')
    p_plot.add_argument('--last', type=int, default=None, help='ostatnie N wpisów')
    p_plot.add_argument('--out', default=None, help='plik wyjściowy (png)')
    p_plot.set_defaults(func=cmd_plot)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return
    args.func(args)

if __name__ == "__main__":
    main()
