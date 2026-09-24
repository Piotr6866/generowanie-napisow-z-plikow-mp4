from tkinter import Tk, filedialog
from pydub import AudioSegment
from dotenv import dotenv_values
from openai import OpenAI
import streamlit as st
import subprocess
import time


# ============================================================
# KONFIGURACJA STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Generowanie napisów do filmów mp4",
    layout="centered"
)


# ============================================================
# ZMIENNE SESSION STATE
# ============================================================

if "przetwarzaj" not in st.session_state:
    st.session_state.przetwarzaj = True

if "przetwarzanie_zakonczone" not in st.session_state:
    st.session_state.przetwarzanie_zakonczone = False


# ============================================================
# WCZYTANIE ZMIENNYCH Z .ENV
# ============================================================

env = dotenv_values(".env")


# ============================================================
# MIEJSCE NA KOMUNIKATY
# ============================================================

komunikat = st.empty()


# ============================================================
# INFORMACJA O DZIAŁANIU PROGRAMU
# ============================================================

if st.session_state.przetwarzaj:

    komunikat.info("""
### Jak działa program?

Program wyciąga z wybranego przez użytkownika pliku MP4 ścieżkę dźwiękową
i zapisuje ją w pliku MP3. Następnie analizuje zapisany plik za pomocą
modułu do rozpoznawania mowy i zapisuje wynik w osobnym pliku tekstowym
w formacie SRT.

Plik SRT zawiera tekst oraz czasy rozpoczęcia i zakończenia poszczególnych sekcji. 
Plik MP4 można następnie otworzyć przykładowo w programie **VLC media player** i w menu:
**Napisy → Dodaj plik z napisami…** wczytać utworzony plik SRT.

Dodatkowo zapisywany jest nowy plik MP4 z zapisaną ścieżki z napisami bezpośrednio w tym pliku
z osobną podścieżkę, wówczas po otwarciu pliku mp4 w programie **VLC media player** możemy wybrać, 
w menu **Napisy | Podścieżka (t)**.
""")

time.sleep(2)

# ============================================================
# KLUCZ API OPENAI
# ============================================================

if not st.session_state.get("openai_api_key"):

    if "OPENAI_API_KEY" in env:
        st.session_state["openai_api_key"] = env["OPENAI_API_KEY"]

    else:
        st.info(
            "Dodaj swój klucz API OpenAI aby móc korzystać z tej aplikacji"
        )

        st.session_state["openai_api_key"] = st.text_input(
            "Klucz API",
            type="password"
        )

        if st.session_state["openai_api_key"]:
            st.rerun()


if not st.session_state.get("openai_api_key"):
    st.stop()


# ============================================================
# KLIENT OPENAI
# ============================================================

openai_client = OpenAI(
    api_key=st.session_state["openai_api_key"]
)


# ============================================================
# FUNKCJA PRZETWARZAJĄCA PLIK
# ============================================================

