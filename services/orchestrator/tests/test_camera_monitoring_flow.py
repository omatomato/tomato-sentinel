import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from tomato_sentinel_device_protocol import (
    CardputerSimulator,
    DeviceMessageRejectedError,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    ProvisionedDevice,
    PushToTalkRecorder,
    load_board_profile,
)
from tomato_sentinel_orchestrator import (
    CameraAliasResolver,
    CameraRecord,
    CameraState,
    CommandRejectedError,
    ContractValidator,
    DeviceCancelGateway,
    ExactVoiceIntentExtractor,
    ExecutionContext,
    ExecutionStatus,
    FixtureSpeechToText,
    FrameObservation,
    InMemoryAuditSink,
    InMemoryCameraRepository,
    InMemoryEventSink,
    InMemoryFrameSource,
    InMemoryNotificationSink,
    InvalidTransitionError,
    JobState,
    MonitoringJob,
    MonitoringService,
    NotificationChannel,
    ProposedVoiceIntent,
    TranscriptionContractValidator,
    VoiceCommandRejectedError,
    VoiceMonitoringGateway,
    audit_to_contract,
    camera_monitor_manifest,
    monitoring_outcome_to_contract,
    notification_to_contract,
    person_event_to_contract,
    transition_to_contract,
)
from tomato_sentinel_orchestrator.monitoring_service import (
    MAXIMUM_EVENTS,
    MAXIMUM_FRAMES,
)
from tomato_sentinel_policy import (
    ActorContext,
    DeviceContext,
    Profile,
    ResourceGrant,
    ToolRegistry,
    TrustState,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
NOW = datetime(2026, 7, 25, 18, 40, tzinfo=UTC)
VOICE_AUDIO = b"reviewed-simulated-opus-garage-two-minutes"
VOICE_TRANSCRIPT = "Monitore a câmera da garagem por dois minutos."
DEVICE_SECRET = b"simulation-device-key-material-32-bytes"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def command(
    *,
    command_id: str = "command:monitor-01",
    action: str = "camera.monitor",
    target: str = "camera:garage-01",
    parameters: dict[str, object] | None = None,
    profile: str = "sentinel",
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "command_id": command_id,
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": profile,
        "action": action,
        "targets": [target],
        "parameters": ({"duration_seconds": 120} if parameters is None else parameters),
        "requested_at": "2026-07-25T18:40:00Z",
        "correlation_id": "correlation:monitor-01",
    }


def context() -> ExecutionContext:
    return ExecutionContext(
        actor=ActorContext(
            actor_id="user:01",
            organization_id="org:01",
            roles=frozenset({"operator"}),
        ),
        device=DeviceContext(
            device_id="cardputer:01",
            organization_id="org:01",
            trust_state=TrustState.TRUSTED,
            capabilities=frozenset({"camera_monitoring"}),
        ),
        resource_grant=ResourceGrant(
            organization_id="org:01",
            resource_ids=frozenset({"camera:garage-01", "camera:other-01"}),
            valid_until=NOW + timedelta(minutes=10),
        ),
    )


def recorded_frames(
    confidences: tuple[float | None, ...] = (None, 0.91, 0.90, 0.92),
) -> tuple[FrameObservation, ...]:
    return tuple(
        FrameObservation(
            frame_id=f"frame:{index}",
            observed_at=NOW + timedelta(seconds=index),
            person_confidence=confidence,
        )
        for index, confidence in enumerate(confidences, start=1)
    )


def build_service(
    frames: tuple[FrameObservation, ...] | None = None,
    *,
    camera_state: CameraState = CameraState.ONLINE,
) -> tuple[
    MonitoringService,
    InMemoryFrameSource,
    InMemoryEventSink,
    InMemoryNotificationSink,
    InMemoryNotificationSink,
    InMemoryAuditSink,
]:
    validator = ContractValidator(
        load_json(SCHEMAS / "command.schema.json"),
        (load_json(ROOT / "config" / "tools" / "camera.monitor.v1.json"),),
    )
    registry = ToolRegistry()
    registry.register(camera_monitor_manifest())
    cameras = InMemoryCameraRepository(
        (
            CameraRecord(
                camera_id="camera:garage-01",
                organization_id="org:01",
                display_name="Garage",
                status=camera_state,
                observed_at=NOW,
                credential_reference="vault:camera-garage",
                private_stream_url="rtsp://admin:secret@192.0.2.10/private",
            ),
            CameraRecord(
                camera_id="camera:other-01",
                organization_id="org:other",
                display_name="Other tenant",
                status=CameraState.ONLINE,
                observed_at=NOW,
                credential_reference="vault:other",
                private_stream_url="rtsp://other.example/private",
            ),
        )
    )
    frame_source = InMemoryFrameSource(
        {"camera:garage-01": frames if frames is not None else recorded_frames()}
    )
    events = InMemoryEventSink()
    push = InMemoryNotificationSink(NotificationChannel.FAKE_PUSH)
    inbox = InMemoryNotificationSink(NotificationChannel.CARDPUTER_INBOX)
    audit = InMemoryAuditSink()
    service = MonitoringService(
        validator=validator,
        registry=registry,
        cameras=cameras,
        frames=frame_source,
        events=events,
        push=push,
        inbox=inbox,
        audit=audit,
    )
    return service, frame_source, events, push, inbox, audit


def validate_contract(schema_name: str, instance: dict[str, object]) -> None:
    Draft202012Validator(
        load_json(SCHEMAS / schema_name),
        format_checker=FormatChecker(),
    ).validate(instance)


def test_complete_monitoring_flow_confirms_once_and_notifies_once() -> None:
    service, frames, events, push, inbox, audit = build_service()

    started = service.start(command(), context(), evaluated_at=NOW)
    completed = service.run_to_completion(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=10),
    )

    assert started.status is JobState.RUNNING
    assert completed.status is JobState.COMPLETED
    assert frames.worker_starts == 1
    assert len(events.events) == 1
    assert len(push.deliveries) == 1
    assert len(inbox.deliveries) == 1
    assert audit.events[0].result is ExecutionStatus.SIMULATED

    job = service.jobs[0]
    assert [transition.resulting_state for transition in job.transitions] == [
        JobState.CREATED,
        JobState.VALIDATED,
        JobState.AUTHORIZED,
        JobState.RUNNING,
        JobState.COMPLETED,
    ]
    event = events.events[0]
    assert event.frame_count == 3
    assert event.confidence == 0.9
    assert event.snapshot_id is None

    monitor_schema = load_json(ROOT / "config" / "tools" / "camera.monitor.v1.json")[
        "result_schema"
    ]
    Draft202012Validator(monitor_schema).validate(
        monitoring_outcome_to_contract(completed)
    )
    for transition in job.transitions:
        validate_contract(
            "job-transition.schema.json",
            transition_to_contract(transition),
        )
    validate_contract(
        "person-detected-event.schema.json",
        person_event_to_contract(event),
    )
    validate_contract(
        "notification.schema.json",
        notification_to_contract(push.deliveries[0]),
    )
    validate_contract(
        "notification.schema.json",
        notification_to_contract(inbox.deliveries[0]),
    )
    validate_contract("audit-event.schema.json", audit_to_contract(audit.events[0]))

    public_material = json.dumps(
        {
            "result": monitoring_outcome_to_contract(completed),
            "event": person_event_to_contract(event),
            "push": notification_to_contract(push.deliveries[0]),
            "inbox": notification_to_contract(inbox.deliveries[0]),
            "audit": audit_to_contract(audit.events[0]),
        }
    )
    assert "secret" not in public_material
    assert "rtsp://" not in public_material
    assert "vault:" not in public_material


