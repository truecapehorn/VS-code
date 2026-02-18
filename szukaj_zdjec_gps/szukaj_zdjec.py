'''
Program szuka zdjęć w określonym folderze (i jego podfolderach) na podstawie współrzędnych
GPS zapisanych w metadanych EXIF.
Znajduje zdjęcia, które zostały zrobione w określonym promieniu od podanego adresu, 
a następnie przenosi je do nowo utworzonego folderu "wyszukane XX" wewnątrz katalogu 
źródłowego. 

Wymaga zainstalowania bibliotek: Pillow, geopy

Konfiguracja:
- Parametry programu są wczytywane z pliku JSON: szukaj_zdjec.json
- Plik musi zawierać: folder_zrodlowy, adres, promien
- Edytuj szukaj_zdjec.json aby zmienić ustawienia bez modyfikowania kodu

{
  "folder_zrodlowy": "C:/Users/truec/Pictures/Camera Roll",
  "adres": "Produkcyjna 110, Białystok",
  "promien": 1.5
}

'''


import os
import json
import shutil
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

def get_gps_coords(image_path):
    """Wyciąga współrzędne GPS z metadanych zdjęcia."""
    try:
        img = Image.open(image_path)
        exif_data = img._getexif()
        if not exif_data:
            return None

        gps_info = {}
        for tag, value in exif_data.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_info[sub_decoded] = value[t]

        if not gps_info:
            return None

        def convert_to_degrees(value):
            d = float(value[0])
            m = float(value[1])
            s = float(value[2])
            return d + (m / 60.0) + (s / 3600.0)

        lat = convert_to_degrees(gps_info['GPSLatitude'])
        if gps_info['GPSLatitudeRef'] != 'N':
            lat = -lat

        lon = convert_to_degrees(gps_info['GPSLongitude'])
        if gps_info['GPSLongitudeRef'] != 'E':
            lon = -lon

        return lat, lon
    except Exception:
        return None

def find_and_move_photos(source_dir, address, radius_km):
    # 1. Lokalizacja adresu
    geolocator = Nominatim(user_agent="photo_mover_geo")
    location = geolocator.geocode(address)
    
    if not location:
        print(f"BŁĄD: Nie odnaleziono adresu: {address}")
        return

    target_coords = (location.latitude, location.longitude)
    source_path = Path(source_dir)

    # 2. Przygotowanie folderu docelowego wewnątrz katalogu źródłowego
    counter = 1
    while True:
        target_folder = source_path / f"wyszukane {counter:02d}"
        if not target_folder.exists():
            break
        counter += 1
    
    # 3. Przeszukiwanie i przenoszenie
    print(f"Szukanie zdjęć w promieniu {radius_km}km od: {location.address}")
    
    found_files = []
    extensions = ('.jpg', '.jpeg', '.png', '.heic')
    
    # Najpierw zbieramy listę, żeby nie przeszukiwać folderu, do którego przenosimy
    for file_path in source_path.rglob('*'):
        # Pomijamy pliki, które już są w folderach "wyszukane"
        if "wyszukane" in file_path.parts:
            continue
            
        if file_path.suffix.lower() in extensions:
            coords = get_gps_coords(file_path)
            if coords:
                distance = geodesic(target_coords, coords).km
                if distance <= radius_km:
                    found_files.append((file_path, distance))

    if found_files:
        target_folder.mkdir(parents=True, exist_ok=True)
        print(f"Tworzę folder: {target_folder.name}")
        
        for file_path, dist in found_files:
            try:
                # Przenoszenie pliku
                shutil.move(str(file_path), str(target_folder / file_path.name))
                print(f"Przeniesiono [{dist:.2f} km]: {file_path.name}")
            except Exception as e:
                print(f"Błąd przy przenoszeniu {file_path.name}: {e}")
        
        print("-" * 30)
        print(f"Sukces! Przeniesiono {len(found_files)} zdjęć do {target_folder}")
    else:
        print("Nie znaleziono żadnych zdjęć spełniających kryteria.")

# --- KONFIGURACJA ---
def load_config(config_file="szukaj_zdjec.json"):
    """Wczytuje konfigurację z pliku JSON."""
    # Obsługa PyInstallera - szukaj w tym samym katalogu co exe
    if getattr(os.sys, 'frozen', False):
        # Program jest uruchomiony jako exe
        script_dir = os.path.dirname(os.sys.executable)
    else:
        # Program jest uruchomiony jako skrypt Python
        script_dir = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(script_dir, config_file)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"BŁĄD: Nie znaleziono pliku konfiguracyjnego: {config_path}")
        return None
    except json.JSONDecodeError:
        print(f"BŁĄD: Plik {config_path} nie jest poprawnym JSON.")
        return None

if __name__ == "__main__":
    config = load_config()
    if config:
        find_and_move_photos(
            config.get("folder_zrodlowy"),
            config.get("adres"),
            config.get("promien")
        )