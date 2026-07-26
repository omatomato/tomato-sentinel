# Product vision

## Mission

Tomato Sentinel provides one controlled interface for assistance, physical
monitoring, asset visibility and an authorized security laboratory without
turning natural-language prompts into unrestricted actions.

The system serves operators who own or are explicitly authorized to manage the
devices, networks, cameras, sensors, identifiers and radio profiles in scope.

## Product capabilities

### AI assistant

- accepts bounded push-to-talk audio and keyboard input;
- interprets intent into versioned structured commands;
- answers read-only state questions;
- explains alerts and inventory changes;
- prepares reviewable plans for registered tools.

### Physical sentinel

- registers approved cameras and sensors;
- detects motion and people without silently identifying them;
- confirms events over time;
- applies privacy filtering and retention policy;
- notifies configured recipients and Cardputer devices.

### Asset visibility

- observes explicitly configured local networks;
- discovers candidates without trusting or enrolling them;
- normalizes approved inventory;
- compares verified internal assets with external intelligence;
- reports relevant changes.

### Authorized laboratory

- exposes only registered, capability-backed tools;
- starts receive-only and read-only;
- requires temporary operating scope for active operations;
- makes sensitive state visible on the device;
- supports immediate cancellation and complete audit.

## Product boundaries

Tomato Sentinel is not:

- a general-purpose autonomous exploitation platform;
- a way to access third-party cameras or networks;
- a credential collection or testing service;
- an unrestricted radio transmitter;
- a biometric identity product;
- a mechanism for executing arbitrary model-generated shell or HID output.

## Operating profiles

| Profile | Purpose | Examples |
| --- | --- | --- |
| `assistant` | Default interaction | voice/text, status, approved automation |
| `sentinel` | Physical monitoring | camera jobs, alerts, privacy masks |
| `inventory` | Asset visibility | passive observation, bounded discovery |
| `lab` | Temporary authorized laboratory | scoped R1/R2 hardware and network tools |
| `recovery` | Repair and containment | rotation, reset, audit export, recovery |

Profiles are device modes, not operator roles. A tool cannot silently switch a
profile. `lab` expires after inactivity and reboot unless an explicit,
reviewed recovery policy says otherwise.

## Success criteria

The platform succeeds when it:

- denies ambiguous or unauthorized actions safely;
- produces useful monitoring and inventory results with minimal personal data;
- makes every sensitive operation visible, bounded and cancellable;
- can replace or quarantine an upstream integration without rewriting business
  logic;
- remains usable with simulated hardware and offline test providers;
- reports exactly what ran, what did not run and why.