def test_command_and_event_replays_create_no_duplicate_side_effects() -> None:
    service, frames, events, push, inbox, _audit = build_service()
    payload = command()

    first = service.start(payload, context(), evaluated_at=NOW)
    replay = service.start(
        payload,
        context(),
        evaluated_at=NOW + timedelta(seconds=1),
    )
    service.run_to_completion(
        first.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=10),
    )
    event = events.events[0]
    created = service.publish_event(event, "user:01")

    assert replay.job_id == first.job_id
    assert frames.worker_starts == 1
    assert created is False
    assert len(events.events) == 1
    assert len(push.deliveries) == 1
    assert len(inbox.deliveries) == 1


def test_changed_payload_cannot_reuse_monitoring_command_identifier() -> None:
    service, frames, _events, _push, _inbox, _audit = build_service()
    service.start(command(), context(), evaluated_at=NOW)

    with pytest.raises(CommandRejectedError) as error:
        service.start(
            command(parameters={"duration_seconds": 60}),
            context(),
            evaluated_at=NOW,
        )

    assert error.value.reason_code == "IDEMPOTENCY_KEY_REUSED"
    assert frames.worker_starts == 1


@pytest.mark.parametrize(
    ("changed_context", "reason_code"),
    [
        (
            replace(
                context(),
                resource_grant=replace(
                    context().resource_grant,
                    resource_ids=frozenset(),
                ),
            ),
            "TARGET_NOT_AUTHORIZED",
        ),
        (
            replace(
                context(),
                resource_grant=replace(
                    context().resource_grant,
                    valid_until=NOW,
                ),
            ),
            "GRANT_EXPIRED",
        ),
        (
            replace(
                context(),
                resource_grant=replace(
                    context().resource_grant,
                    enabled=False,
                ),
            ),
            "GRANT_DISABLED",
        ),
        (
            replace(
                context(),
                device=replace(
                    context().device,
                    trust_state=TrustState.REVOKED,
                ),
            ),
            "DEVICE_NOT_TRUSTED",
        ),
    ],
)
def test_policy_denial_starts_no_worker(
    changed_context: ExecutionContext,
    reason_code: str,
) -> None:
    service, frames, events, push, inbox, audit = build_service()

    outcome = service.start(command(), changed_context, evaluated_at=NOW)

    assert outcome.status is JobState.DENIED
    assert outcome.reason_code == reason_code
    assert outcome.job_id is None
    assert frames.worker_starts == 0
    assert service.jobs == ()
    assert events.events == ()
    assert push.deliveries == ()
    assert inbox.deliveries == ()
    assert audit.events[0].result is ExecutionStatus.DENIED


