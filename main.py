from flask import Flask, render_template, request, jsonify, send_file

import os
import re
import html
import time
import tempfile
import unicodedata
import requests
import shutil

from dotenv import load_dotenv

from youtube_transcript_api import YouTubeTranscriptApi


# =========================================================
# AI TRANSCRIPTION
# =========================================================

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =========================================================
# YOUTUBE TRANSCRIPT ERRORS
# =========================================================

try:
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
        CouldNotRetrieveTranscript,
        RequestBlocked,
        IpBlocked
    )

except ImportError:

    class TranscriptsDisabled(Exception):
        pass

    class NoTranscriptFound(Exception):
        pass

    class VideoUnavailable(Exception):
        pass

    class CouldNotRetrieveTranscript(Exception):
        pass

    class RequestBlocked(Exception):
        pass

    class IpBlocked(Exception):
        pass


# =========================================================
# PROXY CONFIG
# =========================================================

try:
    from youtube_transcript_api.proxies import (
        WebshareProxyConfig,
        GenericProxyConfig
    )

except ImportError:
    WebshareProxyConfig = None
    GenericProxyConfig = None


# =========================================================
# REPORTLAB
# =========================================================

from reportlab.lib.pagesizes import A4

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)

from reportlab.lib.enums import TA_LEFT

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

YOUTUBE_API_KEY = os.getenv(
    "YOUTUBE_API_KEY",
    ""
).strip()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    ""
).strip()

OPENAI_TRANSCRIBE_MODEL = os.getenv(
    "OPENAI_TRANSCRIBE_MODEL",
    "gpt-4o-mini-transcribe"
).strip()


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

FONT_DIR = os.path.join(
    BASE_DIR,
    "fonts"
)


# =========================================================
# PROXY URL NORMALIZER
# =========================================================

def normalize_proxy_url(proxy):

    if not proxy:
        return None

    proxy = str(proxy).strip()

    if not proxy:
        return None

    if proxy.startswith(
        (
            "http://",
            "https://",
            "socks5://",
            "socks5h://"
        )
    ):
        return proxy

    return "http://" + proxy


# =========================================================
# CREATE YOUTUBE API
# =========================================================

def create_youtube_api():

    webshare_username = os.getenv(
        "WEBSHARE_PROXY_USERNAME",
        ""
    ).strip()

    webshare_password = os.getenv(
        "WEBSHARE_PROXY_PASSWORD",
        ""
    ).strip()

    http_proxy = normalize_proxy_url(
        os.getenv(
            "YOUTUBE_HTTP_PROXY",
            ""
        )
    )

    https_proxy = normalize_proxy_url(
        os.getenv(
            "YOUTUBE_HTTPS_PROXY",
            ""
        )
    )

    # -----------------------------------------------------
    # WEBSHARE
    # -----------------------------------------------------

    if (
        webshare_username
        and webshare_password
    ):

        if WebshareProxyConfig is None:

            raise RuntimeError(
                "WebshareProxyConfig is unavailable. "
                "Please install youtube-transcript-api==1.2.4."
            )

        try:

            print(
                "YouTube API: Webshare proxy ENABLED"
            )

            return YouTubeTranscriptApi(

                proxy_config=WebshareProxyConfig(

                    proxy_username=
                        webshare_username,

                    proxy_password=
                        webshare_password

                )

            )

        except Exception as e:

            print(
                "WEBSHARE ERROR:",
                repr(e)
            )

            raise RuntimeError(
                "Webshare proxy configuration failed. "
                "Please check your proxy credentials."
            )


    # -----------------------------------------------------
    # GENERIC PROXY
    # -----------------------------------------------------

    if http_proxy or https_proxy:

        if GenericProxyConfig is None:

            raise RuntimeError(
                "GenericProxyConfig is unavailable. "
                "Please install youtube-transcript-api==1.2.4."
            )

        try:

            print(
                "YouTube API: Generic proxy ENABLED"
            )

            return YouTubeTranscriptApi(

                proxy_config=GenericProxyConfig(

                    http_url=http_proxy,

                    https_url=https_proxy

                )

            )

        except Exception as e:

            print(
                "GENERIC PROXY ERROR:",
                repr(e)
            )

            raise RuntimeError(
                "Generic proxy configuration failed. "
                "Please check your proxy URL."
            )


    # -----------------------------------------------------
    # DIRECT
    # -----------------------------------------------------

    print(
        "YouTube API: NO PROXY configured"
    )

    return YouTubeTranscriptApi()


