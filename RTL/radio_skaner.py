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
from scipy.signal import butter, lfilter, resample_poly

# Wymuszenie ścieżki do FFmpeg (rozwiązuje błąd RuntimeWarning)
FFMPEG_EXE = os.path.join(LIB_DIR, "ffmpeg.exe")
AudioSegment.converter = FFMPEG_EXE
AudioSegment.ffprobe = os.path.join(LIB_DIR, "ffprobe.exe")

try:
    import webrtcvad
except ImportError:
    webrtcvad = None
    print("UWAGA: webrtcvad nie jest zainstalowany - użyję prostej detekcji energetycznej.")

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
        
        # WebRTC VAD - tryb 2 (średnia agresywność)
        self.vad = webrtcvad.Vad(2) if webrtcvad else None
        self.vad_sample_rate = 16000  # WebRTC VAD wymaga 8kHz, 16kHz, 32kHz lub 48kHz
        self.vad_frame_duration_ms = 30  # musi być 10, 20 lub 30 ms
        self.vad_frame_samples = self.vad_sample_rate * self.vad_frame_duration_ms // 1000
        
        # --- KALIBRACJA (Zmienione, by nie łapać szumu -35dB) ---
        self.rssi_threshold = -20.0  # Było -25, teraz jest znacznie wyżej (bezpieczniej)
        self.hang_time_limit = 3.0   # Czas oczekiwania po utracie sygnału (3s dla lepszej tolerancji)
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
        self.rms_activity_delta = 3.0  # dB powyżej średniej szumu (obniżone dla lepszej detekcji)
        self.noise_floor_db = -60.0  # Poziom szumu do adaptacyjnej kalibracji

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

    def _rms_db(self, audio_float):
        """Oblicza poziom RMS w dB"""
        rms = np.sqrt(np.mean(audio_float * audio_float) + 1e-12)
        return 20.0 * np.log10(rms + 1e-12)

    def _energy_fallback_vad(self, audio_float):
        """Prosta detekcja mowy na podstawie energii i zero-crossing gdy brak webrtcvad"""
        energy = self._rms_db(audio_float)
        zc = np.mean(np.abs(np.diff(np.signbit(audio_float))))
        return (energy > self.noise_floor_db + 9.0) and (0.02 < zc < 0.35)

    def _is_voice_detected(self, audio_float):
        """
        Detekcja mowy używając WebRTC VAD lub fallback energetyczny.
        audio_float: znormalizowane audio float32 (-1.0 do 1.0)
        Zwraca: (is_voice, audio_db)
        """
        audio_db = self._rms_db(audio_float)
        
        # Adaptacyjna kalibracja poziomu szumu gdy nie nagrywamy
        if not self.is_recording:
            self.noise_floor_db = 0.98 * self.noise_floor_db + 0.02 * min(audio_db, self.noise_floor_db + 1.0)
        
        # Sprawdzenie czy sygnał jest wystarczająco silny
        strong_signal = audio_db > (self.noise_floor_db + 7.0)
        
        if self.vad and len(audio_float) == self.vad_frame_samples:
            # Konwersja do int16 dla WebRTC VAD
            audio_i16 = np.clip(audio_float * 32767.0, -32768, 32767).astype(np.int16)
            try:
                speech = self.vad.is_speech(audio_i16.tobytes(), self.vad_sample_rate)
            except Exception:
                speech = self._energy_fallback_vad(audio_float)
        else:
            # Fallback bez VAD lub niewłaściwa długość ramki
            speech = self._energy_fallback_vad(audio_float)
        
        return speech and strong_signal, audio_db


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
        self.rssi_threshold = -20.0 # Wyższy próg, mniej szumów
        print(f"Skanowanie częstotliwości 144.950 MHz w trybie N-FM 12kHz")
        if self.vad:
            print("Detekcja głosu: WebRTC VAD (16kHz, 30ms ramki)")
        else:
            print("Detekcja głosu: Fallback energetyczny (zainstaluj webrtcvad dla lepszej skuteczności)")
        print(f"Próg RSSI: {self.rssi_threshold} dB")
        
        last_time = time.time()
        freq = 144950000
        title = "144.950 MHz"
        
        # Bufor dla audio 16kHz do analizy VAD
        vad_audio_buffer = np.array([], dtype=np.float32)
        
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
                    
                    # Normalizacja audio do -1.0 .. +1.0
                    peak = np.max(np.abs(filtered)) if filtered.size else 1.0
                    if peak > 1e-9:
                        audio_normalized = 0.9 * filtered / peak
                    else:
                        audio_normalized = filtered
                    audio_normalized = audio_normalized.astype(np.float32)
                    
                    # --- KROK 5: Resample do 16kHz dla VAD ---
                    # Z ~48.8 kHz do 16 kHz (resample 16/48.8 ≈ 16/49)
                    audio_16k = resample_poly(audio_normalized, up=160, down=int(fs_audio/100))
                    vad_audio_buffer = np.concatenate([vad_audio_buffer, audio_16k])
                    
                except Exception as e:
                    print(f"\nBŁĄD PRZETWARZANIA: {e}")
                    continue
                
                # --- KROK 6: Przetwarzanie ramek VAD ---
                now = time.time()
                dt = now - last_time
                last_time = now
                
                # Przetwarzamy wszystkie kompletne ramki VAD
                is_voice_in_block = False
                avg_db_in_block = -100.0
                db_values = []
                
                while len(vad_audio_buffer) >= self.vad_frame_samples:
                    frame = vad_audio_buffer[:self.vad_frame_samples]
                    vad_audio_buffer = vad_audio_buffer[self.vad_frame_samples:]
                    
                    is_voice, frame_db = self._is_voice_detected(frame)
                    db_values.append(frame_db)
                    if is_voice:
                        is_voice_in_block = True
                
                # Średni poziom dB z bloku
                if db_values:
                    avg_db_in_block = np.mean(db_values)
                else:
                    avg_db_in_block = self.noise_floor_db
                
                self.draw_ui(avg_db_in_block, title)
                
                # --- Logika nagrywania ---
                if is_voice_in_block:
                    if not self.is_recording:
                        self.current_title, self.current_freq_mhz = title, freq / 1e6
                        print(f"\n[START NAGRYWANIA - VAD wykrył mowę] {self.current_title} {self.current_freq_mhz:.3f} MHz | poziom {avg_db_in_block:.1f} dB")
                        self.recording_time_counter = 0.0
                    self.is_recording = True
                    self.hang_time_counter = self.hang_time_limit
                    self.audio_buffer.append(samples)
                    self.recording_time_counter += dt
                    
                    if self.recording_time_counter >= self.max_recording_time:
                        print(f"\n[ZAPIS AUTOMATYCZNY - LIMIT {self.max_recording_time}s]")
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
            print("\nZatrzymano skanowanie.")
            self.sdr.close()

if __name__ == "__main__":
    scanner = ProfessionalRadioScanner(XML_FILE)
    scanner.run()