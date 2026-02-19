# Szukaj Zdjęć GPS

Program szuka zdjęć w określonym folderze (i jego podfolderach) na podstawie współrzędnych GPS zapisanych w metadanych EXIF. Znajduje zdjęcia, które zostały zrobione w określonym promieniu od podanego adresu, a następnie przenosi je do nowo utworzonego folderu "wyszukane XX" wewnątrz katalogu źródłowego.

## Wymagania

Program wymaga zainstalowania następujących bibliotek Python:
- Pillow
- geopy

## Konfiguracja

Parametry programu są wczytywane z pliku JSON: `szukaj_zdjec.json`

Plik musi zawierać następujące pola:
- `folder_zrodlowy`: ścieżka do folderu ze zdjęciami
- `adres`: adres, od którego będą wyszukiwane zdjęcia
- `promien`: promień w kilometrach

Przykład pliku konfiguracyjnego:

```json
{
  "folder_zrodlowy": "C:/Users/truec/Pictures/Camera Roll",
  "adres": "Produkcyjna 110, Białystok",
  "promien": 1.5
}
```

Edytuj `szukaj_zdjec.json` aby zmienić ustawienia bez modyfikowania kodu.

## Użycie

### Jako skrypt Python

Uruchom program poleceniem:
```bash
python szukaj_zdjec.py
```

### Jako plik wykonywalny (exe)

W folderze `dist` znajduje się:
- `szukaj_zdjec.exe` - plik wykonywalny
- `szukaj_zdjec.json` - plik konfiguracyjny

Aby używać programu:
1. Upewnij się, że oba pliki (`szukaj_zdjec.exe` i `szukaj_zdjec.json`) są w tym samym katalogu
2. Edytuj `szukaj_zdjec.json` aby zmienić ustawienia (folder źródłowy, adres, promień)
3. Dwukliknij `szukaj_zdjec.exe` aby uruchomić program

**Uwaga:** Program wymaga bibliotek (Pillow, geopy) zainstalowanych na komputerze, aby działać. Jeśli biblioteki nie są zainstalowane globalnie, możesz rozpowszechniać całą wirtualne środowisko razem z programem, lub użyć opcji PyInstallera do dołączenia wszystkich zależności.

## Jak to działa

1. Program lokalizuje podany adres za pomocą geokodera Nominatim
2. Przeszukuje wszystkie pliki graficzne (.jpg, .jpeg, .png, .heic) w podanym folderze źródłowym i jego podfolderach
3. Wyciąga współrzędne GPS z metadanych EXIF każdego zdjęcia
4. Oblicza odległość między współrzędnymi zdjęcia a celem
5. Przenosi zdjęcia znalezione w podanym promieniu do nowego folderu "wyszukane XX" (gdzie XX to kolejny numer)

## Funkcje

- Obsługa różnych formatów zdjęć: JPG, JPEG, PNG, HEIC
- Rekursywnie przeszukuje podfoldery
- Tworzy unikalne foldery wyjściowe (wyszukane 01, wyszukane 02, itd.)
- Wyświetla postęp i informacje o przeniesionych plikach
- Obsługuje błędy i wyświetla odpowiednie komunikaty</content>
<parameter name="filePath">c:\Users\truec\python_scripts\VS Code\szukaj_zdjec_gps\README.md