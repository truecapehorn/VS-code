import os
import sys

# --- KONFIGURACJA ŚCIEŻEK ---
BASE_DIR = r"c:\Users\truec\python_scripts\VS Code\RTL"
LIB_DIR = os.path.join(BASE_DIR, "lib")
XML_FILE = os.path.join(BASE_DIR, "SDR-QuickMemory_001.xml")
OUTPUT_DIR = os.path.join(BASE_DIR, "nagrania")

# --- DYNAMICZNE ŁADOWANIE BIBLIOTEK Z FOLDERU LIB ---
if os.path.exists(LIB_DIR):
    # Dodajemy lib do PATH, aby system widział ffmpeg.exe i DLL
    os.environ['PATH'] = LIB_DIR + os.pathsep + os.environ['PATH']
    try:
        # Specjalna metoda dla Pythona 3.8+ na Windows (dla plików .dll)
        os.add_dll_directory(LIB_DIR)
    except AttributeError:
        pass
else:
    print(f"OSTRZEŻENIE: Folder {LIB_DIR} nie istnieje!")

import numpy as np
import xml.etree.ElementTree as ET
from rtlsdr import RtlSdr
from pydub import AudioSegment
import time
import datetime

# Informujemy pydub, gdzie dokładnie szukać ffmpeg
AudioSegment.converter = os.path.join(LIB_DIR, "ffmpeg.exe")

class RadioScannerV4:
    def __init__(self, xml_path):
        print(f"Inicjalizacja hardware'u (Szukam bibliotek w: {LIB_DIR})...")
        
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        self.frequencies = self._parse_xml(xml_path)
        try:
            self.sdr = RtlSdr()
        except Exception as e:
            print(f"Błąd: Nie znaleziono RTL-SDR lub brakuje librtlsdr.dll w {LIB_DIR}!")
            print(f"Szczegóły: {e}")
            sys.exit(1)
            
        self.sdr.sample_rate = 2.048e6 
        self.sdr.gain = 40.0
        
        self.rssi_threshold = -20.0 
        self.audio_buffer = []
        self.is_recording = False
        self.current_title = ""
        self.current_freq_mhz = 0.0

    def _parse_xml(self, path):
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            data = []
            for i in range(15): # Sprawdzamy więcej grup Memory
                for mem in root.findall(f'Memory-{i}'):
                    f = int(mem.get('Frequency', 0))
                    t = mem.get('Title', 'Nieznany')
                    if f > 0:
                        data.append({'freq': f, 'title': t})
            return data
        except Exception as e:
            print(f"Błąd czytania pliku XML: {e}")
            return []

    def get_rssi(self, samples):
        pwr = np.mean(np.abs(samples)**2)
        return 10 * np.log10(pwr + 1e-12)

    def save_audio(self, buffer, title, freq_mhz):
        if not buffer: return
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{freq_mhz:.3f}MHz_{title}_{timestamp}.mp3".replace(" ", "_")
        full_path = os.path.join(OUTPUT_DIR, filename)
        
        audio_data = np.concatenate(buffer)
        audio_signal = np.diff(np.unwrap(np.angle(audio_data))) 
        
        if len(audio_signal) == 0: return
        audio_signal = audio_signal - np.mean(audio_signal)
        max_val = np.max(np.abs(audio_signal))
        if max_val > 0:
            audio_signal = np.int16(audio_signal / max_val * 32767)
        
        try:
            segment = AudioSegment(audio_signal.tobytes(), frame_rate=24000, sample_width=2, channels=1)
            segment.export(full_path, format="mp3")
            print(f"!!! ZAPISANO: {filename}")
        except Exception as e:
            print(f"Błąd zapisu MP3 (sprawdź czy ffmpeg.exe jest w lib/): {e}")

    def start_scanning(self):
        print(f"Skanuję {len(self.frequencies)} kanałów. Nagrania w: /nagrania")
        
        try:
            while True:
                for entry in self.frequencies:
                    f = entry['freq']
                    t = entry['title']
                    
                    self.sdr.center_freq = f
                    time.sleep(0.08) 
                    
                    samples = self.sdr.read_samples(131072)
                    rssi = self.get_rssi(samples)
                    
                    if rssi > self.rssi_threshold:
                        print(f"[*] GŁOS: {t} | RSSI: {rssi:.1f} dB")
                        self.audio_buffer.append(samples)
                        self.is_recording = True
                        self.current_title = t
                        self.current_freq_mhz = f / 1e6
                    else:
                        if self.is_recording:
                            self.save_audio(self.audio_buffer, self.current_title, self.current_freq_mhz)
                            self.audio_buffer = []
                            self.is_recording = False
                            
        except KeyboardInterrupt:
            print("\nZatrzymano.")
        finally:
            self.sdr.close()

if __name__ == "__main__":
    scanner = RadioScannerV4(XML_FILE)
    scanner.start_scanning()