# =========================================================
# TRANSLATION LANGUAGES
# =========================================================

TRANSLATION_LANGUAGES = {

    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
    "or": "Odia",
    "as": "Assamese",

    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",

    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Chinese",

    "ar": "Arabic",
    "ru": "Russian"
}


# =========================================================
# NORMALIZE LANGUAGE
# =========================================================

def normalize_language(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value in TRANSLATION_LANGUAGES:
        return value

    lower = value.lower()

    aliases = {

        "english": "en",
        "hindi": "hi",
        "bengali": "bn",
        "bangla": "bn",
        "telugu": "te",
        "marathi": "mr",
        "tamil": "ta",
        "gujarati": "gu",
        "kannada": "kn",
        "malayalam": "ml",
        "punjabi": "pa",
        "urdu": "ur",
        "odia": "or",
        "oriya": "or",
        "assamese": "as",

        "spanish": "es",
        "french": "fr",
        "german": "de",
        "italian": "it",
        "portuguese": "pt",

        "japanese": "ja",
        "korean": "ko",

        "chinese": "zh-CN",
        "mandarin": "zh-CN",
        "zh": "zh-CN",

        "arabic": "ar",
        "russian": "ru"
    }

    if lower in aliases:
        return aliases[lower]

    for code, name in TRANSLATION_LANGUAGES.items():

        if lower == name.lower():
            return code

    return None


# =========================================================
# PDF FONTS
# =========================================================

PDF_FONTS = {}


def register_pdf_font(
    filename,
    font_name
):

    path = os.path.join(
        FONT_DIR,
        filename
    )

    if not os.path.exists(path):

        print(
            "PDF FONT NOT FOUND:",
            filename
        )

        return False

    try:

        pdfmetrics.registerFont(
            TTFont(
                font_name,
                path
            )
        )

        PDF_FONTS[font_name] = True

        print(
            "PDF FONT LOADED:",
            font_name
        )

        return True

    except Exception as e:

        print(
            "PDF FONT ERROR:",
            filename,
            repr(e)
        )

        return False


# =========================================================
# REGISTER PDF FONTS
# =========================================================

register_pdf_font(
    "NotoSans-Regular.ttf",
    "NotoSans"
)

register_pdf_font(
    "NotoSansDevanagari-Regular.ttf",
    "NotoDevanagari"
)

register_pdf_font(
    "NotoSansBengali-Regular.ttf",
    "NotoBengali"
)

register_pdf_font(
    "NotoSansGujarati-Regular.ttf",
    "NotoGujarati"
)

register_pdf_font(
    "NotoSansGurmukhi-Regular.ttf",
    "NotoGurmukhi"
)

register_pdf_font(
    "NotoSansTamil-Regular.ttf",
    "NotoTamil"
)

register_pdf_font(
    "NotoSansTelugu-Regular.ttf",
    "NotoTelugu"
)

register_pdf_font(
    "NotoSansKannada-Regular.ttf",
    "NotoKannada"
)

register_pdf_font(
    "NotoSansMalayalam-Regular.ttf",
    "NotoMalayalam"
)

register_pdf_font(
    "NotoSansOriya-Regular.ttf",
    "NotoOriya"
)

register_pdf_font(
    "NotoSansArabic-Regular.ttf",
    "NotoArabic"
)

register_pdf_font(
    "NotoSansJP-Regular.ttf",
    "NotoJapanese"
)

register_pdf_font(
    "NotoSansKR-Regular.ttf",
    "NotoKorean"
)

register_pdf_font(
    "NotoSansSC-Regular.ttf",
    "NotoChinese"
)


# =========================================================
# FONT SELECTION
# =========================================================

def font_for_character(
    char,
    previous_font=None
):

    code = ord(char)

    if previous_font:

        if unicodedata.combining(char):
            return previous_font

        if char in "\u200c\u200d\ufe0f":
            return previous_font


    if 0x0900 <= code <= 0x097F:
        return "NotoDevanagari"

    if 0x0980 <= code <= 0x09FF:
        return "NotoBengali"

    if 0x0A00 <= code <= 0x0A7F:
        return "NotoGurmukhi"

    if 0x0A80 <= code <= 0x0AFF:
        return "NotoGujarati"

    if 0x0B00 <= code <= 0x0B7F:
        return "NotoOriya"

    if 0x0B80 <= code <= 0x0BFF:
        return "NotoTamil"

    if 0x0C00 <= code <= 0x0C7F:
        return "NotoTelugu"

    if 0x0C80 <= code <= 0x0CFF:
        return "NotoKannada"

    if 0x0D00 <= code <= 0x0D7F:
        return "NotoMalayalam"

    if 0x0600 <= code <= 0x06FF:
        return "NotoArabic"

    if 0x0750 <= code <= 0x077F:
        return "NotoArabic"

    if 0x3040 <= code <= 0x309F:
        return "NotoJapanese"

    if 0x30A0 <= code <= 0x30FF:
        return "NotoJapanese"

    if 0x3400 <= code <= 0x4DBF:
        return "NotoChinese"

    if 0x4E00 <= code <= 0x9FFF:
        return "NotoChinese"

    if 0xAC00 <= code <= 0xD7AF:
        return "NotoKorean"

    if 0x0400 <= code <= 0x04FF:

        if "NotoSans" in PDF_FONTS:
            return "NotoSans"

    if "NotoSans" in PDF_FONTS:
        return "NotoSans"

    return "Helvetica"


# =========================================================
# VALIDATE PDF FONTS
# =========================================================

def validate_pdf_fonts(text):

    missing = set()

    previous_font = None

    for char in text:

        if char.isspace():
            continue

        font = font_for_character(
            char,
            previous_font
        )

        if font not in PDF_FONTS:

            if (
                font == "Helvetica"
                and ord(char) < 128
            ):

                previous_font = font
                continue

            missing.add(font)

        previous_font = font


    if missing:

        raise Exception(
            "Required PDF font is missing: "
            + ", ".join(
                sorted(missing)
            )
            + ". Put the required Noto font "
              "file inside the fonts folder."
        )


# =========================================================
# PDF RICH TEXT
# =========================================================

def make_rich_pdf_text(text):

    result = []

    current_font = None

    buffer = []


    def flush():

        nonlocal buffer

        if not buffer:
            return

        content = html.escape(
            "".join(buffer)
        )

        if current_font:

            result.append(
                f'<font name="{current_font}">'
                f'{content}'
                f'</font>'
            )

        else:

            result.append(
                content
            )

        buffer = []


    for char in text:

        font = font_for_character(
            char,
            current_font
        )

        if current_font is None:
            current_font = font

        if font != current_font:

            flush()

            current_font = font

        buffer.append(char)


    flush()

    return "".join(result)


# =========================================================
# ADD PDF TEXT
# =========================================================

def add_pdf_text(
    story,
    text,
    body_style
):

    validate_pdf_fonts(
        text
    )

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        rich_text = make_rich_pdf_text(
            line
        )

        story.append(
            Paragraph(
                rich_text,
                body_style
            )
        )

        story.append(
            Spacer(1, 6)
        )


# =========================================================
# GET YOUTUBE VIDEO ID
# =========================================================

def get_video_id(url):

    if not url:
        return None

    url = str(url).strip()

    patterns = [

        r"(?:v=)([A-Za-z0-9_-]{11})",

        r"(?:youtu\.be/)"
        r"([A-Za-z0-9_-]{11})",

        r"(?:youtube\.com/shorts/)"
        r"([A-Za-z0-9_-]{11})",

        r"(?:youtube\.com/live/)"
        r"([A-Za-z0-9_-]{11})"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            url
        )

        if match:
            return match.group(1)

    return None


# =========================================================
# FRIENDLY YOUTUBE ERROR
# =========================================================

def youtube_error_message(error):

    if isinstance(
        error,
        TranscriptsDisabled
    ):

        return (
            "Captions are disabled for this YouTube video."
        )


    if isinstance(
        error,
        NoTranscriptFound
    ):

        return (
            "No YouTube transcript/captions were found "
            "for this video."
        )


    if isinstance(
        error,
        VideoUnavailable
    ):

        return (
            "This YouTube video is unavailable, private, "
            "or cannot be accessed."
        )


    if isinstance(
        error,
        RequestBlocked
    ):

        return (
            "YouTube blocked the request from this server. "
            "A working proxy may be required on Render."
        )


    if isinstance(
        error,
        IpBlocked
    ):

        return (
            "YouTube blocked the server IP. "
            "A working proxy may be required on Render."
        )


    if isinstance(
        error,
        CouldNotRetrieveTranscript
    ):

        return (
            "YouTube captions could not be retrieved."
        )


    return (
        "Could not retrieve YouTube captions."
    )


# =========================================================
# AI TRANSCRIPT
# =========================================================

def ai_transcribe_youtube(video_id):

    if yt_dlp is None:

        raise RuntimeError(
            "yt-dlp is not installed. "
            "Run: pip install yt-dlp"
        )


    if OpenAI is None:

        raise RuntimeError(
            "OpenAI package is not installed. "
            "Run: pip install openai"
        )


    api_key = os.getenv(
        "OPENAI_API_KEY",
        ""
    ).strip()


    if not api_key:

        raise RuntimeError(
            "OPENAI_API_KEY is missing. "
            "Add it to your .env file."
        )


    video_url = (
        "https://www.youtube.com/watch?v="
        + video_id
    )


    temp_dir = tempfile.mkdtemp(
        prefix="anislcript_"
    )


    audio_template = os.path.join(
        temp_dir,
        "audio.%(ext)s"
    )


    ydl_opts = {

        "format":
            "bestaudio/best",

        "outtmpl":
            audio_template,

        "noplaylist":
            True,

        "quiet":
            True,

        "no_warnings":
            True,

        "postprocessors": [

            {
                "key":
                    "FFmpegExtractAudio",

                "preferredcodec":
                    "mp3",

                "preferredquality":
                    "64"
            }

        ]
    }


    try:

        print(
            "AI FALLBACK: Starting audio extraction..."
        )

        with yt_dlp.YoutubeDL(
            ydl_opts
        ) as ydl:

            info = ydl.extract_info(
                video_url,
                download=True
            )


        audio_file = os.path.join(
            temp_dir,
            "audio.mp3"
        )


        if not os.path.exists(
            audio_file
        ):

            raise RuntimeError(
                "Audio extraction failed. "
                "Please make sure FFmpeg is installed "
                "and available in PATH."
            )


        print(
            "AI FALLBACK: Audio downloaded."
        )

        print(
            "AI FALLBACK: Sending audio to AI..."
        )


        client = OpenAI(
            api_key=api_key
        )


        with open(
            audio_file,
            "rb"
        ) as audio:

            result = (
                client.audio.transcriptions.create(

                    model=OPENAI_TRANSCRIBE_MODEL,

                    file=audio

                )
            )


        text = str(
            getattr(
                result,
                "text",
                ""
            )
        ).strip()


        if not text:

            raise RuntimeError(
                "AI could not detect speech "
                "in this video."
            )


        print(
            "AI FALLBACK: Transcription completed."
        )


        return {

            "text":
                text,

            "title":
                info.get(
                    "title",
                    "YouTube Video"
                ),

            "source":
                "AI Speech-to-Text"

        }


    except Exception as e:

        print(
            "AI TRANSCRIPTION ERROR:",
            repr(e)
        )

        raise RuntimeError(
            "AI transcription failed: "
            + str(e)
        )


    finally:

        try:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )

        except Exception:
            pass


