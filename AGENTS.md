# AGENTS.md

## 1. Project identity

Working name: Tomato Sentinel

# AGENTS.md

## 1. Project identity

Working name: **Tomato Sentinel**

Tomato Sentinel is a modular, privacy-conscious AI, automation and authorized cybersecurity platform built around M5Stack Cardputer devices, camera nodes, backend services and optional radio or card-reader modules.

The Cardputer acts as a portable human interface and field terminal. It provides:

* push-to-talk voice commands through its built-in microphone;
* keyboard input;
* visual and audio responses;
* local status and alert display;
* access to approved hardware modules;
* controlled cybersecurity and asset-inventory workflows;
* emergency cancellation and physical confirmation.

The Cardputer is not expected to perform heavy language-model or computer-vision inference locally. Expensive processing belongs on an authorized backend, edge computer or configured AI provider.

The project must support both the original Cardputer and newer variants through explicit board profiles. Code must not assume that every variant uses the same audio codec, pins, memory limits or peripheral layout.

---

## 2. Product mission

The system combines four related capabilities:

1. **AI assistant**

   * receives voice and keyboard commands;
   * interprets user intent;
   * queries system state;
   * explains alerts;
   * creates structured, reviewable jobs.

2. **Physical monitoring**

   * registers authorized cameras and sensors;
   * detects movement and people;
   * correlates events from multiple sensors;
   * sends alerts to phones, watches and Cardputer devices.

3. **Asset visibility**

   * discovers authorized devices on configured local networks;
   * inventories services and hardware;
   * compares internal assets with their externally visible exposure;
   * monitors changes in known assets.

4. **Authorized security laboratory**

   * supports approved Wi-Fi, BLE, NFC, RFID, infrared and radio modules;
   * records observations and evidence;
   * performs bounded diagnostics;
   * requires explicit scope and policy checks before active operations.

The project must not become an unrestricted collection of offensive actions controlled by natural-language prompts.

AI may propose operations. Deterministic code must decide whether an operation is allowed.

---

## 3. Primary use cases

### 3.1 Voice-controlled camera monitoring

Example:

> “Observe a câmera da garagem durante trinta minutos e me avise se aparecer alguém.”

Expected flow:

```text
Cardputer microphone
    -> local push-to-talk capture
    -> authenticated audio upload
    -> speech-to-text
    -> structured intent
    -> camera authorization
    -> monitoring job
    -> person detection
    -> event confirmation
    -> phone/watch/Cardputer notification
```

### 3.2 Camera status query

Example:

> “Quais câmeras estão offline?”

The assistant may retrieve camera status and summarize it.

It must not expose camera credentials, private stream URLs or internal network secrets.

### 3.3 Local asset inventory

Example:

> “Mostre os dispositivos novos encontrados na minha rede de laboratório.”

The system compares authorized discovery results with the previous inventory and reports only relevant changes.

### 3.4 External exposure verification

Example:

> “Verifique se algum IP da minha organização aparece exposto no Shodan.”

The system searches only explicitly authorized identifiers, such as:

* organization-owned IP addresses;
* authorized CIDR ranges;
* verified domains;
* verified autonomous system numbers;
* saved asset groups.

Shodan data is treated as external intelligence, not as permission to connect to a device.

### 3.5 NFC or RFID inventory

Example:

> “Leia esta tag e mostre a tecnologia e os dados NDEF.”

Read-only inspection is permitted when a compatible module is connected.

Writing, emulation or replay requires stronger policy checks.

### 3.6 Radio laboratory observation

Example:

> “Comece uma captura passiva no módulo CC1101.”

Receive-only observation may be allowed in laboratory mode.

Transmission requires an explicit authorized configuration, supported frequency profile and physical confirmation.

---

## 4. Operating profiles

The device must have explicit operating profiles. A tool cannot silently change profiles.

### 4.1 `assistant`

Default profile.

Allowed:

* voice and text commands;
* camera status;
* notification review;
* approved automation;
* read-only system queries;
* local device status.

Not allowed:

* active network scanning;
* RF transmission;
* NFC emulation;
* USB HID payload execution;
* credential testing.

### 4.2 `sentinel`

Physical-monitoring profile.

Allowed:

* camera monitoring;
* movement and person detection;
* sensor correlation;
* alert management;
* privacy-mask configuration;
* incident acknowledgement.

### 4.3 `inventory`

Asset-discovery profile.

Allowed:

* passive network observations;
* approved local discovery protocols;
* service inventory inside configured network ranges;
* Shodan queries for verified assets;
* comparison between internal and external exposure.

### 4.4 `lab`

Authorized cybersecurity profile.

Allowed actions depend on the active scope, hardware, risk class and operator confirmation.

Entering this profile requires:

* an unlocked device;
* a configured operator identity;
* an active scope;
* a visible profile indicator;
* an automatic expiration time.

The device must leave laboratory mode after inactivity or reboot unless explicitly configured otherwise.

### 4.5 `recovery`

Minimal profile for:

* credential rotation;
* configuration repair;
* firmware recovery;
* network reset;
* audit export;
* disabling compromised devices.

No AI-directed security tools run in recovery mode.

---

## 5. Capability-based hardware model

Do not assume that a connected device has every possible peripheral.

At startup, enumerate capabilities and create a signed capability report.

Example:

```json
{
  "device_id": "cardputer-01",
  "board_profile": "cardputer",
  "firmware_version": "0.1.0",
  "capabilities": {
    "microphone": true,
    "speaker": true,
    "keyboard": true,
    "display": true,
    "micro_sd": true,
    "wifi": true,
    "ble": true,
    "infrared_tx": true,
    "imu": true,
    "pn532": false,
    "nrf24": true,
    "cc1101": false,
    "gps": false
  }
}
```

A capability must not become available merely because a client claims that it exists.

Hardware detection belongs in trusted firmware code.

---

## 6. Repository structure

