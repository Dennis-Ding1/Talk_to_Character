"""Thin async wrapper over the Boson Higgs REST APIs.

Docs: https://docs.boson.ai/llms.txt
- Realtime client secrets: POST /v1/realtime/client_secrets
- TTS / voice cloning:     POST /v1/audio/speech, POST /v1/audio/voices
- Avatar:                  POST /v1/videos, POST /v1/videos/stream (fragmented MP4)
"""

from collections.abc import AsyncIterator

import httpx

from app.config import get_settings

REALTIME_URL = "wss://api.boson.ai/v1/realtime"
REALTIME_MODEL = "higgs-realtime"
STT_MODEL = "higgs-stt-3.1"
TTS_MODEL = "higgs-tts-3"
AVATAR_MODEL = "higgs-avatar"


class BosonError(RuntimeError):
    pass


class BosonClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.boson_api_key
        self.base_url = (base_url or s.boson_base_url).rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _client(self, timeout: float = 60) -> httpx.AsyncClient:
        if not self.enabled:
            raise BosonError("BOSON_API_KEY is not set (see .env.example)")
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=timeout,
        )

    @staticmethod
    def _check(r: httpx.Response) -> dict:
        if r.is_error:
            raise BosonError(f"{r.status_code} {r.request.url.path}: {r.text[:500]}")
        return r.json()

    # ---------- Realtime ----------

    async def create_client_secret(self, ttl_s: int = 600) -> str:
        """Short-lived key for the browser to open the Realtime WebSocket directly."""
        async with self._client() as c:
            r = await c.post(
                "/realtime/client_secrets",
                json={"expires_after": {"seconds": ttl_s}},
            )
            data = self._check(r)
        return data["value"]  # "bai-eph-..."

    # ---------- Voices (cloning) ----------

    async def create_voice(self, ref_audio_b64: str, ref_text: str | None, title: str) -> str:
        """Register a reusable cloned voice. Same audio -> same voice_id (idempotent)."""
        body = {"ref_audio": ref_audio_b64, "title": title}
        if ref_text:
            body["ref_text"] = ref_text
        async with self._client() as c:
            data = self._check(await c.post("/audio/voices", json=body))
        return data["voice_id"]

    async def list_voices(self) -> list[dict]:
        async with self._client() as c:
            data = self._check(await c.get("/audio/voices"))
        return data.get("data", data if isinstance(data, list) else [])

    # ---------- TTS ----------

    async def speech(self, text: str, voice: str, response_format: str = "wav") -> bytes:
        async with self._client() as c:
            r = await c.post(
                "/audio/speech",
                json={
                    "model": TTS_MODEL,
                    "input": text,
                    "voice": voice,
                    "response_format": response_format,
                },
            )
            if r.is_error:
                raise BosonError(f"{r.status_code}: {r.text[:500]}")
            return r.content

    # ---------- Avatar ----------

    @staticmethod
    def avatar_body(
        ref_image: str,
        *,
        audio: str | None = None,
        text: str | None = None,
        voice: str | None = None,
        size: str = "640x640",
    ) -> dict:
        """ref_image/audio may be an https URL or a data URI. Exactly one of audio/text."""
        if (audio is None) == (text is None):
            raise ValueError("pass exactly one of audio or text")
        body: dict = {"model": AVATAR_MODEL, "ref_image": ref_image, "size": size}
        if audio is not None:
            body["input"] = audio
        else:
            body["input_tts"] = {"model": TTS_MODEL, "input": text, "voice": voice or "default"}
        return body

    async def avatar_stream(self, body: dict) -> AsyncIterator[bytes]:
        """Yields fragmented-MP4 chunks as they are generated (play with MSE in the browser)."""
        async with self._client(timeout=300) as c:
            async with c.stream("POST", "/videos/stream", json=body) as r:
                if r.is_error:
                    await r.aread()
                    raise BosonError(f"{r.status_code}: {r.text[:500]}")
                async for chunk in r.aiter_bytes():
                    yield chunk
