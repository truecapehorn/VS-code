import noisereduce as nr
import os
import time
import wave
import datetime
from collections import deque
import sys

import numpy as np
from scipy.signal import butter, lfilter, resample_poly
import scipy.signal
try:
    import sounddevice as sd
except ImportError:
    sd = None

# --- LADOWANIE DLL DLA WINDOWS (RTL/lib) ---
BASE_DIR = os.path.dirname(__file__)
LIB_DIR = os.path.join(BASE_DIR, "lib")
if os.path.isdir(LIB_DIR):
    os.environ["PATH"] = LIB_DIR + os.pathsep + os.environ.get("PATH", "")
    if sys.platform == "win32":
        try:
            os.add_dll_directory(LIB_DIR)
        except (AttributeError, FileNotFoundError):
            pass

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

try:
    from rtlsdr import RtlSdr
except ImportError as exc:
    raise SystemExit(
        "Nie mozna zaladowac rtlsdr. Sprawdz pip install pyrtlsdr "
        "oraz obecność DLL w RTL/lib (rtlsdr.dll, libusb-1.0.dll)."
    ) from exc


# --- KONFIGURACJA ---
FREQ_HZ = 144_950_000
CHANNEL_BW_HZ = 12_000          # N-FM 12 kHz
SDR_SAMPLE_RATE = 1_024_000     # wygodna decymacja do 16 kHz (x64)
AUDIO_SAMPLE_RATE = 16_000
GAIN = 35.0
BLOCK_SAMPLES = 102_400         # ~100 ms IQ
OUTPUT_DIR = os.path.join(BASE_DIR, "nagrania_voice")

# VAD / logika zapisu
FRAME_MS = 20
FRAME_SAMPLES = AUDIO_SAMPLE_RATE * FRAME_MS // 1000
PREBUFFER_SEC = 0.8
HANGOVER_SEC = 1.2
START_VOICE_SEC = 0.12
MAX_TX_SEC = 180
SIGNAL_MARGIN_DB = 12.0
LIVE_MONITOR = True
MONITOR_GAIN = 1.2


