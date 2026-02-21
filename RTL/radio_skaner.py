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
        self.recording_time_counter = 0.0  # Licznik czasu nagrania
        self.max_recording_time = 10.0     # Maksymalna długość nagrania w sekundach
        self.clear_recordings()
        self.rms_history = []
        self.rms_history_len = 40  # ok. 5 sekund przy ~8 cyklach/s
        self.rms_activity_delta = 6.0  # dB powyżej średniej szumu

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

    def butter_lowpass_filter(self, data, cutoff=6000, fs=2.048e6, order=5):
        """Filtr dolnoprzepustowy dla wydzielenia kanału NFM 12kHz"""
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype='low')
        return lfilter(b, a, data)

    def butter_bandpass_filter(self, data, lowcut=300, highcut=3000, fs=24000, order=5):
        """Filtr pasmowy dla audio (mowa)"""
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
            
            # Pełne przetwarzanie N-FM dla zapisu
            filtered_channel = self.butter_lowpass_filter(samples, cutoff=6000, fs=self.sdr.sample_rate)
            decimation_factor = 42
            decimated = filtered_channel[::decimation_factor]
            audio = np.diff(np.unwrap(np.angle(decimated)))
            fs_audio = self.sdr.sample_rate / decimation_factor
            audio = self.butter_bandpass_filter(audio, lowcut=300, highcut=3000, fs=fs_audio)
            
            # Normalizacja i eksport
            audio = (audio / np.max(np.abs(audio)) * 32767).astype(np.int16)
            seg = AudioSegment(audio.tobytes(), frame_rate=int(fs_audio), sample_width=2, channels=1)
            seg.export(full_path, format="mp3")
            print(f"\n[ZAPISANO N-FM] {fname}")
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
        self.rssi_threshold = -5.0 # Wyższy próg, mniej szumów
        print(f"Skanowanie częstotliwości 144.950 MHz w trybie N-FM 12kHz")
        print(f"Próg RSSI: {self.rssi_threshold} dB + detekcja aktywności ({self.rms_activity_delta} dB powyżej szumu)")
        last_time = time.time()
        freq = 144950000
        title = "144.950 MHz"
        try:
            while True:
                self.sdr.center_freq = freq
                time.sleep(0.12) # Stabilizacja tunera
                try:
                    samples = self.sdr.read_samples(131072)
                    
                    # --- KROK 1: Filtracja kanału N-FM 12kHz ---
                    # Filtr dolnoprzepustowy ~6kHz (połowa szerokości kanału NFM)
                    filtered_channel = self.butter_lowpass_filter(samples, cutoff=6000, fs=self.sdr.sample_rate)
                    
                    # --- KROK 2: Decymacja próbek ---
                    # Z 2.048 MHz do ~48 kHz (decymacja 42x)
                    decimation_factor = 42
                    decimated = filtered_channel[::decimation_factor]
                    
                    # --- KROK 3: Demodulacja FM ---
                    audio = np.diff(np.unwrap(np.angle(decimated)))
                    
                    # --- KROK 4: Filtracja mowy (300-3000 Hz) ---
                    fs_audio = self.sdr.sample_rate / decimation_factor  # ~48.8 kHz
                    filtered = self.butter_bandpass_filter(audio, lowcut=300, highcut=3000, fs=fs_audio)
                    
                    # --- KROK 5: Obliczanie RSSI ---
                    rms = np.sqrt(np.mean(filtered**2))
                    rssi = 20 * np.log10(rms + 1e-12)
                    print(f"DEBUG: freq={freq/1e6:.3f} MHz, rssi={rssi:.1f} dB [N-FM 12kHz]")
                except Exception as e:
                    print(f"\nBŁĄD PRZETWARZANIA: {e}")
                    continue
                self.draw_ui(rssi, title)
                now = time.time()
                dt = now - last_time
                last_time = now
                # --- Detekcja aktywności na podstawie RMS względem tła ---
                self.rms_history.append(rssi)
                if len(self.rms_history) > self.rms_history_len:
                    self.rms_history.pop(0)
                rms_avg = np.mean(self.rms_history) if self.rms_history else rssi
                is_active = (rssi > self.rssi_threshold) and (rssi > rms_avg + self.rms_activity_delta)
                if is_active:
                    if not self.is_recording:
                        self.current_title, self.current_freq_mhz = title, freq / 1e6
                        print(f"\n[START NAGRYWANIA] {self.current_title} {self.current_freq_mhz:.3f} MHz")
                        self.recording_time_counter = 0.0
                    self.is_recording = True
                    self.hang_time_counter = self.hang_time_limit
                    self.audio_buffer.append(samples)
                    self.recording_time_counter += dt
                    if self.recording_time_counter >= self.max_recording_time:
                        print(f"\n[ZAPIS AUTOMATYCZNY - LIMIT 10s]")
                        self.save_file()
                        self.audio_buffer, self.is_recording = [], False
                        self.recording_time_counter = 0.0
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