def przetworz_plik():

    # --------------------------------------------------------
    # WYBÓR PLIKU MP4
    # --------------------------------------------------------

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    video_path = filedialog.askopenfilename(
        title="Wybierz plik MP4",
        filetypes=[
            ("Pliki MP4", "*.mp4"),
            ("Wszystkie pliki", "*.*")
        ]
    )

    root.attributes("-topmost", False)
    root.destroy()


    # --------------------------------------------------------
    # JEŻELI UŻYTKOWNIK WYBRAŁ PLIK
    # --------------------------------------------------------

    if video_path:

        # Usunięcie wcześniejszego komunikatu
        komunikat.empty()

        # Wyświetlenie informacji o rozpoczęciu przetwarzania
        komunikat.info("### Przetwarzanie w toku...")


        # ----------------------------------------------------
        # WYODRĘBNIENIE ŚCIEŻKI AUDIO
        # ----------------------------------------------------

        audio = AudioSegment.from_file(video_path)

        audio_path = video_path.rsplit(".", 1)[0] + ".mp3"

        audio.export(
            audio_path,
            format="mp3"
        )


        # ----------------------------------------------------
        # TRANSKRYPCJA OPENAI
        # ----------------------------------------------------

        with open(audio_path, "rb") as f:

            transcript = openai_client.audio.transcriptions.create(
                file=f,
                model="whisper-1",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )


        # ----------------------------------------------------
        # PRZYGOTOWANIE SEGMENTÓW
        # ----------------------------------------------------

        segments = [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            for segment in transcript.segments
        ]


        # ----------------------------------------------------
        # ZAPIS PLIKU TXT
        # ----------------------------------------------------

        txt_path = video_path.rsplit(".", 1)[0] + ".txt"

        with open(
            txt_path,
            "w",
            encoding="utf-8"
        ) as txt_file:

            for segment in segments:

                start = segment["start"]
                end = segment["end"]

                start_time = (
                    f"{int(start // 3600):02d}:"
                    f"{int((start % 3600) // 60):02d}:"
                    f"{int(start % 60):02d},"
                    f"{int((start % 1) * 1000):03d}"
                )

                end_time = (
                    f"{int(end // 3600):02d}:"
                    f"{int((end % 3600) // 60):02d}:"
                    f"{int(end % 60):02d},"
                    f"{int((end % 1) * 1000):03d}"
                )

                line = (
                    f"{start_time} - "
                    f"{end_time} - "
                    f"{segment['text'].strip()}\n"
                )

                txt_file.write(line)


        # ----------------------------------------------------
        # ZAPIS PLIKU SRT
        # ----------------------------------------------------

        srt_path = video_path.rsplit(".", 1)[0] + ".srt"

        with open(
            srt_path,
            "w",
            encoding="utf-8"
        ) as srt_file:

            for i, segment in enumerate(
                segments,
                start=1
            ):

                start = segment["start"]
                end = segment["end"]

                start_time = (
                    f"{int(start // 3600):02d}:"
                    f"{int((start % 3600) // 60):02d}:"
                    f"{int(start % 60):02d},"
                    f"{int((start % 1) * 1000):03d}"
                )

                end_time = (
                    f"{int(end // 3600):02d}:"
                    f"{int((end % 3600) // 60):02d}:"
                    f"{int(end % 60):02d},"
                    f"{int((end % 1) * 1000):03d}"
                )

                line = (
                    f"{i}\n"
                    f"{start_time} --> {end_time}\n"
                    f"{segment['text'].strip()}\n\n"
                )

                srt_file.write(line)


        # ----------------------------------------------------
        # DODANIE NAPISÓW DO PLIKU MP4
        # ----------------------------------------------------

        output_path = (
            video_path.rsplit(".", 1)[0]
            + "_z_napisami.mp4"
        )

        command = [
            "ffmpeg","-y",
            "-i",  video_path,
            "-i",srt_path,
            "-map","0:v",
            "-map","0:a?",
            "-map","1:0",
            "-c:v","copy",
            "-c:a","copy",
            "-c:s","mov_text",
            "-metadata:s:s:0",f"language={transcript.language}",
            "-metadata:s:s:0",f"title=Napisy {transcript.language}",
            output_path
        ]


        subprocess.run(
            command,
            check=True
        )


        # ----------------------------------------------------
        # PRZETWARZANIE ZAKOŃCZONE
        # ----------------------------------------------------

        st.session_state.przetwarzanie_zakonczone = True


# ============================================================
# URUCHOMIENIE PRZETWARZANIA
# ============================================================

if (
    st.session_state.przetwarzaj
    and not st.session_state.przetwarzanie_zakonczone
):

    przetworz_plik()


# ============================================================
# KOMUNIKAT PO ZAKOŃCZENIU PRZETWARZANIA
# ============================================================

if st.session_state.przetwarzanie_zakonczone:

    # --------------------------------------------------------
    # KOMUNIKAT
    # --------------------------------------------------------

    komunikat.empty()

    komunikat.info("""
### Przetwarzanie zakończone.

Jeśli chcesz wybrać kolejny plik wciśnij **Tak**.

Jeśli chcesz zakończyć wciśnij **Nie**.
""")


    # --------------------------------------------------------
    # PRZYCISKI
    # --------------------------------------------------------

    col1, col2 = st.columns(2)


    with col1:

        if st.button("Tak"):

            # Najpierw zmieniamy stan
            st.session_state.przetwarzaj = True
            st.session_state.przetwarzanie_zakonczone = False

            # Następnie ponownie uruchamiamy aplikację
            st.rerun()


    with col2:

        if st.button("Nie"):

            # Zmieniamy stan aplikacji
            st.session_state.przetwarzaj = False
            st.session_state.przetwarzanie_zakonczone = False

            # Ponownie uruchamiamy aplikację
            st.rerun()