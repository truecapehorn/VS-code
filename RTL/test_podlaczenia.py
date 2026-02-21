import os
import sys

# --- TO DODAŁAM, ABY ROZWIĄZAĆ TWÓJ BŁĄD ---
# Ścieżka do folderu, w którym jest Twój skrypt i plik .dll
script_dir = r"c:\Users\truec\python_scripts\VS Code\RTL"
os.add_dll_directory(script_dir) 
# ------------------------------------------

try:
    from rtlsdr import RtlSdr
    sdr = RtlSdr()
    print("Sukces! Połączono z RTL-SDR Blog V4.")
    print(f"Aktualna częstotliwość: {sdr.center_freq / 1e6} MHz")
    sdr.close()
except ImportError as e:
    print(f"Nadal brakuje pliku DLL: {e}")
except Exception as e:
    print(f"Błąd hardware'u (czy masz zainstalowany WinUSB przez Zadig?): {e}")