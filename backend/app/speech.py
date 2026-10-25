"""Spoken commentary with Azure AI Speech neural voices (text-to-speech REST API).

English uses a Dragon HD voice (natural pacing and emotion inferred from the text, so it needs
no prosody tweaks); other languages use the locale's neural commentator voice, lifted slightly
for goals and big moments. Results are cached, since the same line is often requested more than once.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from xml.sax.saxutils import escape

import httpx

VOICES = {
    "en": ("en-GB", "en-GB-Ollie:DragonHDLatestNeural"),
    "tr": ("tr-TR", "tr-TR-AhmetNeural"),
    "es": ("es-ES", "es-ES-AlvaroNeural"),
    "fr": ("fr-FR", "fr-FR-HenriNeural"),
    "de": ("de-DE", "de-DE-ConradNeural"),
    "pt": ("pt-BR", "pt-BR-AntonioNeural"),
    "ar": ("ar-SA", "ar-SA-HamedNeural"),
}
EXCITED_KINDS = {"goal", "big_chance", "forecast_on_target", "rocket_shot"}
MAX_CHARS = 600
CACHE_SIZE = 300


class Speech:
    def __init__(self, key: str, region: str):
        self.url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self.headers = {
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "insidethegame",
        }
        self._client = httpx.AsyncClient(timeout=15.0)
        self._cache: OrderedDict[tuple[str, str, bool], bytes] = OrderedDict()

    @staticmethod
    def ssml(text: str, lang: str, excited: bool) -> str:
        locale, voice = VOICES.get(lang, VOICES["en"])
        body = escape(text.strip()[:MAX_CHARS])
        if "DragonHD" in voice:  # HD voices pick tone and pace from the text itself
            return f"<speak version='1.0' xml:lang='{locale}'><voice name='{voice}'>{body}</voice></speak>"
        rate, pitch = ("+6%", "+4%") if excited else ("+0%", "+0%")
        return (f"<speak version='1.0' xml:lang='{locale}'><voice name='{voice}'>"
                f"<prosody rate='{rate}' pitch='{pitch}'>{body}</prosody></voice></speak>")

    async def synthesize(self, text: str, lang: str = "en", kind: str | None = None) -> bytes:
        excited = kind in EXCITED_KINDS
        key = (text, lang, excited)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        resp = await self._client.post(self.url, headers=self.headers, content=self.ssml(text, lang, excited).encode("utf-8"))
        resp.raise_for_status()
        audio = resp.content
        self._cache[key] = audio
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return audio


def get_speech() -> Speech | None:
    key, region = os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION")
    return Speech(key, region) if key and region else None