```text
firmware/
  cardputer/
    core/
    board_profiles/
    audio/
    ui/
    storage/
    transport/
    policy/
    tools/
      wifi/
      ble/
      nfc/
      subghz/
      nrf24/
      infrared/
      usb/
    tests/
    AGENTS.md

apps/
  api/
  operator-console/
  mobile/

services/
  orchestrator/
  assistant/
  speech/
  vision/
  camera-gateway/
  asset-inventory/
  external-intelligence/
  notifications/
  evidence/
  audit/

packages/
  contracts/
  policy-engine/
  security/
  scope/
  device-protocol/
  tool-sdk/

integrations/
  shodan/
  mqtt/
  webhooks/
  home-automation/
  notification-providers/

infra/
  compose/
  deployment/
  monitoring/
  provisioning/

docs/
  architecture/
  threat-models/
  decisions/
  protocols/
  hardware/
  privacy/
  operations/

tests/
  integration/
  end-to-end/
  security/
  hardware-simulation/
```

Shared message and event schemas belong in `packages/contracts`.

Shared permission logic belongs in `packages/policy-engine`.

Do not duplicate authorization rules inside individual user interfaces.

---

# . Bruce integration policy

Bruce is a reference implementation and potential integration source, not an automatically vendored dependency.

Before using Bruce code:

1. inspect the exact source files and current license;
2. record the applicable license in a dependency manifest;
3. decide whether the project will:

   * use Bruce as separate firmware;
   * interoperate through exported data;
   * implement compatible hardware drivers independently;
   * incorporate AGPL-compatible code;
4. document the decision in an architecture decision record;
5. preserve required notices and source obligations.

Do not copy functions from Bruce into this repository without recording their origin and license.

Preferred initial strategy:

```text
M5Launcher or another boot manager
    ├── Tomato Sentinel firmware
    ├── Bruce firmware
    └── Recovery firmware
```

This provides strong separation while the native Tomato Sentinel tool framework is developed.

A later unified firmware is acceptable only after:

* memory and storage analysis;
* security review;
* dependency-license review;
* boot and recovery design;
* clear tool isolation;
* reliable hardware abstraction.

Do not blindly merge two large firmware codebases.
## Upstream software ecosystem

This project is designed to study, reuse, adapt and integrate multiple open-source projects.

Bruce is one possible upstream project. It is not the primary architecture and must not receive special treatment that bypasses the general upstream-software policy.

Potential upstream categories include:

* M5Stack and Cardputer firmware;
* launchers and firmware managers;
* Wi-Fi and Bluetooth diagnostic firmware;
* NFC, RFID, infrared and radio libraries;
* camera-discovery clients;
* network video recorders;
* video-restreaming services;
* object-detection systems;
* home-automation platforms;
* network-inventory tools;
* packet-analysis tools;
* notification services;
* speech-processing tools;
* local AI inference engines;
* mobile and watch integrations.

The presence of a repository on GitHub does not make it an approved dependency.

Codex may inspect any relevant public repository for research. Codex must not automatically import, build, execute or deploy repository code merely because it appears useful.

---

## Upstream integration modes

Every upstream project must use exactly one declared integration mode.

### `reference_only`

The project is inspected to understand:

* protocols;
* device drivers;
* user flows;
* architectural approaches;
* known compatibility issues.

No source code is copied or executed.

### `independent_reimplementation`

The upstream behavior or protocol is independently implemented using public specifications and documented observations.

The implementation must not copy source code from an incompatible license.

### `native_library`

A small, reviewed dependency is linked directly into a Tomato Sentinel component.

This mode is appropriate for:

* hardware drivers;
* protocol parsers;
* serialization libraries;
* bounded utility libraries.

Native libraries require:

* a pinned version;
* dependency review;
* license review;
* resource analysis;
* automated tests;
* a documented update policy.

### `vendored_component`

Selected upstream source files are stored inside the repository.

This mode requires:

* explicit justification;
* source provenance;
* original copyright notices;
* exact upstream commit;
* local patch tracking;
* license compatibility;
* a procedure for synchronizing security fixes.

Vendoring an entire repository by default is prohibited.

### `external_service`

The project runs as an independent process or container.

This is the preferred mode for large Linux-oriented applications such as:

* network video recorders;
* camera gateways;
* home-automation platforms;
* network-analysis tools;
* model servers;
* databases.

The external service must communicate through a documented API, event bus or message contract.

### `firmware_image`

The project runs as a separate firmware image on the Cardputer.

This mode is appropriate when:

* the project controls the complete device;
* peripheral conflicts make coexistence unsafe;
* memory usage prevents native integration;
* licensing favors distribution as an independent image;
* the project was not designed as a reusable library.

Separate firmware images must not automatically inherit Tomato Sentinel credentials.

### `remote_adapter`

Tomato Sentinel connects to an installation managed outside this repository.

Examples include:

* an existing home-automation server;
* an existing NVR;
* an existing Shodan account;
* an existing notification provider;
* a separate security-laboratory server.

Credentials remain isolated inside the adapter responsible for that integration.

---

## Upstream software catalog

All researched or integrated projects must be registered in:

```text
config/upstream/software-catalog.yaml
```

Example:

```yaml
projects:
  - project_id: example-camera-service
    display_name: Example Camera Service
    source:
      provider: github
      owner: example
      repository: camera-service
      commit: 0123456789abcdef
      release: null

    purpose:
      - camera_ingestion
      - video_restreaming

    runtime:
      environment: linux_container
      architectures:
        - amd64
        - arm64

    integration:
      mode: external_service
      status: evaluating
      adapter: integrations/example_camera

    licensing:
      detected_license: MIT
      reviewed: false
      compatible: unknown
      notice_required: true

    security:
      trust_level: untrusted_upstream
      network_access: restricted
      filesystem_access: read_only
      privileged_container: false
      vulnerability_reviewed_at: null

    provenance:
      checksum: null
      signature_verified: false
      reviewed_commit: null

    maintenance:
      last_upstream_activity: null
      last_local_review: null
      update_policy: manual
      owner: camera-team

    compatibility:
      cardputer: not_applicable
      backend: untested
      test_environment: null
```