def test_cross_tenant_target_starts_no_worker_and_reveals_no_state() -> None:
    service, frames, events, push, inbox, _audit = build_service()

    outcome = service.start(
        command(target="camera:other-01"),
        context(),
        evaluated_at=NOW,
    )

    assert outcome.status is JobState.DENIED
    assert outcome.reason_code == "TARGET_NOT_ACCESSIBLE"
    assert frames.worker_starts == 0
    assert events.events == ()
    assert push.deliveries == ()
    assert inbox.deliveries == ()


@pytest.mark.parametrize(
    "payload",
    [
        command(action="camera.unknown"),
        command(parameters={"duration_seconds": 120, "shell": "whoami"}),
        {**command(), "unknown": True},
        command(parameters={"duration_seconds": 0}),
        command(parameters={"duration_seconds": 301}),
        command(parameters={"duration_seconds": True}),
        command(parameters={"padding": "x" * 17_000}),
    ],
)
def test_invalid_command_starts_no_worker(payload: dict[str, object]) -> None:
    service, frames, events, push, inbox, audit = build_service()

    with pytest.raises(CommandRejectedError):
        service.start(payload, context(), evaluated_at=NOW)

    assert frames.worker_starts == 0
    assert events.events == ()
    assert push.deliveries == ()
    assert inbox.deliveries == ()
    assert audit.events == ()