# =========================================================
# GET AVAILABLE TRANSCRIPTS
# =========================================================

def get_available_tracks(video_id):

    try:

        api = create_youtube_api()

        transcript_list = api.list(
            video_id
        )

        tracks = []

        for transcript in transcript_list:

            tracks.append({

                "language":
                    transcript.language,

                "language_code":
                    transcript.language_code,

                "is_generated":
                    bool(
                        transcript.is_generated
                    ),

                "is_translatable":
                    bool(
                        transcript.is_translatable
                    )

            })


        return tracks


    except (
        TranscriptsDisabled,
        NoTranscriptFound
    ) as e:

        print(
            "CAPTIONS UNAVAILABLE:",
            repr(e)
        )

        # -------------------------------------------------
        # AI FALLBACK TRACK
        # -------------------------------------------------

        return [

            {

                "language":
                    "🤖 AI Transcript",

                "language_code":
                    "ai",

                "is_generated":
                    True,

                "is_translatable":
                    True

            }

        ]


    except Exception as e:

        print(
            "GET TRACKS ERROR:",
            repr(e)
        )

        raise RuntimeError(
            youtube_error_message(e)
        )


# =========================================================
# FETCH TRANSCRIPT
# =========================================================

def fetch_transcript(
    video_id,
    language_code
):

    # =====================================================
    # AI FALLBACK
    # =====================================================

    if language_code == "ai":

        print(
            "AI FALLBACK SELECTED"
        )

        result = ai_transcribe_youtube(
            video_id
        )

        return (

            result["text"],

            "AI Transcript",

            "ai"

        )


    # =====================================================
    # NORMAL YOUTUBE CAPTIONS
    # =====================================================

    try:

        api = create_youtube_api()

        transcript_list = api.list(
            video_id
        )

        selected = None

        for transcript in transcript_list:

            if (
                transcript.language_code
                == language_code
            ):

                selected = transcript
                break


        if selected is None:

            raise RuntimeError(
                f"Transcript language "
                f"'{language_code}' "
                "is not available for this video."
            )


        fetched = selected.fetch()

        text_parts = []


        for item in fetched:

            if hasattr(
                item,
                "text"
            ):

                text_parts.append(
                    item.text
                )

            elif isinstance(
                item,
                dict
            ):

                text_parts.append(
                    item.get(
                        "text",
                        ""
                    )
                )


        text = "\n".join(
            text_parts
        ).strip()


        if not text:

            raise RuntimeError(
                "Transcript was found but contains no text."
            )


        return (

            text,

            selected.language,

            selected.language_code

        )


    except RuntimeError:

        raise


    except Exception as e:

        print(
            "FETCH TRANSCRIPT ERROR:",
            repr(e)
        )

        raise RuntimeError(
            youtube_error_message(e)
        )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# =========================================================
