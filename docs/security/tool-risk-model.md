# Tool risk model

## Tool registry

Every executable capability has a versioned manifest containing:

- unique tool ID and version;
- category and execution location;
- risk class and interaction mode;
- required roles and profile;
- accepted grant or scope types;
- required verified capabilities;
- confirmation policy;
- parameter and result schemas;
- timeout and resource limits;
- idempotency behavior;
- audit and evidence behavior;
- cancellation and rollback behavior;
- outbound network policy.

Unknown tools, versions, fields, targets and result shapes are rejected.

## Risk classes

### R0 — read-only

Reads previously authorized state without starting an observing worker or
changing external state.

Examples:

- camera status;
- known assets;
- prior alerts;
- stored evidence;
- local configuration summary.

### R1 — bounded observation

Starts finite observation against an authorized resource or operation scope.

Examples:

- camera monitoring;
- passive BLE or radio observation;
- approved multicast discovery;
- NFC reading;
- Shodan lookup for a verified asset.

R1 requires a finite window, resource limits and cancellation when it outlives
the request.

### R2 — active or state-changing

Changes state, transmits, probes actively or causes a target-visible action.

Examples:

- approved active discovery;
- test-tag NFC writing;
- approved RF test transmission;
- camera configuration;
- paired-host declarative HID script.

R2 requires:

- an exact target;
- an eligible operator role;
- the correct profile;
- a short-lived operation scope;
- immutable preview;
- explicit confirmation, physical when specified;
- complete audit;
- strict limits, timeout and emergency cancellation.

### R3 — prohibited

R3 includes:

- jamming and uncontrolled flooding;
- credential interception, theft, stuffing or default-password automation;
- third-party camera or stream access;
- autonomous exploitation;
- persistence on another system;
- destructive payloads;
- arbitrary model-generated HID or shell actions;
- undefined or Internet-wide targets;
- interference with safety systems.

R3 is not merely “manual only.” In Tomato Sentinel it is:

```yaml
executable: false
registrable: false
ai_proposable: false
```

## Interaction modes

Do not overload an `activity: active` field. Declare one or more precise modes:

```text
read_existing_state
passive_observation
multicast_discovery
targeted_validation
state_change
radio_transmission
physical_output
```

The interaction mode informs network, confirmation, evidence and UI
obligations independently of the broad risk class.

## Sensitive hardware defaults

- NFC/RFID: read-only.
- nRF24 and sub-GHz: receive-only.
- Infrared: learn-only until an approved target command exists.
- USB HID: disabled.
- Wi-Fi/BLE: passive observation.

Transmission, writing and target-visible operations are separate R2 tools;
they are never parameters that silently upgrade a read-only tool.

## Regulatory and physical constraints

Radio profiles must declare region, frequency/channel, modulation when known,
power, antenna assumptions, duty cycle, maximum duration and supported
hardware. A configured profile does not override applicable law.

The emergency-cancel path has higher priority than normal UI work and records
the best available terminal audit event without delaying shutdown.