def test_cancellation_is_terminal_idempotent_and_audited() -> None:
    service, frames, events, push, inbox, audit = build_service()
    started = service.start(command(), context(), evaluated_at=NOW)
    job_id = started.job_id or ""

    service.advance(job_id, context(), evaluated_at=NOW + timedelta(seconds=1))
    cancelled = service.cancel(
        job_id,
        context(),
        evaluated_at=NOW + timedelta(seconds=2),
    )
    replay = service.cancel(
        job_id,
        context(),
        evaluated_at=NOW + timedelta(seconds=3),
    )
    after_cancel = service.advance(
        job_id,
        context(),
        evaluated_at=NOW + timedelta(seconds=4),
    )

    assert cancelled.status is JobState.CANCELLED
    assert replay == cancelled
    assert after_cancel == cancelled
    assert service.jobs[0].frames_processed == 1
    assert events.events == ()
    assert push.deliveries == ()
    assert inbox.deliveries == ()
    assert len(audit.events) == 1
    assert audit.events[0].result is ExecutionStatus.CANCELLED
    assert frames.worker_starts == 1


def test_below_threshold_and_nonconsecutive_frames_create_no_event() -> None:
    service, _frames, events, push, inbox, audit = build_service(
        recorded_frames((0.81, 0.79, 0.91, 0.92))
    )
    started = service.start(command(), context(), evaluated_at=NOW)

    outcome = service.run_to_completion(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=10),
    )

    assert outcome.status is JobState.COMPLETED
    assert events.events == ()
    assert push.deliveries == ()
    assert inbox.deliveries == ()
    assert audit.events[0].result is ExecutionStatus.SIMULATED


def test_frame_after_job_deadline_is_not_processed() -> None:
    late_frame = FrameObservation(
        frame_id="frame:late",
        observed_at=NOW + timedelta(seconds=3),
        person_confidence=0.99,
    )
    service, _frames, events, push, inbox, _audit = build_service((late_frame,))
    started = service.start(
        command(parameters={"duration_seconds": 2}),
        context(),
        evaluated_at=NOW,
    )

    outcome = service.advance(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=1),
    )

    assert outcome.status is JobState.COMPLETED
    assert service.jobs[0].frames_processed == 0
    assert events.events == ()
    assert push.deliveries == ()
    assert inbox.deliveries == ()


def test_fake_frame_buffer_rejects_more_than_manifest_limit() -> None:
    too_many = tuple(
        FrameObservation(
            frame_id=f"frame:{index}",
            observed_at=NOW + timedelta(milliseconds=index),
            person_confidence=None,
        )
        for index in range(301)
    )

    with pytest.raises(ValueError, match="exceeds 300 frames"):
        InMemoryFrameSource({"camera:garage-01": too_many})


def test_offline_camera_is_denied_before_worker_start() -> None:
    service, frames, _events, _push, _inbox, _audit = build_service(
        camera_state=CameraState.OFFLINE
    )

    outcome = service.start(command(), context(), evaluated_at=NOW)

    assert outcome.status is JobState.DENIED
    assert outcome.reason_code == "CAMERA_NOT_AVAILABLE"
    assert frames.worker_starts == 0


def test_other_actor_cannot_cancel_job() -> None:
    service, _frames, _events, _push, _inbox, _audit = build_service()
    started = service.start(command(), context(), evaluated_at=NOW)
    other = replace(
        context(),
        actor=replace(context().actor, actor_id="user:other"),
    )

    with pytest.raises(PermissionError):
        service.cancel(
            started.job_id or "",
            other,
            evaluated_at=NOW + timedelta(seconds=1),
        )

    assert service.outcome(started.job_id).status is JobState.RUNNING


def test_event_with_changed_camera_cannot_be_published() -> None:
    service, _frames, events, push, inbox, _audit = build_service()
    started = service.start(command(), context(), evaluated_at=NOW)
    service.run_to_completion(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=10),
    )
    changed = replace(events.events[0], camera_id="camera:other-01")

    with pytest.raises(ValueError, match="not bound"):
        service.publish_event(changed, "user:01")

    assert len(events.events) == 1
    assert len(push.deliveries) == 1
    assert len(inbox.deliveries) == 1