# LANGUAGES API
# =========================================================

@app.route(
    "/languages",
    methods=["POST"]
)
def languages():

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        url = str(
            data.get(
                "url",
                ""
            )
        ).strip()


        if not url:

            return jsonify({

                "success": False,

                "message":
                    "Please enter a YouTube URL."

            }), 400


        video_id = get_video_id(
            url
        )


        if not video_id:

            return jsonify({

                "success": False,

                "message":
                    "Invalid YouTube URL."

            }), 400


        tracks = get_available_tracks(
            video_id
        )


        if not tracks:

            return jsonify({

                "success": False,

                "message":
                    "No transcript languages are available for this video."

            }), 404


        return jsonify({

            "success": True,

            "languages": tracks,

            "ai_fallback":
                any(
                    track.get(
                        "language_code"
                    ) == "ai"
                    for track in tracks
                )

        }), 200


    except RuntimeError as e:

        print(
            "LANGUAGE ERROR:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "message":
                str(e)

        }), 400


    except Exception as e:

        print(
            "UNEXPECTED LANGUAGE ERROR:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to check YouTube captions right now."

        }), 500


# =========================================================
# TRANSCRIPT API
# =========================================================

@app.route(
    "/transcript",
    methods=["POST"]
)
def transcript():

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        url = str(
            data.get(
                "url",
                ""
            )
        ).strip()


        language_code = str(
            data.get(
                "language_code",
                ""
            )
        ).strip()


        if not url:

            return jsonify({

                "success": False,

                "message":
                    "Please enter a YouTube URL."

            }), 400


        if not language_code:

            return jsonify({

                "success": False,

                "message":
                    "Please select a transcript language."

            }), 400


        video_id = get_video_id(
            url
        )


        if not video_id:

            return jsonify({

                "success": False,

                "message":
                    "Invalid YouTube URL."

            }), 400


        (
            text,
            language,
            actual_language_code
        ) = fetch_transcript(

            video_id,

            language_code

        )


        return jsonify({

            "success": True,

            "language":
                language,

            "language_code":
                actual_language_code,

            "source":
                (
                    "AI Speech-to-Text"
                    if actual_language_code == "ai"
                    else "YouTube Captions"
                ),

            "text":
                text

        }), 200


    except RuntimeError as e:

        print(
            "TRANSCRIPT ERROR:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "message":
                str(e)

        }), 400


    except Exception as e:

        print(
            "UNEXPECTED TRANSCRIPT ERROR:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to retrieve transcript right now."

        }), 500