Never use a floating branch such as `main` as a production dependency.

The catalog must identify an exact release, tag or commit.

---

## Upstream intake workflow

Before Codex integrates an upstream project, it must perform the following workflow.

### Step 1 — Identify the objective

Document the exact capability needed.

Bad objective:

```text
Add this cool hacking repository.
```

Good objective:

```text
Provide receive-only nRF24 channel activity measurements
through the Cardputer laboratory interface.
```

### Step 2 — Inspect the repository

Record:

* repository owner;
* exact repository;
* default branch;
* latest reviewed commit;
* release model;
* implementation language;
* supported hardware;
* build system;
* dependency manifests;
* test suite;
* license;
* recent maintenance activity;
* open security advisories;
* required privileges;
* network destinations;
* storage behavior.

### Step 3 — Classify compatibility

Determine whether the repository is intended for:

```text
ESP32 firmware
Linux backend
desktop application
mobile application
browser application
library
container
external service
```

Do not attempt to compile arbitrary Linux software for the Cardputer.

### Step 4 — Select an integration mode

Select one of:

```text
reference_only
independent_reimplementation
native_library
vendored_component
external_service
firmware_image
remote_adapter
```

Explain why that mode is safer and easier to maintain than the alternatives.

### Step 5 — Review licensing

Before copying code:

* identify the actual repository license;
* inspect licenses of relevant dependencies;
* determine distribution obligations;
* preserve required notices;
* reject code with missing or incompatible licensing;
* document any exception.

A repository without a clear license must be treated as source-visible, not automatically reusable.

### Step 6 — Threat-model the component

Identify:

* inputs controlled by users;
* external network access;
* secrets required;
* filesystem access;
* device access;
* radio or USB access;
* elevated privileges;
* update mechanism;
* parser exposure;
* untrusted binary execution;
* impact if compromised.

### Step 7 — Create an isolation plan

Prefer:

* unprivileged containers;
* read-only filesystems;
* explicit device allowlists;
* explicit destination allowlists;
* resource limits;
* isolated credentials;
* bounded execution;
* structured logs;
* emergency cancellation.

### Step 8 — Build a proof of concept

The proof of concept must:

* use synthetic or owned test data;
* run in a sandbox;
* avoid production credentials;
* demonstrate one bounded capability;
* include a negative control;
* record resource usage;
* record commands actually executed.

### Step 9 — Approve or reject

Possible statuses:

```text
discovered
evaluating
prototype
approved
integrated
isolated_firmware
rejected
deprecated
quarantined
```

A rejected project remains in the catalog with the rejection reason to prevent repeated evaluation.

---

## Codex repository-research rules

Codex may search GitHub to locate possible implementations.

Search results are research leads, not trusted dependencies.

For every candidate, Codex must answer:

1. What exact problem would this repository solve?
2. What part of the repository is actually needed?
3. Can the same result be achieved through a standard protocol?
4. Does it run on ESP32, Linux, mobile or another platform?
5. What privileges does it require?
6. What license applies?
7. Is the project actively maintained?
8. Does it have tests?
9. Does it download or execute additional code?
10. Which integration mode should be used?
11. What is the smallest safe proof of concept?
12. How will it be removed if it becomes unsafe or abandoned?

Codex must not:

* execute installation scripts directly from a URL;
* run unreviewed shell pipelines;
* trust GitHub star counts as a security signal;
* automatically accept generated binaries;
* use floating dependency versions;
* silently add network destinations;
* add privileged containers without justification;
* copy code without preserving provenance;
* disable security checks to make upstream code compile;
* expose Tomato Sentinel credentials to separate firmware.

---

## Software bill of materials

The project must maintain a software bill of materials for:

* backend services;
* firmware libraries;
* containers;
* mobile applications;
* vendored components;
* build tools;
* generated release artifacts.

Each release must record:

```text
component
version
source repository
source commit
package checksum
license
direct or transitive relationship
build environment
release artifact
```

Dependencies that cannot be detected automatically must be added manually.

Release artifacts should be reproducible where practical.

---

## Upstream change monitoring

Approved upstream projects must be monitored for:

* new releases;
* security advisories;
* dependency changes;
* license changes;
* archived repositories;
* deleted releases;
* force-pushed tags;
* changes in supported hardware;
* protocol changes;
* removed functionality.

An update is not automatically merged.

Required update flow:

```text
upstream change detected
    -> catalog entry marked revalidation_required
    -> changelog and diff reviewed
    -> tests executed
    -> permissions compared
    -> SBOM regenerated
    -> update accepted or rejected
```

---

## Local discovery model

Local discovery identifies possible devices on explicitly configured networks.

It does not authenticate, enroll or authorize them.

Discovery must be divided into stages.

### Stage 1 — Passive observations

Use available sources such as:

* DHCP lease information;
* ARP or neighbor tables;
* mDNS announcements;
* existing SSDP notifications;
* existing WS-Discovery announcements;
* router or access-point inventory integrations.

Passive observations must not create trusted assets automatically.

### Stage 2 — Multicast discovery

Supported discovery mechanisms may include:

```text
mDNS
SSDP
WS-Discovery
ONVIF device discovery
```

Discovery jobs must have:

* an allowlisted interface;
* an allowlisted network;
* a finite duration;
* rate limits;
* cancellation;
* structured results.

### Stage 3 — Targeted validation

Only discovered candidates or explicitly scoped addresses may be validated.

Validation may determine:

* whether HTTP or HTTPS is available;
* whether an ONVIF device service exists;
* whether RTSP is advertised;
* whether the device exposes a supported discovery document;
* probable manufacturer or product family;
* whether authentication is required.

Validation must not:

* guess credentials;
* attempt default passwords;
* enumerate unrelated services without scope;
* test arbitrary Internet addresses;
* bypass camera authentication.

### Stage 4 — ONVIF capability inspection

For an ONVIF candidate, the system may query supported device services after authorization.

Potentially relevant information includes:

* device service endpoint;
* media services;
* available profiles;
* event services;
* PTZ capability;
* audio capability;
* snapshot capability;
* supported authentication method.

A discovery response must not be treated as proof of official conformance.

### Stage 5 — Operator approval

The operator must approve enrollment.

The interface should display:

```text
IP address
MAC or pseudonymous identifier
discovery protocols
probable device type
manufacturer information, when available
authentication status
first observed
last observed
confidence
```

### Stage 6 — Credentialed enrollment

Credentials are supplied separately and stored in the credential vault.

Discovery records must not contain plaintext credentials.

---

## Discovery result schema

```json
{
  "discovery_id": "discovery-01",
  "observed_at": "2026-07-25T18:40:00Z",
  "observer_id": "edge-node-01",
  "network_id": "home-lan",
  "addresses": [
    "192.168.1.73"
  ],
  "protocols": [
    "ws_discovery",
    "onvif"
  ],
  "probable_types": [
    "network_camera"
  ],
  "services": [
    {
      "service_type": "onvif_device",
      "endpoint": "redacted-reference",
      "authentication_required": true
    }
  ],
  "confidence": 0.91,
  "enrollment_status": "candidate"
}
```

Possible enrollment statuses:

```text
candidate
ignored
approved
credential_required
enrolled
rejected
quarantined
```

---

## Execution placement

Do not force every capability onto the Cardputer.

Use the following preference:

```text
Cardputer
    user interface
    microphone
    keyboard
    display
    basic passive observations
    directly connected hardware modules
    physical confirmation

Edge node
    multicast discovery
    camera connectivity
    local vision inference
    packet capture
    protocol normalization

Backend
    orchestration
    AI interpretation
    policy engine
    asset inventory
    external intelligence
    notifications
    evidence and audit

External isolated service
    large upstream applications
    NVR software
    home automation
    network-analysis engines
    model servers
```

The Cardputer may request a task without executing the complete task locally.

Example:

```text
Cardputer:
“Descubra câmeras nesta rede.”

Backend:
validates scope and authorization

Edge node:
performs SSDP and WS-Discovery

Backend:
normalizes and stores candidates

Cardputer:
displays candidates for approval
```

---

## Upstream adapter contract

External services must be hidden behind stable internal adapters.

```python
from typing import Protocol

class UpstreamAdapter(Protocol):
    project_id: str

    async def health(self) -> "HealthResult":
        ...

    async def capabilities(self) -> list[str]:
        ...

    async def validate_configuration(self) -> "ValidationResult":
        ...

    async def execute(
        self,
        operation: str,
        parameters: dict,
        context: "ExecutionContext",
    ) -> "ExecutionResult":
        ...

    async def cancel(self, execution_id: str) -> None:
        ...
```

Business logic must depend on the internal adapter contract, not directly on an upstream project’s API.

This allows an upstream project to be:

* upgraded;
* replaced;
* disabled;
* quarantined;
* moved to another host;

without rewriting the complete system.

---

## 8. Voice interaction

The built-in microphone is a primary interface.

### 8.1 Default behavior

Use push-to-talk by default.

Continuous audio recording is disabled by default.

Recommended interaction:

1. user holds a configured key;
2. the display shows a recording indicator;
3. firmware records bounded audio;
4. user releases the key;
5. firmware stops recording;
6. audio is encrypted and sent;
7. the server transcribes it;
8. the assistant returns a structured command or answer;
9. the Cardputer displays the planned action;
10. sensitive actions request confirmation.

### 8.2 Audio limits

Audio capture must have:

* configurable maximum duration;
* finite memory use;
* cancellation;
* codec and sample-rate metadata;
* no silent background recording;
* visible recording state;
* deletion after successful processing unless retention is explicitly enabled.

Example:

```json
{
  "protocol_version": 1,
  "message_id": "msg-01",
  "device_id": "cardputer-01",
  "message_type": "voice_command",
  "recorded_at": "2026-07-25T18:40:00Z",
  "audio": {
    "encoding": "opus",
    "sample_rate": 16000,
    "channels": 1,
    "duration_ms": 4820
  }
}
```

### 8.3 Optional local audio features

Potential local features include:

* voice activity detection;
* wake-button detection;
* audio-level visualization;
* offline command shortcuts;
* alarm-tone recognition;
* glass-break or smoke-alarm classification.

Audio-event recognition must be independently configurable and must not imply continuous cloud recording.

---

## 9. Structured AI command pipeline

Never execute free-form model output.

Required pipeline:

```text
user input
    -> transcription
    -> intent extraction
    -> schema validation
    -> target resolution
    -> scope validation
    -> authorization
    -> risk classification
    -> confirmation policy
    -> execution
    -> evidence
    -> user-visible result
```

Example command:

```json
{
  "command_id": "cmd-01",
  "actor_id": "user-01",
  "source_device_id": "cardputer-01",
  "profile": "sentinel",
  "action": "monitor_camera",
  "targets": ["camera:garage-01"],
  "parameters": {
    "duration_seconds": 1800,
    "detections": ["person"],
    "notification_policy": "immediate"
  },
  "scope_id": "scope-home-01",
  "requested_at": "2026-07-25T18:40:01Z"
}
```

The model may only choose actions registered in the tool registry.

Unknown actions, parameters or targets must be rejected.

The AI must not invent device identifiers.

---

## 10. Tool registry

Every executable capability must be registered.

Example:

```json
{
  "tool_id": "network.local_discovery",
  "version": 1,
  "category": "inventory",
  "execution_location": "backend",
  "activity": "active",
  "risk_class": "R1",
  "required_profile": "inventory",
  "required_scope_types": ["cidr"],
  "requires_confirmation": false,
  "supports_dry_run": true,
  "timeout_seconds": 120
}
```