def test_invalid_state_transition_fails_explicitly() -> None:
    job = MonitoringJob(
        job_id="job:01",
        organization_id="org:01",
        actor_id="user:01",
        device_id="cardputer:01",
        camera_id="camera:garage-01",
        camera_display_name="Garage",
        duration_seconds=120,
        created_at=NOW,
        plan_hash=f"sha256:{'a' * 64}",
        correlation_id="correlation:01",
    )

    with pytest.raises(InvalidTransitionError, match="invalid transition"):
        job.transition(
            JobState.COMPLETED,
            requested_action="complete",
            actor_id="user:01",
            timestamp=NOW,
            reason="INVALID_TEST_TRANSITION",
        )


def test_monitor_domain_manifest_matches_registered_contract() -> None:
    contract = load_json(ROOT / "config" / "tools" / "camera.monitor.v1.json")
    manifest = camera_monitor_manifest()

    assert manifest.tool_id == contract["tool_id"]
    assert manifest.version == contract["version"]
    assert manifest.risk_class.value == contract["risk_class"]
    assert manifest.required_profile.value == contract["required_profile"]
    assert manifest.authorization_kind.value == contract["authorization_kind"]
    assert sorted(manifest.required_roles) == contract["required_roles"]
    assert sorted(manifest.required_capabilities) == contract["required_capabilities"]
    assert manifest.maximum_duration_seconds == contract["maximum_duration_seconds"]
    assert manifest.maximum_targets == contract["maximum_targets"]
    assert contract["resource_limits"] == {
        "maximum_frames": MAXIMUM_FRAMES,
        "maximum_events": MAXIMUM_EVENTS,
    }


def test_signed_physical_cancel_reaches_exact_running_job_once() -> None:
    service, _frames, _events, _push, _inbox, audit = build_service()
    started = service.start(command(), context(), evaluated_at=NOW)
    board_schema = load_json(SCHEMAS / "board-profile.schema.json")
    profile = load_board_profile(
        load_json(
            ROOT
            / "firmware"
            / "cardputer"
            / "board_profiles"
            / "cardputer.original.v1.json"
        ),
        board_schema,
    )
    secret = b"simulation-device-key-material-32-bytes"
    device = CardputerSimulator(
        device_id="cardputer:01",
        key_id="device-key:01",
        secret=secret,
        board_profile=profile,
        firmware_version="0.1.0-sim",
        boot_id="boot:cancel-01",
    )
    registry = DeviceRegistry()
    registry.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=profile,
            firmware_version="0.1.0-sim",
        ),
        secret,
    )
    protocol_validator = DeviceProtocolValidator(
        envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
        payload_schemas={
            "cancel_request": load_json(SCHEMAS / "cancel-request.schema.json")
        },
    )
    gateway = DeviceCancelGateway(DeviceMessageVerifier(protocol_validator, registry))
    envelope = device.physical_cancel_message(
        started.job_id or "",
        sent_at=NOW + timedelta(seconds=1),
        correlation_id="correlation:cancel-01",
    )

    cancelled = gateway.handle(
        envelope,
        context(),
        service,
        received_at=NOW + timedelta(seconds=1),
    )

    assert cancelled.status is JobState.CANCELLED
    assert audit.events[0].result is ExecutionStatus.CANCELLED
    with pytest.raises(DeviceMessageRejectedError) as error:
        gateway.handle(
            envelope,
            context(),
            service,
            received_at=NOW + timedelta(seconds=2),
        )
    assert error.value.reason_code == "MESSAGE_ID_REPLAYED"
    assert len(audit.events) == 1


