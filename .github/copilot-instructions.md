# Instrukcje dla GitHub Copilot — VS Code Python Scripts

## Commitowanie zmian

Po każdej modyfikacji pliku w tym projekcie wykonaj commit do gita:

```bash
git add .
git commit -m "<krótki opis zmian w języku polskim>"
```

Opis commita powinien być zwięzły (max 72 znaki) i opisywać co zostało zmienione, np.:
- `monitor_cen_foto: dodaj obsługę nowych obiektywów`
- `config: zmiana odbiorców email dla foto i inwest`
- `monitor_cen: poprawka parsowania ceny`

Nie rób `git push` automatycznie — tylko `git add` + `git commit`.
