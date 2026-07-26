"""Deterministic simulated voice-to-monitoring composition."""

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from tomato_sentinel_device_protocol import DeviceMessageVerifier

from .models import ExecutionContext
from .monitoring_models import MonitoringOutcome
from .monitoring_service import MonitoringService

MAXIMUM_TRANSCRIPTION_BYTES = 4_096


class VoiceCommandRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class SpeechToTextAdapter(Protocol):
    def transcribe(
        self,
        audio: bytes,
        *,
        capture_id: str,
        created_at: datetime,
    ) -> Mapping[str, object]:
        """Return untrusted normalized transcription data."""


@dataclass(frozen=True, slots=True)
class ValidatedTranscription:
    transcription_id: str
    text: str
    audio_sha256: str


@dataclass(frozen=True, slots=True)
class ProposedVoiceIntent:
    action: str
    target_alias: str
    duration_seconds: int


class TranscriptionContractValidator:
    def __init__(self, schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    def validate(
        self,
        payload: Mapping[str, object],
        *,
        expected_audio_sha256: str,
    ) -> ValidatedTranscription:
        try:
            encoded = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError) as error:
            raise VoiceCommandRejectedError("TRANSCRIPTION_NOT_JSON") from error
        if len(encoded) > MAXIMUM_TRANSCRIPTION_BYTES:
            raise VoiceCommandRejectedError("TRANSCRIPTION_TOO_LARGE")
        try:
            self._validator.validate(payload)
        except ValidationError as error:
            raise VoiceCommandRejectedError("TRANSCRIPTION_SCHEMA_INVALID") from error
        if payload["audio_sha256"] != expected_audio_sha256:
            raise VoiceCommandRejectedError("TRANSCRIPTION_AUDIO_MISMATCH")
        return ValidatedTranscription(
            transcription_id=cast(str, payload["transcription_id"]),
            text=cast(str, payload["text"]),
            audio_sha256=expected_audio_sha256,
        )


class FixtureSpeechToText:
    """Exact audio-digest fixture; it performs no inference or network I/O."""

    def __init__(self, transcripts_by_audio_sha256: Mapping[str, str]) -> None:
        for digest, transcript in transcripts_by_audio_sha256.items():
            if re.fullmatch(r"sha256:[a-f0-9]{64}", digest) is None:
                raise ValueError("fixture audio digest is invalid")
            if not transcript or len(transcript) > 512:
                raise ValueError("fixture transcript is invalid")
        self._transcripts = dict(transcripts_by_audio_sha256)
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    def transcribe(
        self,
        audio: bytes,
        *,
        capture_id: str,
        created_at: datetime,
    ) -> Mapping[str, object]:
        self._calls += 1
        digest = _audio_digest(audio)
        transcript = self._transcripts.get(digest)
        if transcript is None:
            raise VoiceCommandRejectedError("AUDIO_FIXTURE_UNKNOWN")
        return {
            "contract_version": 1,
            "transcription_id": f"transcription:{digest[7:31]}",
            "provider_id": "speech-provider:fixture-v1",
            "execution_mode": "simulated",
            "language": "pt-BR",
            "text": transcript,
            "audio_sha256": digest,
            "created_at": _timestamp(created_at),
        }


class ExactVoiceIntentExtractor:
    """Maps an exact reviewed transcript to a bounded proposed intent."""

    def __init__(
        self, intents_by_transcript: Mapping[str, ProposedVoiceIntent]
    ) -> None:
        for transcript, intent in intents_by_transcript.items():
            if not transcript or len(transcript) > 512:
                raise ValueError("intent transcript is invalid")
            if intent.action != "camera.monitor":
                raise ValueError("fixture intent action is not supported")
            if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", intent.target_alias) is None:
                raise ValueError("fixture target alias is invalid")
            if not 1 <= intent.duration_seconds <= 300:
                raise ValueError("fixture duration is outside tool limits")
        self._intents = dict(intents_by_transcript)

    def extract(self, transcription: ValidatedTranscription) -> ProposedVoiceIntent:
        intent = self._intents.get(transcription.text)
        if intent is None:
            raise VoiceCommandRejectedError("TRANSCRIPT_NOT_REGISTERED")
        return intent


class CameraAliasResolver:
    """Resolves reviewed organization-local aliases to canonical camera IDs."""

    def __init__(self, aliases: Mapping[tuple[str, str], str]) -> None:
        for (organization_id, alias), camera_id in aliases.items():
            if not organization_id.startswith("org:"):
                raise ValueError("camera alias organization is invalid")
            if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", alias) is None:
                raise ValueError("camera alias is invalid")
            if not camera_id.startswith("camera:"):
                raise ValueError("camera alias target is invalid")
        self._aliases = dict(aliases)

    def resolve(self, organization_id: str, alias: str) -> str:
        camera_id = self._aliases.get((organization_id, alias))
        if camera_id is None:
            raise VoiceCommandRejectedError("TARGET_ALIAS_NOT_REGISTERED")
        return camera_id


class VoiceMonitoringGateway:
    def __init__(
        self,
        *,
        verifier: DeviceMessageVerifier,
        speech: SpeechToTextAdapter,
        transcription_validator: TranscriptionContractValidator,
        intent_extractor: ExactVoiceIntentExtractor,
        aliases: CameraAliasResolver,
    ) -> None:
        self._verifier = verifier
        self._speech = speech
        self._transcription_validator = transcription_validator
        self._intent_extractor = intent_extractor
        self._aliases = aliases

    def handle(
        self,
        envelope: Mapping[str, object],
        context: ExecutionContext,
        monitoring: MonitoringService,
        *,
        received_at: datetime,
    ) -> MonitoringOutcome:
        message = self._verifier.verify(envelope, received_at=received_at)
        if message.payload_type != "voice_command":
            raise VoiceCommandRejectedError("VOICE_MESSAGE_REQUIRED")
        if message.device_id != context.device.device_id:
            raise VoiceCommandRejectedError("VOICE_DEVICE_CONTEXT_MISMATCH")
        if message.payload["active_profile"] != "sentinel":
            raise VoiceCommandRejectedError("SENTINEL_PROFILE_REQUIRED")

        audio_payload = cast(Mapping[str, object], message.payload["audio"])
        audio = base64.b64decode(
            cast(str, audio_payload["content_base64"]),
            validate=True,
        )
        audio_digest = _audio_digest(audio)
        transcription_payload = self._speech.transcribe(
            audio,
            capture_id=cast(str, message.payload["capture_id"]),
            created_at=received_at,
        )
        transcription = self._transcription_validator.validate(
            transcription_payload,
            expected_audio_sha256=audio_digest,
        )
        intent = self._intent_extractor.extract(transcription)
        target = self._aliases.resolve(
            context.actor.organization_id,
            intent.target_alias,
        )
        command = {
            "contract_version": 1,
            "command_id": _command_id(cast(str, message.payload["capture_id"])),
            "actor_id": context.actor.actor_id,
            "organization_id": context.actor.organization_id,
            "source_device_id": context.device.device_id,
            "profile": "sentinel",
            "action": intent.action,
            "targets": [target],
            "parameters": {"duration_seconds": intent.duration_seconds},
            "requested_at": _timestamp(message.sent_at),
            "correlation_id": message.correlation_id,
        }
        return monitoring.start(command, context, evaluated_at=received_at)


def _audio_digest(audio: bytes) -> str:
    return f"sha256:{hashlib.sha256(audio).hexdigest()}"


def _command_id(capture_id: str) -> str:
    return f"command:{capture_id.removeprefix('capture:')}"


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
