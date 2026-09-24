import os
import subprocess
import tempfile
from pathlib import Path

import streamlit as st
from openai import OpenAI


# ============================================================
# KONFIGURACJA STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Generowanie napisów do filmów MP4",
    layout="centered"
)


# ============================================================
# FUNKCJE POMOCNICZE
# ============================================================

def formatuj_czas_srt(seconds):
    """
    Zamienia czas w sekundach na format SRT:
    HH:MM:SS,mmm
    """

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds % 1) * 1000))

    # Korekta sytuacji, gdy zaokrąglenie da 1000 ms
    if milliseconds == 1000:
        milliseconds = 0
        secs += 1

    if secs == 60:
        secs = 0
        minutes += 1

    if minutes == 60:
        minutes = 0
        hours += 1

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{milliseconds:03d}"
    )


def utworz_srt(segments):
    """
    Tworzy zawartość pliku SRT z listy segmentów.
    """

    lines = []

    for i, segment in enumerate(segments, start=1):
        start_time = formatuj_czas_srt(segment["start"])
        end_time = formatuj_czas_srt(segment["end"])

        lines.append(
            f"{i}\n"
            f"{start_time} --> {end_time}\n"
            f"{segment['text'].strip()}\n"
        )

    return "\n".join(lines)


def przetlumacz_segmenty(client, segments, language):
    """
    Tłumaczy wszystkie segmenty na język polski.

    Zachowuje:
    - numery segmentów,
    - czas rozpoczęcia,
    - czas zakończenia.

    Zmienia tylko tekst.
    """

    tekst_do_tlumaczenia = "\n".join(
        f"{i}. {segment['text'].strip()}"
        for i, segment in enumerate(segments, start=1)
    )

    prompt = f"""
Przetłumacz poniższy tekst z języka {language} na język polski.

Bardzo ważne zasady:

1. Zachowaj dokładnie tę samą liczbę segmentów.
2. Nie zmieniaj numeracji.
3. Nie dodawaj komentarzy ani wyjaśnień.
4. Każdy segment ma być zapisany w osobnej linii.
5. Zachowaj format:

1. przetłumaczony tekst
2. przetłumaczony tekst
3. przetłumaczony tekst

Tekst do przetłumaczenia:

{tekst_do_tlumaczenia}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    wynik = response.output_text.strip()

    translated_lines = []

    for line in wynik.splitlines():
        line = line.strip()

        if not line:
            continue

        # Usunięcie numeracji typu:
        # 1. tekst
        # 2. tekst
        if "." in line:
            number_part, text_part = line.split(".", 1)

            if number_part.strip().isdigit():
                translated_lines.append(text_part.strip())
            else:
                translated_lines.append(line)
        else:
            translated_lines.append(line)

    # Jeżeli model zwrócił poprawną liczbę segmentów
    if len(translated_lines) == len(segments):

        translated_segments = []

        for segment, translated_text in zip(
            segments,
            translated_lines
        ):
            translated_segments.append(
                {
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": translated_text
                }
            )

        return translated_segments

    # Jeżeli format odpowiedzi był niepoprawny,
    # przerywamy z czytelnym komunikatem.
    raise ValueError(
        "Model tłumaczący zwrócił inną liczbę segmentów "
        "niż liczba segmentów transkrypcji."
    )


def pobierz_api_key():
    """
    Pobiera OPENAI_API_KEY.

    Priorytet:
    1. Streamlit Secrets
    2. zmienna środowiskowa
    """

    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        api_key = None

    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")

    return api_key


# ============================================================
# STAN APLIKACJI
# ============================================================

if "przetwarzanie_zakonczone" not in st.session_state:
    st.session_state.przetwarzanie_zakonczone = False

if "wyniki" not in st.session_state:
    st.session_state.wyniki = None


# ============================================================
# TYTUŁ
# ============================================================

st.title("🎬 Generowanie napisów do filmów MP4")


# ============================================================
# INFORMACJA O PROGRAMIE
# ============================================================

if not st.session_state.przetwarzanie_zakonczone:

    st.info(
        """
### Jak działa program?

Program umożliwia wybranie pliku MP4, a następnie:

1. wyciąga z niego ścieżkę dźwiękową,
2. zapisuje ją jako plik MP3,
3. analizuje nagranie za pomocą modułu rozpoznawania mowy,
4. tworzy plik TXT zawierający czasy i rozpoznany tekst,
5. tworzy plik SRT z napisami,
6. jeżeli język nagrania nie jest polski, tworzy również
   przetłumaczony na język polski plik SRT,
7. tworzy kopię pliku MP4 z osadzoną ścieżką napisów.

Wygenerowane pliki można następnie pobrać na swój komputer.
"""
    )


# ============================================================
# KLUCZ OPENAI
# ============================================================

api_key = pobierz_api_key()

if not api_key:

    st.warning(
        """