class NfmVoiceRecorder:
    def __init__(self):
        self.sdr = RtlSdr()
        self.sdr.sample_rate = SDR_SAMPLE_RATE
        self.sdr.center_freq = FREQ_HZ
        self.sdr.gain = GAIN

        # Niektóre sterowniki wspierają bandwidth, inne nie.
        try:
            self.sdr.bandwidth = CHANNEL_BW_HZ
        except Exception:
            pass

        self.vad = webrtcvad.Vad(2) if webrtcvad else None

        self.noise_floor_db = -60.0
        self.frame_buf = np.array([], dtype=np.float32)
        self.prebuffer = deque(maxlen=max(1, int(PREBUFFER_SEC * 1000 / FRAME_MS)))

        self.recording = False
        self.record_frames = []
        self.voice_streak = 0
        self.prev_frame_db = self.noise_floor_db
        self.silence_streak = 0
        self.frames_in_tx = 0

        self.start_frames = max(1, int(START_VOICE_SEC * 1000 / FRAME_MS))
        # Szybka detekcja końca transmisji: 2 ramki ciszy (40 ms)
        self.hang_frames = 2
        self.max_tx_frames = max(1, int(MAX_TX_SEC * 1000 / FRAME_MS))
        self.monitor_stream = None
        self.monitor_enabled = False

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self._init_monitor()

    def _init_monitor(self):
        if not LIVE_MONITOR:
            return
        if sd is None:
            print("Odsluch live: OFF (brak biblioteki sounddevice)")
            return
        try:
            self.monitor_stream = sd.RawOutputStream(
                samplerate=AUDIO_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
            )
            self.monitor_stream.start()
            self.monitor_enabled = True
            print("Odsluch live: ON (glosnik komputera)")
        except Exception as exc:
            self.monitor_stream = None
            self.monitor_enabled = False
            print(f"Odsluch live: OFF ({exc})")

    @staticmethod
    def _lowpass(data, cutoff_hz, fs_hz, order=5):
        nyq = 0.5 * fs_hz
        b, a = butter(order, cutoff_hz / nyq, btype="low")
        return lfilter(b, a, data)

    @staticmethod
    def _bandpass(data, low_hz, high_hz, fs_hz, order=4):
        nyq = 0.5 * fs_hz
        b, a = butter(order, [low_hz / nyq, high_hz / nyq], btype="band")
        return lfilter(b, a, data)

    @staticmethod
    def _deemphasis(audio, fs_hz, tau=75e-6):
        alpha = np.exp(-1.0 / (fs_hz * tau))
        y = np.empty_like(audio)
        if audio.size == 0:
            return audio
        y[0] = audio[0]
        for i in range(1, len(audio)):
            y[i] = alpha * y[i - 1] + (1 - alpha) * audio[i]
        return y

    def _demod_nfm(self, iq):
        iq_f = self._lowpass(iq, cutoff_hz=CHANNEL_BW_HZ / 2, fs_hz=SDR_SAMPLE_RATE, order=5)
        i = np.real(iq_f)
        q = np.imag(iq_f)

        i_ds = resample_poly(i, up=1, down=64)
        q_ds = resample_poly(q, up=1, down=64)
        iq_ds = i_ds + 1j * q_ds

        phase = np.angle(iq_ds)
        fm = np.diff(np.unwrap(phase))

        fm = self._deemphasis(fm, AUDIO_SAMPLE_RATE)
        fm = self._bandpass(fm, low_hz=250, high_hz=3400, fs_hz=AUDIO_SAMPLE_RATE, order=4)

        # Redukcja szumów: szacuj szum na początku sygnału (pierwsze 0.5 sekundy)
        noise_len = int(AUDIO_SAMPLE_RATE * 0.5)
        noise_clip = fm[:noise_len] if fm.size > noise_len else fm
        fm_denoised = nr.reduce_noise(y=fm, y_noise=noise_clip, sr=AUDIO_SAMPLE_RATE, prop_decrease=1.0)

        # Filtr medianowy (ogranicza trzaski impulsowe)
        fm_denoised = scipy.signal.medfilt(fm_denoised, kernel_size=5)

        peak = np.max(np.abs(fm_denoised)) if fm_denoised.size else 0.0
        if peak > 1e-9:
            fm_denoised = 0.9 * fm_denoised / peak
        return fm_denoised.astype(np.float32)

    @staticmethod
    def _rms_db(frame_float):
        rms = np.sqrt(np.mean(frame_float * frame_float) + 1e-12)
        return 20.0 * np.log10(rms + 1e-12)

    def _energy_fallback_vad(self, frame_float):
        energy = self._rms_db(frame_float)
        zc = np.mean(np.abs(np.diff(np.signbit(frame_float))))
        return (energy > self.noise_floor_db + 9.0) and (0.02 < zc < 0.35)

    def _is_voice(self, frame_float):
        frame_i16 = np.clip(frame_float * 32767.0, -32768, 32767).astype(np.int16)
        frame_db = self._rms_db(frame_float)

        strong_signal = frame_db > (self.noise_floor_db + SIGNAL_MARGIN_DB)
        if not self.recording:
            self.noise_floor_db = 0.98 * self.noise_floor_db + 0.02 * min(frame_db, self.noise_floor_db + 1.0)

        if self.vad:
            speech = self.vad.is_speech(frame_i16.tobytes(), AUDIO_SAMPLE_RATE)
        else:
            speech = self._energy_fallback_vad(frame_float)

        return speech and strong_signal, frame_i16, frame_db

    def _save_tx(self):
        if not self.record_frames:
            return

        date_dir = os.path.join(OUTPUT_DIR, datetime.datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(date_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%H%M%S")
        path = os.path.join(date_dir, f"144.950MHz_{stamp}.wav")

        pcm = np.concatenate(self.record_frames)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(AUDIO_SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())

        secs = len(pcm) / AUDIO_SAMPLE_RATE
        print(f"\n[ZAPISANO] {path} ({secs:.1f} s)")

    def _handle_frame(self, frame_float):
        is_voice, frame_i16, frame_db = self._is_voice(frame_float)
        db_jump = frame_db - self.prev_frame_db
        if self.monitor_enabled and self.monitor_stream is not None:
            out = np.clip(frame_i16.astype(np.float32) * MONITOR_GAIN, -32768, 32767).astype(np.int16)
            try:
                self.monitor_stream.write(out.tobytes())
            except Exception:
                self.monitor_enabled = False
        self.prebuffer.append(frame_i16)

        if self.recording:
            self.record_frames.append(frame_i16)
            self.frames_in_tx += 1

            if is_voice:
                self.silence_streak = 0
            else:
                self.silence_streak += 1

            # Zatrzymaj nagrywanie natychmiast po 2 ramkach ciszy
            if self.silence_streak >= self.hang_frames or self.frames_in_tx >= self.max_tx_frames:
                self._save_tx()
                self.recording = False
                self.record_frames = []
                self.frames_in_tx = 0
                self.silence_streak = 0

        else:
            # Adaptacyjny start: wykryj nagły wzrost poziomu dB (np. > 4 dB względem poprzedniej ramki)
            # oraz VAD wykrywa głos
            if is_voice and db_jump > 4.0:
                self.voice_streak += 1
            else:
                self.voice_streak = max(0, self.voice_streak - 1)

            if self.voice_streak >= self.start_frames:
                self.recording = True
                self.record_frames = list(self.prebuffer)
                self.frames_in_tx = len(self.record_frames)
                self.silence_streak = 0
                self.voice_streak = 0
                print(f"\n[START] Voice @ 144.950 MHz | poziom {frame_db:.1f} dB")

        self.prev_frame_db = frame_db

        status = "REC" if self.recording else "SCAN"
        print(
            f"\r{status} | noise={self.noise_floor_db:6.1f} dB | frame={frame_db:6.1f} dB",
            end="",
            flush=True,
        )

    def run(self):
        print("Nasluch RTL-SDR Blog V4")
        print("Czestotliwosc: 144.950 MHz | Tryb: N-FM 12 kHz")
        if self.vad:
            print("Detekcja glosu: WebRTC VAD")
        else:
            print("Detekcja glosu: fallback energetyczny (zainstaluj webrtcvad dla lepszej skutecznosci)")

        try:
            while True:
                iq = self.sdr.read_samples(BLOCK_SAMPLES)
                audio = self._demod_nfm(iq)
                self.frame_buf = np.concatenate([self.frame_buf, audio])

                while len(self.frame_buf) >= FRAME_SAMPLES:
                    frame = self.frame_buf[:FRAME_SAMPLES]
                    self.frame_buf = self.frame_buf[FRAME_SAMPLES:]
                    self._handle_frame(frame)

        except KeyboardInterrupt:
            print("\nZatrzymano.")
        finally:
            if self.monitor_stream is not None:
                try:
                    self.monitor_stream.stop()
                    self.monitor_stream.close()
                except Exception:
                    pass
            self.sdr.close()


if __name__ == "__main__":
    NfmVoiceRecorder().run()