# =========================================================
# SOURCE LANGUAGE DETECTION
# =========================================================

def detect_source_language(text):

    checks = [

        ("hi", 0x0900, 0x097F),
        ("bn", 0x0980, 0x09FF),
        ("pa", 0x0A00, 0x0A7F),
        ("gu", 0x0A80, 0x0AFF),
        ("or", 0x0B00, 0x0B7F),
        ("ta", 0x0B80, 0x0BFF),
        ("te", 0x0C00, 0x0C7F),
        ("kn", 0x0C80, 0x0CFF),
        ("ml", 0x0D00, 0x0D7F)

    ]


    for language, start, end in checks:

        count = sum(

            1

            for char in text

            if (
                start
                <= ord(char)
                <= end
            )

        )

        if count >= 3:
            return language


    arabic_count = sum(

        1

        for char in text

        if (
            0x0600
            <= ord(char)
            <= 0x06FF
        )

    )


    if arabic_count >= 3:
        return "ar"


    return "en"


# =========================================================
# SPLIT TEXT
# =========================================================

def split_text(
    text,
    max_chars=450
):

    lines = text.splitlines()

    chunks = []

    current = ""


    for line in lines:

        line = line.strip()

        if not line:
            continue


        if len(line) > max_chars:

            if current:

                chunks.append(
                    current
                )

                current = ""


            for start in range(
                0,
                len(line),
                max_chars
            ):

                chunks.append(
                    line[
                        start:
                        start + max_chars
                    ]
                )

            continue


        if (
            len(current)
            + len(line)
            + 1
            <= max_chars
        ):

            if current:
                current += "\n"

            current += line

        else:

            if current:

                chunks.append(
                    current
                )

            current = line


    if current:

        chunks.append(
            current
        )


    return chunks


