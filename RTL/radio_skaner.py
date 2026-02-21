import os
import sys
import numpy as np
import xml.etree.ElementTree as ET
import time
import datetime
import shutil

# --- KONFIGURACJA ---
BASE_DIR = r"c:\Users\truec\python_scripts\VS Code\RTL"
LIB_DIR = os.path.join(BASE_DIR, "lib")
XML_FILE = os.path.join(BASE_DIR, "SDR-QuickMemory_001.xml")
BASE_OUTPUT_DIR = os.path.join(BASE_DIR, "nagrania")

# --- ŁADOWANIE BIBLIOTEK ---
if os.path.exists(LIB_DIR):
    os.environ['PATH'] = LIB_DIR + os.pathsep + os.environ['PATH']
    if sys.platform == 'win32':
        try: os.add_dll_directory(LIB_DIR)
        except AttributeError: pass

# Importy po ustawieniu PATH
from pydub import AudioSegment
from scipy.signal import butter, lfilter

# Wymuszenie ścieżki do FFmpeg (rozwiązuje błąd RuntimeWarning)
FFMPEG_EXE = os.path.join(LIB_DIR, "ffmpeg.exe")
AudioSegment.converter = FFMPEG_EXE
AudioSegment.ffprobe = os.path.join(LIB_DIR, "ffprobe.exe")

try:
    from rtlsdr import RtlSdr
except ImportError:
    print("BŁĄD: Nie znaleziono biblioteki rtlsdr!")
    sys.exit(1)

class ProfessionalRadioScanner:
    def __init__(self, xml_path):
        print(f"--- Inteligentny Skaner V4 | Lokalizacja: {BASE_DIR} ---")
        self.frequencies = self._parse_xml(xml_path)
        self.sdr = RtlSdr()
        self.sdr.sample_rate = 2.048e6 # Zwiększony do 2.048 MHz dla lepszej jakości audio
        self.sdr.gain = 45.0 # Maksymalny gain (możesz dostosować, jeśli masz szum)
        
        # --- KALIBRACJA (Zmienione, by nie łapać szumu -35dB) ---
        self.rssi_threshold = -20.0  # Było -25, teraz jest znacznie wyżej (bezpieczniej)
        self.hang_time_limit = 1.0   # Skróciłam nieco czas oczekiwania
        self.hang_time_counter = 0   # Licznik czasu zawieszenia
        
        self.audio_buffer = []
        self.is_recording = False
        self.current_title = ""
        self.current_freq_mhz = 0.0
        self.clear_recordings()

    def clear_recordings(self):
        if os.path.exists(BASE_OUTPUT_DIR):
            shutil.rmtree(BASE_OUTPUT_DIR)
            os.makedirs(BASE_OUTPUT_DIR)
            print("Wyczyszczono poprzednie nagrania.")

    def get_daily_folder(self):
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(BASE_OUTPUT_DIR, today)
        if not os.path.exists(path): os.makedirs(path)
        return path

    def _parse_xml(self, path):
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            data = []
            for i in range(10):
                for mem in root.findall(f'Memory-{i}'):
                    f = int(mem.get('Frequency', 0))
                    t = mem.get('Title', 'Nieznany')
                    if f > 0: data.append({'freq': f, 'title': t})
            return data
        except Exception: return []

    def butter_bandpass_filter(self, data, lowcut=300, highcut=3000, fs=24000, order=5):
        nyq = 0.5 * fs
        low, high = lowcut / nyq, highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return lfilter(b, a, data)


    def save_file(self):
        if not self.audio_buffer: return
        t_str = datetime.datetime.now().strftime("%H%M%S")
        daily_path = self.get_daily_folder()
        fname = f"{self.current_freq_mhz:.3f}MHz_{self.current_title}_{t_str}.mp3".replace(" ", "_")
        full_path = os.path.join(daily_path, fname)
        
        try:
            samples = np.concatenate(self.audio_buffer)
            audio = np.diff(np.unwrap(np.angle(samples))) 
            audio = self.butter_bandpass_filter(audio, fs=24000)
            audio = (audio / np.max(np.abs(audio)) * 32767).astype(np.int16)
            seg = AudioSegment(audio.tobytes(), frame_rate=24000, sample_width=2, channels=1)
            seg.export(full_path, format="mp3")
            print(f"\n[ZAPISANO] {fname}")
        except Exception as e:
            print(f"\n[BŁĄD ZAPISU] {e}")

    def draw_ui(self, rssi, title):
        bar_len = 30
        min_db, max_db = -70, 0  # Szersza skala dla lepszej widoczności
        
        # Obliczanie pozycji paska i progu
        level = int((max(min(rssi, max_db), min_db) - min_db) / (max_db - min_db) * bar_len)
        thresh_pos = int((self.rssi_threshold - min_db) / (max_db - min_db) * bar_len)
        
        bar = list("-" * bar_len)
        for i in range(level):
            if i < bar_len: bar[i] = "█"
        
        # Wstawienie znacznika progu
        if 0 <= thresh_pos < bar_len:
            bar[thresh_pos] = "║"
            
        bar_str = "".join(bar)
        
        if self.is_recording:
            status = f" [WAIT {self.hang_time_counter:.1f}s]" if self.hang_time_counter > 0 else " [REC!]"
        else:
            status = " [SCAN]"
            
        sys.stdout.write(f"\r{title[:12]:<12} |{bar_str}| {rssi:.1f} dB{status}    ")
        sys.stdout.flush()

    def run(self):
        # --- NOWY PRÓG DLA TEJ SKALI ---
        self.rssi_threshold = -35.0 # Ustawiamy na -35, bo szum powinien być niżej
        print(f"Skanowanie {len(self.frequencies)} kanałów. Próg: {self.rssi_threshold} dB")
        last_time = time.time()
        
        try:
            while True:
                for entry in self.frequencies:
                    f, t = entry['freq'], entry['title']
                    self.sdr.center_freq = f
                    time.sleep(0.12) # Stabilizacja tunera
                    
                    try:
                        samples = self.sdr.read_samples(131072)
                        # Demodulacja do FM
                        audio = np.diff(np.unwrap(np.angle(samples)))
                        # Filtracja mowy
                        filtered = self.butter_bandpass_filter(audio, fs=24000)
                        
                        # Obliczanie RSSI (logarytm z RMS)
                        rms = np.sqrt(np.mean(filtered**2))
                        rssi = 20 * np.log10(rms + 1e-12) 
                    except:
                        continue

                    self.draw_ui(rssi, t)
                    
                    now = time.time()
                    dt = now - last_time
                    last_time = now

                    if rssi > self.rssi_threshold:
                        if not self.is_recording:
                            self.current_title, self.current_freq_mhz = t, f / 1e6
                        self.is_recording = True
                        self.hang_time_counter = self.hang_time_limit
                        self.audio_buffer.append(samples)
                    else:
                        if self.is_recording:
                            self.hang_time_counter -= dt
                            self.audio_buffer.append(samples)
                            if self.hang_time_counter <= 0:
                                self.save_file()
                                self.audio_buffer, self.is_recording = [], False
                                
        except KeyboardInterrupt:
            self.sdr.close()

if __name__ == "__main__":
    scanner = ProfessionalRadioScanner(XML_FILE)
    scanner.run()