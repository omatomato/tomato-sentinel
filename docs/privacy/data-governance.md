# Privacy and data governance

## Principles

- collect the minimum data required for a declared purpose;
- prefer local processing and pseudonymous identifiers;
- default to short retention;
- separate credentials from observations and evidence;
- make recording and sensitive operations visible;
- do not silently expand person detection into identity recognition;
- document every transfer to an external provider.

## Data classes

| Class | Examples | Default handling |
| --- | --- | --- |
| Public | release documentation | normal repository controls |
| Internal | architecture, non-secret configuration | authenticated access |
| Sensitive operational | private IPs, camera IDs, inventory, radio metadata | encryption and limited access |
| Personal | audio, images of people, stable device identifiers, location | minimization, purpose and retention |
| Secret | tokens, private keys, camera credentials | dedicated vault; never logs/evidence |
| Restricted evidence | packet/radio captures, sensitive NFC contents | explicit approval and strongest controls |

Payment-card track data, access credentials and unrelated sensitive NFC
contents are not stored by default.

## Default retention intent

Exact durations must be configured before implementation.

- push-to-talk audio: delete after successful processing unless retention is
  explicitly enabled;
- transient frames: process in memory where practical;
- alert snapshots: short-lived policy with access logging;
- discovery candidates: retain only for operator review and change detection;
- raw network/radio captures: disabled by default and bounded when approved;
- normalized audit events: retained according to security and compliance need;
- secrets: retained only while the integration or device identity is active.

Backups follow the same classification and deletion schedule, including a
documented maximum deletion delay.

## Audio

Push-to-talk is the default. Audio capture requires:

- a visible recording indicator;
- a maximum duration and size;
- codec and sample-rate metadata;
- cancellation;
- no silent continuous cloud recording;
- deletion semantics visible to the operator.

Local audio-event recognition is separately configured and must not imply
cloud recording.

## Camera data

Person detection, presence inference, identity recognition and biometric
identification are different capabilities.

The MVP supports person detection only. Identity or biometric features require
a separate architecture decision, consent model, enrollment and deletion
controls, false-match analysis, access restrictions and privacy review.

Privacy masks are applied as early as technically possible. Permanent stream
URLs and credentials never appear in public API responses or notifications.

## Stable identifiers

Avoid retaining raw MAC addresses, tag UIDs or advertising identifiers when a
rotatable or keyed pseudonym supports the purpose. Document the rotation and
reconciliation behavior.

## AI and external providers

Before sending personal or sensitive operational data to a provider, record:

- provider and service;
- purpose and data categories;
- destination region when known;
- retention/training configuration;
- redaction applied;
- credentials owner;
- deletion and provider-replacement procedure.

Support `local_only` policies for data classes that cannot leave authorized
infrastructure.

## Operator controls

The product must provide, as applicable:

- visibility into active collection;
- retention configuration;
- deletion and export;
- access history for sensitive artifacts;
- provider enable/disable controls;
- incident containment and credential rotation.

Before public or production use in Brazil, complete a dedicated LGPD review
covering roles, legal basis, data-subject requests, processor agreements and
incident handling. This document is an engineering baseline, not legal advice.