Required fields:

* unique tool identifier;
* version;
* category;
* execution location;
* passive or active classification;
* risk class;
* required profile;
* accepted scope types;
* confirmation policy;
* timeout;
* resource limits;
* audit behavior;
* rollback or cancellation behavior;
* schema for parameters;
* schema for results.

No hidden tools.

No execution by arbitrary shell command.

---

## 11. Risk classes

### `R0 — Read-only`

Examples:

* show camera status;
* list known devices;
* view previous alerts;
* query stored inventory;
* inspect local configuration;
* summarize existing evidence.

May run without confirmation after authorization.

### `R1 — Bounded observation`

Examples:

* passive BLE discovery;
* passive radio capture;
* approved local service discovery;
* camera monitoring;
* Shodan lookup for verified assets;
* NFC reading.

Requires a valid scope and finite execution window.

### `R2 — Active or state-changing`

Examples:

* writing to a test NFC tag;
* transmitting an approved RF test signal;
* active network probing;
* changing camera configuration;
* enrolling a new device;
* executing an approved USB HID test script.

Requires:

* laboratory or administrative profile;
* explicit target;
* operator confirmation;
* short expiration;
* complete audit event.

### `R3 — Restricted`

Examples:

* jamming;
* uncontrolled RF flooding;
* deauthentication of third-party devices;
* credential interception;
* credential stuffing;
* opening third-party camera feeds;
* autonomous exploitation;
* destructive payloads;
* persistence on another system;
* arbitrary USB HID commands;
* actions without a defined target.

R3 operations must not be autonomously executed.

Adding any R3-adjacent functionality requires a separate threat model, architecture decision and implementation review.

---

## 12. Scopes

All active cybersecurity activity requires an active scope.

Example:

```json
{
  "scope_id": "scope-lab-01",
  "name": "Home security laboratory",
  "owner_id": "user-01",
  "valid_from": "2026-07-25T12:00:00Z",
  "valid_until": "2026-07-25T22:00:00Z",
  "allowed_targets": {
    "cidrs": ["192.0.2.0/28"],
    "domains": ["lab.example"],
    "device_ids": ["camera-lab-01"],
    "radio_profiles": ["test-433-profile"],
    "nfc_tags": ["tag-lab-*"]
  },
  "allowed_tool_ids": [
    "network.local_discovery",
    "radio.capture",
    "nfc.read"
  ]
}
```

Scope validation must use canonical representations.

Do not use substring matching for domains, IP addresses or device identifiers.

Expired scope means denied execution.

---

## 13. Camera subsystem

### 13.1 Registered cameras

A camera must have:

```json
{
  "camera_id": "garage-01",
  "display_name": "Garage",
  "organization_id": "org-01",
  "source_type": "rtsp",
  "enabled": true,
  "capabilities": ["snapshot", "stream"],
  "retention_policy_id": "short-lived",
  "status": "online"
}
```

Camera credentials must be stored separately.

The public API must never return raw camera passwords or permanent stream URLs.

### 13.2 Local camera discovery

Authorized local discovery may use:

* mDNS;
* SSDP;
* WS-Discovery;
* ONVIF discovery;
* configured DHCP or ARP observations;
* bounded service discovery inside allowlisted CIDRs.

Discovery must produce candidates, not automatically trusted cameras.

Required flow:

```text
discover candidate
    -> normalize address
    -> verify address is in scope
    -> classify probable device
    -> request operator approval
    -> enroll with separate credentials
```

Do not:

* guess passwords;
* attempt default credentials automatically;
* connect outside the configured network range;
* add discovered devices without approval;
* expose discovered stream addresses to unauthorized users.

### 13.3 Vision pipeline

```text
camera frame
    -> motion or frame-change filter
    -> local object detector
    -> temporal confirmation
    -> optional multimodal confirmation
    -> privacy filtering
    -> normalized event
```

One frame must not normally be sufficient for a confirmed person alert.

Example detection event:

```json
{
  "event_id": "evt-01",
  "event_type": "person.detected",
  "camera_id": "garage-01",
  "confidence": 0.92,
  "frame_count": 3,
  "first_seen_at": "2026-07-25T18:42:09Z",
  "last_seen_at": "2026-07-25T18:42:11Z",
  "snapshot_id": "snapshot-01",
  "detector": {
    "name": "local-person-detector",
    "version": "1.0.0"
  }
}
```

Model confidence is not certainty.

### 13.4 Identity recognition

Person detection and identity recognition are separate features.

Identity recognition is outside the initial MVP.

It must not be introduced silently as part of:

* camera classification;
* event summarization;
* photo organization;
* alert enrichment.

Any identity feature requires:

* explicit enrollment;
* documented consent;
* deletion controls;
* false-match analysis;
* access restrictions;
* dedicated privacy review.

---

## 14. Shodan and external intelligence

Shodan integration belongs in `services/external-intelligence` and `integrations/shodan`.

The Cardputer must not store the Shodan API key.

The backend stores and uses the credential.

### 14.1 Allowed uses

* look up verified organization IPs;
* search verified domains or network ranges;
* retrieve externally visible services;
* detect unexpected exposure;
* compare external results with the internal inventory;
* monitor changes in owned assets;
* generate remediation tasks;
* obtain aggregate statistics for research.

### 14.2 Prohibited automatic behavior

Do not automatically:

* open camera streams found in results;
* attempt authentication;
* use default passwords;
* exploit a listed vulnerability;
* contact arbitrary third-party hosts;
* treat geolocation as proof that a device is physically nearby;
* treat a Shodan result as current ground truth;
* send raw search results to unrelated external services.

### 14.3 Exposure reconciliation

The useful feature is not “show random cameras.”

The useful feature is:

```text
internal inventory
    +
verified public identifiers
    +
Shodan observations
    =
external exposure differences
```

Example finding:

```json
{
  "finding_id": "finding-01",
  "asset_id": "camera-gateway-01",
  "finding_type": "unexpected_external_service",
  "observed_port": 8080,
  "observed_product": "http",
  "source": "shodan",
  "source_observed_at": "2026-07-20T10:20:00Z",
  "ownership_verified": true,
  "requires_live_validation": true
}
```

All Shodan findings must include the source observation time.

Historical intelligence must not be presented as a live connection test.

### 14.4 Nearby-device distinction

Use separate commands:

```text
discover_local_assets
search_external_exposure
```

Never map the phrase “devices nearby” directly to a global Shodan search.

For nearby devices, resolve the request to authorized local discovery.

For Internet exposure, require a verified asset selector.

---

## 15. Wi-Fi and BLE tools

### 15.1 Passive discovery

Permitted in an authorized scope:

* identify visible SSIDs;
* record channel and signal strength;
* identify configured BLE advertisements;
* detect changes from previous inventories;
* flag unknown devices based on local policy.

Avoid unnecessary storage of complete hardware addresses.

Use pseudonymous identifiers when long-term raw identifiers are not necessary.

### 15.2 Active network discovery

Active discovery must:

* remain inside allowlisted CIDRs;
* have a rate limit;
* have a timeout;
* identify its source device;
* support cancellation;
* produce structured results;
* avoid credential guessing;
* avoid service disruption.

### 15.3 Sensitive Wi-Fi behavior

Deauthentication, credential collection, rogue access points and traffic interception are not assistant-mode tools.

They must not be triggered by conversational ambiguity.

Any future laboratory implementation requires:

* explicit target BSSID;
* laboratory profile;
* physical confirmation;
* short duration;
* rate limits;
* clear on-screen active-state indicator;
* complete audit record;
* separate documentation.

---

## 16. NFC and RFID

Supported module families may include PN532-compatible readers.

Initial functionality:

* detect tag technology;
* read UID when permitted by the technology;
* parse NDEF records;
* store user-approved inventory metadata;
* compare test tags;
* export redacted evidence.

Writing and emulation are separate tools.

Example tool separation:

```text
nfc.read
nfc.parse_ndef
nfc.inventory
nfc.write_test_tag
nfc.emulate_test_tag
```

Do not combine all functionality into `nfc.execute`.

Writing or emulation requires:

* laboratory profile;
* explicit test-tag target;
* operator confirmation;
* result verification;
* audit event.

Do not store payment-card track data, access credentials or sensitive card contents by default.

---

## 17. nRF24 and sub-GHz modules

nRF24 and CC1101-compatible modules must be treated as separate drivers and tool families.

### 17.1 Default behavior

Receive-only by default.

Allowed initial features:

* spectrum or channel activity observation;
* packet-count statistics;
* signal-strength visualization;
* bounded raw capture;
* comparison between captures;
* labeling of the user’s own laboratory devices.

### 17.2 Transmission

Transmission must require:

* a configured hardware module;
* an approved radio profile;
* an active laboratory scope;
* a specific frequency or channel;
* a finite duration;
* bounded output;
* physical confirmation.

Do not implement unrestricted “replay everything captured.”

Captured signals may belong to unrelated systems.

### 17.3 Disallowed behavior

Do not autonomously perform:

* jamming;
* broad-spectrum flooding;
* replay against unknown targets;
* interference with safety systems;
* transmission outside configured profiles;
* indefinite transmit loops.

---

## 18. Infrared tools

Initial infrared functionality may include:

* learning signals from owned remotes;
* labeling saved commands;
* replaying an approved command;
* controlling configured home devices.

Each saved signal must include:

* creation time;
* source device;
* operator;
* label;
* protocol when known;
* target device;
* checksum or content hash.

Bulk replay and disruptive command loops are not allowed.

---

## 19. USB HID tools

USB HID functionality is disabled by default.

A future implementation must use signed, declarative scripts.

Example:

```yaml
script_id: lab-open-terminal-01
version: 1
allowed_hosts:
  - host-lab-01
steps:
  - action: key_combo
    keys: [CTRL, ALT, T]
```

Requirements:

* paired host identity;
* visible preview;
* physical confirmation;
* finite number of actions;
* no arbitrary generated keystrokes from an LLM;
* emergency cancellation;
* execution log.

The AI may select an approved script.

The AI must not generate and immediately execute a new HID payload.

---

## 20. Sensor fusion

Alerts may combine multiple authorized signals:

* camera person detection;
* door or window sensor;
* BLE presence of an enrolled device;
* Cardputer location state;
* motion sensor;
* time window;
* alarm state;
* known-home or away mode.

Example rule:

```json
{
  "rule_id": "rule-01",
  "name": "Garage person while away",
  "conditions": [
    {
      "source": "camera:garage-01",
      "event": "person.detected"
    },
    {
      "source": "presence:owner",
      "state": "away"
    }
  ],
  "actions": [
    {
      "type": "notify",
      "channels": ["phone", "watch", "cardputer"]
    }
  ]
}
```

Sensor correlation must reduce false positives rather than create opaque AI decisions.

Rules must remain inspectable.

---

## 21. Notifications

Notification channels may include:

* mobile push;
* watch through the paired phone;
* Cardputer event inbox;
* MQTT;
* configured webhooks;
* local siren or speaker, when explicitly enabled.

Every notification request needs an idempotency key.

```json
{
  "notification_id": "notification-01",
  "event_id": "event-01",
  "recipient_id": "user-01",
  "channel": "push",
  "title": "Person detected",
  "body": "A person was detected by the Garage camera.",
  "idempotency_key": "event-01:user-01:push"
}
```

Do not include:

* camera passwords;
* private addresses;
* permanent snapshot URLs;
* API keys;
* unnecessary personal data.

---

## 22. Device and backend security