# =========================================================
# MYMEMORY
# =========================================================

def translate_chunk(
    chunk,
    source_language,
    target_language
):

    api_url = (
        "https://api.mymemory.translated.net/get"
    )


    params = {

        "q": chunk,

        "langpair":
            f"{source_language}|"
            f"{target_language}"

    }


    headers = {

        "User-Agent":
            "AniScript-Pro/1.0"

    }


    last_error = ""


    for attempt in range(3):

        try:

            response = requests.get(

                api_url,

                params=params,

                headers=headers,

                timeout=30

            )


            response.raise_for_status()


            data = response.json()


            status = data.get(
                "responseStatus"
            )


            if str(status) == "200":

                translated = (

                    data
                    .get(
                        "responseData",
                        {}
                    )
                    .get(
                        "translatedText",
                        ""
                    )
                )


                if translated:

                    return html.unescape(
                        translated
                    )


            last_error = str(
                data
            )


        except Exception as e:

            last_error = str(e)


        if attempt < 2:

            time.sleep(2)


    raise Exception(

        "Translation service is temporarily "
        "unavailable. "
        + last_error

    )


# =========================================================
# TRANSLATE COMPLETE TEXT
# =========================================================

def translate_text(
    text,
    target_language,
    source_language=None
):

    if not text.strip():

        raise Exception(
            "Transcript is empty."
        )


    target_language = normalize_language(
        target_language
    )


    if not target_language:

        raise Exception(
            "Invalid translation language."
        )


    if source_language:

        source_language = normalize_language(
            source_language
        )


    if not source_language:

        source_language = detect_source_language(
            text
        )


    print(
        "TRANSLATION SOURCE:",
        source_language
    )

    print(
        "TRANSLATION TARGET:",
        target_language
    )


    if (
        source_language
        == target_language
    ):

        return text


    chunks = split_text(
        text,
        450
    )


    if not chunks:

        raise Exception(
            "Transcript could not be split for translation."
        )


    translated_chunks = []


    for index, chunk in enumerate(
        chunks
    ):

        print(
            f"Translating chunk "
            f"{index + 1}/"
            f"{len(chunks)}..."
        )


        translated = translate_chunk(

            chunk,

            source_language,

            target_language

        )


        translated_chunks.append(
            translated
        )


        if index < len(chunks) - 1:

            time.sleep(1)


    return "\n\n".join(
        translated_chunks
    )