def voice_fixture(
    *,
    active_profile: Profile = Profile.SENTINEL,
    audio: bytes = VOICE_AUDIO,
    transcript: str = VOICE_TRANSCRIPT,
    intent: ProposedVoiceIntent | None = None,
    aliases: dict[tuple[str, str], str] | None = None,
) -> tuple[
    dict[str, object],
    PushToTalkRecorder,
    VoiceMonitoringGateway,
    FixtureSpeechToText,
]:
    profile = load_board_profile(
        load_json(
            ROOT
            / "firmware"
            / "cardputer"
            / "board_profiles"
            / "cardputer.original.v1.json"
        ),
        load_json(SCHEMAS / "board-profile.schema.json"),
    )
    device = CardputerSimulator(
        device_id="cardputer:01",
        key_id="device-key:01",
        secret=DEVICE_SECRET,
        board_profile=profile,
        firmware_version="0.1.0-sim",
        boot_id="boot:voice-01",
    )
    if active_profile is not Profile.ASSISTANT:
        device.switch_profile(
            active_profile,
            changed_at=NOW,
            unlocked=True,
        )
    recorder = PushToTalkRecorder(profile)
    recorder.press("capture:voice-monitor-01", recorded_at=NOW)
    recorder.append_encoded(audio, duration_ms=1_200)
    recorder.release(completed_at=NOW + timedelta(milliseconds=1_200))
    envelope = device.voice_command_message(
        recorder,
        sent_at=NOW + timedelta(seconds=2),
        correlation_id="correlation:voice-monitor-01",
    )
    registry = DeviceRegistry()
    registry.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=profile,
            firmware_version="0.1.0-sim",
        ),
        DEVICE_SECRET,
    )
    protocol_validator = DeviceProtocolValidator(
        envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
        payload_schemas={
            "voice_command": load_json(SCHEMAS / "voice-command.schema.json")
        },
    )
    digest = f"sha256:{hashlib.sha256(audio).hexdigest()}"
    speech = FixtureSpeechToText({digest: transcript})
    extractor = ExactVoiceIntentExtractor(
        {
            VOICE_TRANSCRIPT: intent
            or ProposedVoiceIntent(
                action="camera.monitor",
                target_alias="garagem",
                duration_seconds=120,
            )
        }
    )
    gateway = VoiceMonitoringGateway(
        verifier=DeviceMessageVerifier(protocol_validator, registry),
        speech=speech,
        transcription_validator=TranscriptionContractValidator(
            load_json(SCHEMAS / "speech-transcription.schema.json")
        ),
        intent_extractor=extractor,
        aliases=CameraAliasResolver(
            aliases
            if aliases is not None
            else {("org:01", "garagem"): "camera:garage-01"}
        ),
    )
    return envelope, recorder, gateway, speech


def test_voice_message_runs_complete_monitoring_path_without_raw_audio_retention() -> (
    None
):
    service, frames, events, push, inbox, audit = build_service()
    envelope, recorder, gateway, speech = voice_fixture()

    started = gateway.handle(
        envelope,
        context(),
        service,
        received_at=NOW + timedelta(seconds=2),
    )
    recorder.acknowledge_processed("capture:voice-monitor-01", succeeded=True)
    completed = service.run_to_completion(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=10),
    )

    assert started.status is JobState.RUNNING
    assert completed.status is JobState.COMPLETED
    assert speech.calls == 1
    assert frames.worker_starts == 1
    assert len(events.events) == 1
    assert len(push.deliveries) == 1
    assert len(inbox.deliveries) == 1
    assert len(audit.events) == 1
    assert recorder.buffered_bytes == 0
    public_material = json.dumps(
        {
            "outcome": monitoring_outcome_to_contract(completed),
            "audit": audit_to_contract(audit.events[0]),
        }
    )
    assert VOICE_TRANSCRIPT not in public_material
    assert VOICE_AUDIO.decode() not in public_material