### 22.1 Device identity

Each physical device needs an independent identity.

Required:

* per-device credential;
* revocation;
* rotation;
* secure provisioning;
* server-side device status;
* replay protection;
* firmware-version reporting.

Do not use one permanent token for every Cardputer.

### 22.2 Communication

All communication must use authenticated encryption.

Messages must contain:

* protocol version;
* message ID;
* device ID;
* timestamp;
* correlation ID;
* payload type.

Reject:

* invalid signatures;
* expired messages;
* unsupported protocol versions;
* unknown devices;
* replayed message IDs;
* oversized payloads.

### 22.3 Secrets

Do not commit secrets.

Do not log:

* access tokens;
* API keys;
* private keys;
* authorization headers;
* camera credentials;
* full sensitive NFC contents;
* raw audio by default.

### 22.4 Local storage

Sensitive data stored on microSD must use an encrypted vault where practical.

The firmware must tolerate:

* missing SD card;
* corrupted filesystem;
* full storage;
* sudden power loss;
* removed card.

The system must not place device private keys in ordinary plaintext files.

---

## 23. Policy engine

The policy engine is deterministic.

Required decision inputs:

```json
{
  "actor": {},
  "device": {},
  "profile": "lab",
  "scope": {},
  "tool": {},
  "targets": [],
  "parameters": {},
  "environment": {
    "network_id": "lab-network",
    "physical_confirmation": true
  }
}
```

Decision result:

```json
{
  "decision": "allow",
  "reason_code": "AUTHORIZED_LAB_OPERATION",
  "requires_confirmation": true,
  "limits": {
    "maximum_duration_seconds": 60,
    "maximum_requests": 100
  }
}
```

Possible decisions:

```text
allow
allow_with_confirmation
deny
require_scope
require_profile_change
require_physical_confirmation
```

The LLM must not override the policy engine.

---

## 24. Evidence and audit

Every significant action creates an audit event.

Required fields:

```text
event_id
timestamp
actor_id
device_id
profile
scope_id
tool_id
target
parameters_hash
policy_decision
confirmation_method
result
correlation_id
```

Security-testing evidence may additionally record:

* previous state;
* expected result;
* observed result;
* request metadata;
* response metadata;
* sanitized artifact reference;
* tool version;
* hardware module;
* exact start and stop times.

Remove secrets and unrelated personal data from exported evidence.

Never claim that an action ran when it was only planned or simulated.

Use these statuses:

```text
planned
authorized
running
cancelled
completed
failed
denied
simulated
```

---

## 25. AI boundaries

AI may:

* interpret commands;
* resolve references to known devices;
* summarize alerts;
* suggest monitoring rules;
* generate plans;
* classify selected images;
* explain inventory changes;
* rank externally exposed authorized assets;
* recommend the next defensive validation.

AI must not independently:

* enroll a new camera;
* add a network range to scope;
* disable logs;
* reveal secrets;
* open third-party camera streams;
* transmit RF;
* emulate access cards;
* run arbitrary HID payloads;
* exploit a host;
* change administrator permissions;
* delete evidence;
* create permanent external exposure.

High-risk operations need deterministic checks and user-visible confirmation.

---

## 26. Plugin architecture

Hardware and service integrations must implement explicit interfaces.

Example tool interface:

```python
from typing import Protocol

class Tool(Protocol):
    tool_id: str

    async def validate(self, request: "ToolRequest") -> None:
        ...

    async def dry_run(self, request: "ToolRequest") -> "ToolPlan":
        ...

    async def execute(self, request: "ToolRequest") -> "ToolResult":
        ...

    async def cancel(self, execution_id: str) -> None:
        ...
```

A plugin must declare:

* capabilities;
* risk class;
* required hardware;
* resource limits;
* supported board profiles;
* supported cancellation behavior;
* result schema;
* security assumptions.

Do not allow dynamically downloaded unsigned firmware plugins.

---

## 27. State machines

Long-running jobs are state machines.

Valid generic states:

```text
created
validated
authorized
awaiting_confirmation
running
completed
cancelled
expired
failed
denied
```

Invalid transitions must fail explicitly.

Each transition records:

* previous state;
* requested action;
* resulting state;
* actor;
* timestamp;
* reason;
* correlation ID.

Replayed requests must not create duplicate workers.

---

## 28. Observability

Use structured logs.

Required fields:

```text
timestamp
level
service
event
correlation_id
device_id
actor_id
scope_id
tool_id
camera_id
```

Metrics should include:

```text
connected_devices
active_camera_jobs
camera_connection_status
frames_processed_total
person_detections_total
person_detections_rejected_total
voice_commands_total
speech_processing_latency_seconds
tool_executions_total
tool_denials_total
policy_decisions_total
notification_delivery_total
notification_failures_total
external_inventory_changes_total
```

The device UI should clearly indicate:

* current profile;
* microphone recording;
* active camera monitoring;
* active network operation;
* active radio transmission;
* pending confirmation;
* disconnected backend.

---

## 29. Coding standards

### Python

* use type hints;
* validate external data;
* keep business logic outside API handlers;
* avoid global mutable state;
* use dependency injection for providers;
* apply finite timeouts;
* make retries bounded;
* separate domain models from transport models;
* use mock or fake providers in tests.

### C and C++ firmware

* avoid unbounded allocation;
* check all hardware return values;
* use finite network timeouts;
* avoid unsafe string operations;
* bound audio and packet buffers;
* document pin ownership;
* prevent simultaneous conflicting peripheral use;
* redact secrets from serial logs;
* use watchdog-compatible loops;
* support cancellation.

### TypeScript

* enable strict mode;
* avoid `any`;
* validate runtime input;
* do not rely on frontend-only authorization;
* keep generated contracts separate from domain logic.

---

## 30. Testing strategy

### 30.1 Unit tests

Test:

* command-schema validation;
* policy decisions;
* scope canonicalization;
* job state transitions;
* event deduplication;
* notification idempotency;
* camera authorization;
* Shodan-result normalization;
* hardware capability checks;
* audio size limits;
* RF transmission limits;
* retention calculations.

### 30.2 Negative controls

Every sensitive feature needs at least one negative control.

Examples:

```text
authorized camera -> monitoring starts
unauthorized camera -> no worker starts

allowlisted CIDR -> discovery runs
outside CIDR -> operation denied

registered test tag -> write requires confirmation
unknown tag -> write denied

receive-only radio capture -> allowed
transmission without lab profile -> denied

verified IP -> Shodan lookup allowed
arbitrary third-party IP -> lookup denied
```

### 30.3 Integration tests

Use fake adapters for:

* cameras;
* speech-to-text;
* Shodan;
* notifications;
* NFC;
* radio modules;
* network discovery.

External APIs must not be required for ordinary unit tests.

### 30.4 Hardware simulation

Where real hardware is unavailable, test:

* protocol serialization;
* missing module behavior;
* module hot-plug behavior;
* audio-buffer limits;
* storage failure;
* network timeout;
* cancellation;
* invalid server responses;
* credential redaction.

### 30.5 Security regressions

Include tests for:

* cross-tenant camera access;
* modified object identifiers;
* replayed device messages;
* expired scope;
* command injection into model output;
* unknown AI actions;
* SSRF through camera URLs;
* oversized image or audio uploads;
* malformed frames;
* duplicate events;
* public snapshot leakage;
* profile bypass;
* confirmation bypass;
* arbitrary Shodan target submission.

---

## 31. Agent workflow

Before modifying code:

1. read this file;
2. read the nearest nested `AGENTS.md`;
ddddd3. inspect current architecture;
4. identify the affected trust boundary;
5. determine the tool risk class;
6. identify required scope and confirmation behavior;
7. identify positive and negative tests;
8. make the smallest complete change.

During implementation:

1. preserve subsystem boundaries;
2. use structured contracts;
3. do not execute model text directly;
4. add tests alongside behavior;
5. avoid unrelated refactoring;
6. keep network access out of unit tests;
7. preserve cancellation;
8. preserve auditability;
9. do not weaken policy checks to simplify a feature.

After implementation:

1. run formatting;
2. run linting;
3. run type checking;
4. run relevant unit tests;
5. run integration tests;
6. review logs for secrets;
7. verify negative controls;
8. review the final diff;
9. report commands actually executed;
10. report checks that could not be executed.

---

## 32. Definition of done

A feature is complete only when:

* behavior is implemented;
* inputs are validated;
* required hardware capabilities are checked;
* scope is enforced;
* authorization is server-side;
* risk class is declared;
* confirmation is enforced where required;
* execution is bounded;
* cancellation works;
* events are idempotent;
* positive tests pass;
* negative controls pass;
* logs do not expose secrets;
* documentation is updated;
* the UI shows active sensitive operations;
* no unsupported claim of testing is made.

For camera detection, completion also requires:

* documented detection threshold;
* temporal confirmation;
* false-positive control;
* event deduplication;
* retention policy;
* reproducible test frames.

For security tools, completion also requires:

* explicit scope type;
* safe default mode;
* denial test;
* evidence format;
* resource limits;
* timeout;
* emergency cancellation.

---

## 33. Initial implementation order

### Phase 1 — Cardputer core

* board-profile abstraction;
* keyboard interface;
* built-in microphone capture;
* speaker response;
* push-to-talk;
* authenticated device registration;
* text command transport;
* voice command transport;
* profile indicator;
* cancellation key;
* structured logging.

### Phase 2 — Backend assistant

* speech-to-text adapter;
* structured intent extraction;
* tool registry;
* policy engine;
* scope model;
* job state machine;
* fake notification provider;
* audit events.

### Phase 3 — Camera sentinel

* camera registration;
* fake camera adapter;
* local network camera discovery;
* motion filter;
* person detector;
* temporal confirmation;
* snapshot retention;
* phone notification;
* Cardputer alert inbox.

### Phase 4 — Asset inventory

* authorized CIDR inventory;
* passive Wi-Fi and BLE observations;
* asset normalization;
* change detection;
* verified external identifiers;
* Shodan adapter;
* internal-versus-external exposure comparison.

### Phase 5 — Hardware laboratory

* peripheral capability detection;
* PN532 read-only support;
* nRF24 receive-only support;
* CC1101 receive-only support;
* infrared learning and approved replay;
* encrypted evidence storage;
* explicit lab profile;
* physical confirmation.

### Phase 6 — Controlled active tools

Only after the policy engine and negative tests are mature:

* bounded active network discovery;
* test-tag NFC writing;
* approved radio test transmission;
* paired-host USB HID scripts;
* signed tool manifests;
* advanced evidence workflows.

### Phase 7 — Hardening

* credential rotation;
* signed firmware;
* secure update channel;
* recovery image;
* encrypted local vault;
* PostgreSQL;
* broker or event bus;
* mobile application;
* watch notification integration;
* security review;
* privacy review;
* disaster-recovery procedures.

---

## 34. First MVP acceptance test

The first complete demonstration must be:

```text
1. User holds the Cardputer push-to-talk key.
2. User says:
   “Monitore a câmera da garagem por dois minutos.”
3. Audio is sent to the backend.
4. The command is transcribed.
5. The intent is converted into a validated schema.
6. The user is authorized for the camera.
7. A monitoring job starts.
8. A fake or recorded frame sequence contains a person.
9. Temporal confirmation succeeds.
10. One event is created.
11. One notification is delivered.
12. The Cardputer displays the event.
13. Replaying the same event creates no duplicate notification.
14. An unauthorized camera ID produces a denial and starts no worker.
```

Do not begin with facial recognition, uncontrolled radio transmission, random Internet-camera access or autonomous exploitation.

Build the reliable command, policy, event and evidence foundation first.