# =========================================================
# TRANSLATION API
# =========================================================

@app.route(
    "/translate",
    methods=["POST"]
)
def translate():

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        text = str(
            data.get(
                "text",
                ""
            )
        ).strip()


        target_language = normalize_language(
            data.get(
                "target_language",
                ""
            )
        )


        source_language = normalize_language(
            data.get(
                "source_language",
                ""
            )
        )


        if not text:

            return jsonify({

                "success": False,

                "message":
                    "Transcript is empty."

            }), 400


        if not target_language:

            return jsonify({

                "success": False,

                "message":
                    "Invalid translation language."

            }), 400


        translated = translate_text(

            text,

            target_language,

            source_language

        )


        return jsonify({

            "success": True,

            "language":
                TRANSLATION_LANGUAGES[
                    target_language
                ],

            "language_code":
                target_language,

            "source_language_code":
                source_language,

            "text":
                translated,

            "translated_text":
                translated

        }), 200


    except Exception as e:

        print(
            "TRANSLATION ERROR:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "message":
                str(e)

        }), 500


# =========================================================
# PDF DOWNLOAD
# =========================================================

@app.route(
    "/download-pdf",
    methods=["POST"]
)
def download_pdf():

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        original_text = str(
            data.get(
                "original_text",
                ""
            )
        ).strip()


        translated_text = str(
            data.get(
                "translated_text",
                ""
            )
        ).strip()


        source_language = normalize_language(
            data.get(
                "source_language",
                ""
            )
        )


        target_language = normalize_language(
            data.get(
                "target_language",
                ""
            )
        )


        if (
            not original_text
            and not translated_text
        ):

            old_text = str(
                data.get(
                    "text",
                    ""
                )
            ).strip()


            if old_text:
                original_text = old_text


        if (
            not original_text
            and not translated_text
        ):

            return jsonify({

                "success": False,

                "message":
                    "Transcript is empty."

            }), 400


        if (
            translated_text
            and not target_language
        ):

            target_language = "en"


        if (
            original_text
            and not source_language
        ):

            source_language = detect_source_language(
                original_text
            )


        if original_text:

            validate_pdf_fonts(
                original_text
            )


        if translated_text:

            validate_pdf_fonts(
                translated_text
            )


        if translated_text:

            language_name = (
                TRANSLATION_LANGUAGES.get(
                    target_language,
                    "Translation"
                )
            )

        else:

            language_name = "Original"


        safe_language_name = re.sub(

            r"[^A-Za-z0-9_-]+",

            "_",

            language_name

        )


        pdf_filename = (
            f"AniScript_"
            f"{safe_language_name}.pdf"
        )


        pdf_path = os.path.join(

            tempfile.gettempdir(),

            pdf_filename

        )


        document = SimpleDocTemplate(

            pdf_path,

            pagesize=A4,

            rightMargin=40,

            leftMargin=40,

            topMargin=40,

            bottomMargin=40

        )


        styles = getSampleStyleSheet()


        base_font = (

            "NotoSans"

            if "NotoSans"
            in PDF_FONTS

            else "Helvetica"

        )


        title_style = ParagraphStyle(

            "AniScriptTitle",

            parent=styles["Title"],

            fontName=base_font,

            fontSize=22,

            leading=28,

            alignment=TA_LEFT,

            spaceAfter=10

        )


        heading_style = ParagraphStyle(

            "AniScriptHeading",

            parent=styles["Heading2"],

            fontName=base_font,

            fontSize=15,

            leading=20,

            alignment=TA_LEFT,

            spaceAfter=10

        )


        body_style = ParagraphStyle(

            "AniScriptBody",

            parent=styles["BodyText"],

            fontName=base_font,

            fontSize=10,

            leading=17,

            alignment=TA_LEFT,

            spaceAfter=4

        )


        story = []


        story.append(

            Paragraph(

                "AniScript Pro",

                title_style

            )

        )


        story.append(
            Spacer(1, 5)
        )


        story.append(

            Paragraph(

                "YouTube Transcript",

                heading_style

            )

        )


        story.append(
            Spacer(1, 15)
        )


        if original_text:

            if source_language == "ai":

                original_name = "AI Speech-to-Text"

            else:

                original_name = (

                    TRANSLATION_LANGUAGES.get(

                        source_language,

                        source_language
                        or "Original"

                    )
                )


            story.append(

                Paragraph(

                    "Original Transcript "
                    f"({html.escape(original_name)})",

                    heading_style

                )

            )


            story.append(
                Spacer(1, 5)
            )


            add_pdf_text(

                story,

                original_text,

                body_style

            )


        if translated_text:

            story.append(
                Spacer(1, 15)
            )


            target_name = (

                TRANSLATION_LANGUAGES.get(

                    target_language,

                    target_language
                    or "Translation"

                )

            )


            story.append(

                Paragraph(

                    "Translated Transcript "
                    f"({html.escape(target_name)})",

                    heading_style

                )

            )


            story.append(
                Spacer(1, 5)
            )


            add_pdf_text(

                story,

                translated_text,

                body_style

            )


        document.build(
            story
        )


        if not os.path.exists(
            pdf_path
        ):

            raise Exception(
                "PDF file was not created."
            )


        file_size = os.path.getsize(
            pdf_path
        )


        if file_size <= 0:

            raise Exception(
                "Generated PDF is empty."
            )


        print(
            "PDF CREATED:",
            pdf_path
        )

        print(
            "PDF SIZE:",
            file_size,
            "bytes"
        )


        return send_file(

            pdf_path,

            as_attachment=True,

            download_name=pdf_filename,

            mimetype="application/pdf"

        )


    except Exception as e:

        print(
            "PDF ERROR:",
            repr(e)
        )


        return jsonify({

            "success": False,

            "message":
                "PDF generation failed: "
                + str(e)

        }), 500


# =========================================================
# HEALTH
# =========================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status": "ok",

        "service":
            "AniScript Pro",

        "ai_transcript":
            bool(
                OPENAI_API_KEY
            )

    })


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )


    app.run(

        host="0.0.0.0",

        port=port,

        debug=False,

        use_reloader=False

    )