Nie znaleziono klucza `OPENAI_API_KEY`.

W przypadku Streamlit Community Cloud dodaj go w:

**App → Settings → Secrets**

w postaci:

```toml
OPENAI_API_KEY = "twój_klucz_api"
"""
    )

st.stop()
client = OpenAI(api_key=api_key)

# ============================================================
# WYBÓR PLIKU
# ============================================================

if not st.session_state.przetwarzanie_zakonczone:

    uploaded_file = st.file_uploader(
    "Wybierz plik MP4",
    type=["mp4"],
    help="Wybierz film, dla którego chcesz wygenerować napisy."
)


# ========================================================
# PRZETWARZANIE
# ========================================================

if uploaded_file is not None:

    st.info("### Przetwarzanie w toku...")

    try:

        # ------------------------------------------------
        # KATALOG TYMCZASOWY
        # ------------------------------------------------

        temp_dir = tempfile.mkdtemp()

        original_name = Path(uploaded_file.name).stem

        video_path = os.path.join(
            temp_dir,
            uploaded_file.name
        )

        audio_path = os.path.join(
            temp_dir,
            f"{original_name}.mp3"
        )

        txt_path = os.path.join(
            temp_dir,
            f"{original_name}.txt"
        )

        srt_path = os.path.join(
            temp_dir,
            f"{original_name}.srt"
        )

        translated_srt_path = os.path.join(
            temp_dir,
            f"{original_name}_tłumaczenie_na_pl.srt"
        )

        output_mp4_path = os.path.join(
            temp_dir,
            f"{original_name}_z_napisami.mp4"
        )


        # ------------------------------------------------
        # ZAPISANIE UPLOADED FILE NA DYSKU
        # ------------------------------------------------

        with open(video_path, "wb") as video_file:

            video_file.write(
                uploaded_file.getbuffer()
            )


        # ------------------------------------------------
        # SPRAWDZENIE ROZMIARU PLIKU
        # ------------------------------------------------

        video_size_mb = os.path.getsize(video_path) / (
            1024 * 1024
        )

        st.write(
            f"📁 Wybrany plik: **{uploaded_file.name}**"
        )

        st.write(
            f"📦 Rozmiar pliku: **{video_size_mb:.2f} MB**"
        )


        # ------------------------------------------------
        # WYCIĄGNIĘCIE AUDIO Z MP4
        # ------------------------------------------------

        st.write("🎵 Wyodrębnianie ścieżki audio...")

        ffmpeg_audio_command = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            audio_path
        ]

        subprocess.run(
            ffmpeg_audio_command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )


        # ------------------------------------------------
        # TRANSKRYPCJA
        # ------------------------------------------------

        st.write(
            "🎙️ Rozpoznawanie mowy..."
        )

        with open(audio_path, "rb") as audio_file:

            transcript = (
                client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            )


        # ------------------------------------------------
        # SEGMENTY
        # ------------------------------------------------

        segments = [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            for segment in transcript.segments
        ]


        if not segments:
            raise ValueError(
                "Transkrypcja nie zawiera żadnych segmentów."
            )


        detected_language = (
            transcript.language
            if transcript.language
            else "unknown"
        )


        st.write(
            f"🌐 Wykryty język: **{detected_language}**"
        )


        # ------------------------------------------------
        # PLIK TXT
        # ------------------------------------------------

        st.write(
            "📝 Tworzenie pliku TXT..."
        )

        with open(
            txt_path,
            "w",
            encoding="utf-8"
        ) as txt_file:

            for segment in segments:

                start_time = formatuj_czas_srt(
                    segment["start"]
                )

                end_time = formatuj_czas_srt(
                    segment["end"]
                )

                txt_file.write(
                    f"{start_time} - "
                    f"{end_time} - "
                    f"{segment['text'].strip()}\n"
                )


        # ------------------------------------------------
        # PLIK SRT
        # ------------------------------------------------

        st.write(
            "🎞️ Tworzenie pliku SRT..."
        )

        srt_content = utworz_srt(
            segments
        )

        with open(
            srt_path,
            "w",
            encoding="utf-8"
        ) as srt_file:

            srt_file.write(
                srt_content
            )


        # ------------------------------------------------
        # TŁUMACZENIE NA POLSKI
        # ------------------------------------------------

        translated_srt_content = None

        language_lower = detected_language.lower()

        if language_lower not in (
            "polish",
            "polski",
            "pl"
        ):

            st.write(
                "🇵🇱 Tłumaczenie napisów na język polski..."
            )

            translated_segments = (
                przetlumacz_segmenty(
                    client,
                    segments,
                    detected_language
                )
            )

            translated_srt_content = (
                utworz_srt(
                    translated_segments
                )
            )

            with open(
                translated_srt_path,
                "w",
                encoding="utf-8"
            ) as translated_file:

                translated_file.write(
                    translated_srt_content
                )


        # ------------------------------------------------
        # OSADZENIE NAPISÓW W MP4
        # ------------------------------------------------

        st.write(
            "🎬 Osadzanie napisów w pliku MP4..."
        )

        ffmpeg_command = [
            "ffmpeg",
            "-y",

            "-i",
            video_path,

            "-i",
            srt_path,

            "-map",
            "0:v",

            "-map",
            "0:a?",

            "-map",
            "1:0",

            "-c:v",
            "copy",

            "-c:a",
            "copy",

            "-c:s",
            "mov_text",

            "-metadata:s:s:0",
            "language=und",

            "-metadata:s:s:0",
            f"title=Napisy {detected_language}",

            output_mp4_path
        ]


        subprocess.run(
            ffmpeg_command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )


        # ------------------------------------------------
        # ZAPIS W SESSION STATE
        # ------------------------------------------------

        st.session_state.wyniki = {
            "audio_path": audio_path,
            "txt_path": txt_path,
            "srt_path": srt_path,
            "translated_srt_path": (
                translated_srt_path
                if translated_srt_content is not None
                else None
            ),
            "output_mp4_path": output_mp4_path,
            "original_name": original_name,
            "language": detected_language
        }

        st.session_state.przetwarzanie_zakonczone = True

        st.rerun()


    except Exception as e:

        st.error(
            "Wystąpił błąd podczas przetwarzania pliku."
        )

        st.exception(e)

        st.stop()

# ============================================================
# WYNIKI
# ============================================================

if st.session_state.przetwarzanie_zakonczone:
    st.success(
    """
Przetwarzanie zakończone.

Wygenerowane pliki są dostępne poniżej.
"""
    )

wyniki = st.session_state.wyniki


# ========================================================
# MP3
# ========================================================

audio_path = wyniki["audio_path"]

if os.path.exists(audio_path):

    with open(
        audio_path,
        "rb"
    ) as file:

        st.download_button(
            label="⬇️ Pobierz MP3",
            data=file.read(),
            file_name=os.path.basename(
                audio_path
            ),
            mime="audio/mpeg",
            use_container_width=True
        )


# ========================================================
# TXT
# ========================================================

txt_path = wyniki["txt_path"]

if os.path.exists(txt_path):

    with open(
        txt_path,
        "rb"
    ) as file:

        st.download_button(
            label="⬇️ Pobierz TXT",
            data=file.read(),
            file_name=os.path.basename(
                txt_path
            ),
            mime="text/plain",
            use_container_width=True
        )


# ========================================================
# ORYGINALNY SRT
# ========================================================

srt_path = wyniki["srt_path"]

if os.path.exists(srt_path):

    with open(
        srt_path,
        "rb"
    ) as file:

        st.download_button(
            label="⬇️ Pobierz SRT",
            data=file.read(),
            file_name=os.path.basename(
                srt_path
            ),
            mime="application/x-subrip",
            use_container_width=True
        )


# ========================================================
# TŁUMACZONY SRT
# ========================================================

translated_srt_path = (
    wyniki["translated_srt_path"]
)

if (
    translated_srt_path
    and os.path.exists(translated_srt_path)
):

    st.download_button(
        label="🇵🇱 Pobierz SRT po polsku",
        data=open(
            translated_srt_path,
            "rb"
        ).read(),
        file_name=os.path.basename(
            translated_srt_path
        ),
        mime="application/x-subrip",
        use_container_width=True
    )


# ========================================================
# MP4 Z NAPISAMI
# ========================================================

output_mp4_path = (
    wyniki["output_mp4_path"]
)

if os.path.exists(output_mp4_path):

    with open(
        output_mp4_path,
        "rb"
    ) as file:

        st.download_button(
            label="🎬 Pobierz MP4 z napisami",
            data=file.read(),
            file_name=os.path.basename(
                output_mp4_path
            ),
            mime="video/mp4",
            use_container_width=True
        )


# ========================================================
# INFORMACJA
# ========================================================

st.info(
    """
Jeśli chcesz wybrać kolejny plik wciśnij Tak.

Jeśli chcesz zakończyć wciśnij Nie.
"""
)

# ========================================================
# PRZYCISKI TAK / NIE
# ========================================================

col1, col2 = st.columns(2)


with col1:

    if st.button(
        "Tak",
        use_container_width=True
    ):

        st.session_state.przetwarzanie_zakonczone = False
        st.session_state.wyniki = None

        st.rerun()


with col2:

    if st.button(
        "Nie",
        use_container_width=True
    ):

        st.session_state.przetwarzanie_zakonczone = False
        st.session_state.wyniki = None

        st.rerun()

        st.stop()