def test_voice_in_assistant_profile_is_rejected_before_transcription() -> None:
    service, frames, _events, _push, _inbox, _audit = build_service()
    envelope, _recorder, gateway, speech = voice_fixture(
        active_profile=Profile.ASSISTANT
    )

    with pytest.raises(VoiceCommandRejectedError) as error:
        gateway.handle(
            envelope,
            context(),
            service,
            received_at=NOW + timedelta(seconds=2),
        )

    assert error.value.reason_code == "SENTINEL_PROFILE_REQUIRED"
    assert speech.calls == 0
    assert frames.worker_starts == 0


def test_unknown_transcript_is_not_interpreted_or_dispatched() -> None:
    service, frames, _events, _push, _inbox, _audit = build_service()
    envelope, _recorder, gateway, speech = voice_fixture(
        transcript="Execute alguma coisa diferente."
    )

    with pytest.raises(VoiceCommandRejectedError) as error:
        gateway.handle(
            envelope,
            context(),
            service,
            received_at=NOW + timedelta(seconds=2),
        )

    assert error.value.reason_code == "TRANSCRIPT_NOT_REGISTERED"
    assert speech.calls == 1
    assert frames.worker_starts == 0


def test_transcription_cannot_claim_a_different_audio_digest() -> None:
    validator = TranscriptionContractValidator(
        load_json(SCHEMAS / "speech-transcription.schema.json")
    )
    payload = {
        "contract_version": 1,
        "transcription_id": "transcription:01",
        "provider_id": "speech-provider:fixture-v1",
        "execution_mode": "simulated",
        "language": "pt-BR",
        "text": VOICE_TRANSCRIPT,
        "audio_sha256": f"sha256:{'a' * 64}",
        "created_at": "2026-07-25T18:40:02Z",
    }

    with pytest.raises(VoiceCommandRejectedError) as error:
        validator.validate(
            payload,
            expected_audio_sha256=f"sha256:{'b' * 64}",
        )

    assert error.value.reason_code == "TRANSCRIPTION_AUDIO_MISMATCH"


def test_unknown_camera_alias_starts_no_worker() -> None:
    service, frames, _events, _push, _inbox, _audit = build_service()
    envelope, _recorder, gateway, _speech = voice_fixture(
        intent=ProposedVoiceIntent(
            action="camera.monitor",
            target_alias="portao",
            duration_seconds=120,
        )
    )

    with pytest.raises(VoiceCommandRejectedError) as error:
        gateway.handle(
            envelope,
            context(),
            service,
            received_at=NOW + timedelta(seconds=2),
        )

    assert error.value.reason_code == "TARGET_ALIAS_NOT_REGISTERED"
    assert frames.worker_starts == 0


def test_voice_replay_does_not_start_duplicate_worker() -> None:
    service, frames, _events, _push, _inbox, _audit = build_service()
    envelope, _recorder, gateway, _speech = voice_fixture()
    gateway.handle(
        envelope,
        context(),
        service,
        received_at=NOW + timedelta(seconds=2),
    )

    with pytest.raises(DeviceMessageRejectedError) as error:
        gateway.handle(
            envelope,
            context(),
            service,
            received_at=NOW + timedelta(seconds=3),
        )

    assert error.value.reason_code == "MESSAGE_ID_REPLAYED"
    assert frames.worker_starts == 1


def test_voice_command_still_obeys_resource_policy() -> None:
    service, frames, _events, _push, _inbox, audit = build_service()
    envelope, _recorder, gateway, _speech = voice_fixture()
    unauthorized = replace(
        context(),
        resource_grant=replace(
            context().resource_grant,
            resource_ids=frozenset(),
        ),
    )

    outcome = gateway.handle(
        envelope,
        unauthorized,
        service,
        received_at=NOW + timedelta(seconds=2),
    )

    assert outcome.status is JobState.DENIED
    assert outcome.reason_code == "TARGET_NOT_AUTHORIZED"
    assert frames.worker_starts == 0
    assert audit.events[0].result is ExecutionStatus.DENIED
