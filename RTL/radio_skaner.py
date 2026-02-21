import os
import sys

# --- KROK 1: KONFIGURACJA ŚCIEŻEK (MUSI BYĆ NA POCZĄTKU) ---
# Upewnij się, że ten folder zawiera Twoje pliki .dll i ffmpeg.exe
BASE_DIR = r"c:\Users\truec\python_scripts\VS Code\szukaj_zdjec_gps\RTL"
LIB_DIR = os.path.join(BASE_DIR, "lib")
XML_FILE = os.path.join(BASE_DIR, "SDR-QuickMemory_001.xml")
OUTPUT_DIR = os.path.join(BASE_DIR, "nagrania")

# --- KROK 2: WSKAZANIE BIBLIOTEK SYSTEMOWI ---
if os.path.exists(LIB_DIR):
    # Dodanie do PATH dla ffmpeg i starych wersji Pythona
    os.environ['PATH'] = LIB_DIR + os.pathsep + os.environ['PATH']
    try:
        # Kluczowe dla nowych wersji Pythona na Windows
        os.add_dll_directory(LIB_DIR)
    except AttributeError:
        pass
else:
    print(f"BŁĄD: Nie znaleziono folderu {LIB_DIR}!")

# --- KROK 3: TERAZ DOPIERO IMPORTUJEMY RESZTĘ ---
import numpy as np
import xml.etree.ElementTree as ET
try:
    from rtlsdr import RtlSdr
except ImportError:
    print("BŁĄD: Nie można załadować rtlsdr. Sprawdź czy librtlsdr.dll jest w folderze lib.")
    sys.exit(1)

from pydub import AudioSegment
from scipy.signal import butter, lfilter
import time
import datetime

# Wskazanie konwertera dla pydub
AudioSegment.converter = os.path.join(LIB_DIR, "ffmpeg.exe")

class AdvancedRadioScanner:
    def __init__(self, xml_path):
        print(f"--- Skaner RTL-SDR Blog V4 (Tryb Audio Clean) ---")
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        self.frequencies = self._parse_xml(xml_path)
        try:
            self.sdr = RtlSdr()
        except Exception as e:
            print(f"Błąd hardware: {e}")
            sys.exit(1)

        self.sdr.sample_rate = 2.048e6 
        self.sdr.gain = 45.0 
        
        # Próg RSSI - zmień jeśli nagrywa ciszę
        self.rssi_threshold = -14.0 # dB, im wyższy tym mniej nagrywa, ale może przegapić słabsze sygnały
        self.audio_buffer = []
        self.is_recording = False
        self.current_title = ""
        self.current_freq_mhz = 0.0

    def _parse_xml(self, path):
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            data = []
            for i in range(15):
                for mem in root.findall(f'Memory-{i}'):
                    f = int(mem.get('Frequency', 0))
                    t = mem.get('Title', 'Nieznany')
                    if f > 0: data.append({'freq': f, 'title': t})
            return data
        except Exception as e:
            print(f"Błąd XML: {e}")
            return []

    def butter_bandpass_filter(self, data, lowcut=300, highcut=3000, fs=24000, order=5):
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return lfilter(b, a, data)

    def draw_rssi_bar(self, rssi, title):
        bar_length = 25
        # Skalowanie paska
        level = int((max(min(rssi, -10), -45) + 45) / 35 * bar_length)
        bar = "█" * level + "-" * (bar_length - level)
        status = " [REC]" if self.is_recording else "      "
        sys.stdout.write(f"\r{title[:12]:<12} |{bar}| {rssi:.1f} dB{status}")
        sys.stdout.flush()

    def save_audio(self, buffer, title, freq_mhz):
        if not buffer: return
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        filename = f"{freq_mhz:.3f}MHz_{title}_{timestamp}.mp3".replace(" ", "_")
        full_path = os.path.join(OUTPUT_DIR, filename)
        
        audio_data = np.concatenate(buffer)
        audio_signal = np.diff(np.unwrap(np.angle(audio_data))) 
        
        try:
            # Filtracja pasmowa (tylko głos ludzki)
            audio_signal = self.butter_bandpass_filter(audio_signal, fs=24000)
            
            # Normalizacja
            audio_signal = audio_signal - np.mean(audio_signal)
            max_v = np.max(np.abs(audio_signal))
            if max_v > 0:
                audio_signal = np.int16(audio_signal / max_v * 32767)
            
            segment = AudioSegment(audio_signal.tobytes(), frame_rate=24000, sample_width=2, channels=1)
            segment.export(full_path, format="mp3")
            print(f"\n[ZAPISANO] {filename}")
        except Exception as e:
            print(f"\n[BŁĄD ZAPISU] {e}")

    def start(self):
        print(f"Nasłuchuję {len(self.frequencies)} kanałów. Naciśnij Ctrl+C aby przerwać.")
        try:
            while True:
                for entry in self.frequencies:
                    f, t = entry['freq'], entry['title']
                    self.sdr.center_freq = f
                    time.sleep(0.08)
                    
                    samples = self.sdr.read_samples(131072)
                    rssi = 10 * np.log10(np.mean(np.abs(samples)**2) + 1e-12)
                    
                    self.draw_rssi_bar(rssi, t)
                    
                    if rssi > self.rssi_threshold:
                        self.audio_buffer.append(samples)
                        self.is_recording = True
                        self.current_title = t
                        self.current_freq_mhz = f / 1e6
                    else:
                        if self.is_recording:
                            self.save_audio(self.audio_buffer, self.current_title, self.current_freq_mhz)
                            self.audio_buffer, self.is_recording = [], False
                            
        except KeyboardInterrupt:
            print("\nZamykanie...")
            self.sdr.close()

if __name__ == "__main__":
    scanner = AdvancedRadioScanner(XML_FILE)
    scanner.start()