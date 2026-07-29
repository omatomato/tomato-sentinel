# Tomato Link local pairing framing threat model

## Scope

This model covers encoding and incremental parsing of public pairing hello and
empty cancellation frames in Python and original-Cardputer C++.

It does not cover a USB, serial or network listener; peer authentication;
operator confirmation; entropy generation; credential installation; or
persistent storage.

## Assets and data

- parser memory safety and availability;
- exact public hello bytes used by the pairing transcript;
- route, ceremony, boot and time metadata integrity;
- physical cancellation semantics.

Public keys and identifiers are not secrets, but changing them must change the
later transcript fingerprint. Private keys and derived roots are credentials
and are forbidden from this layer.

## Trust boundaries

Every byte entering the decoder is untrusted. A successfully decoded frame is
still untrusted transport data. The strict pairing contract and domain logic
must validate it before changing ceremony state.

CRC-32 crosses no authentication boundary. It detects corruption only.

## Controls

- fixed magic, version and header layout;
- 1,024-byte payload and 1,044-byte frame limits;
- non-zero sequence with no implicit replay-state mutation;
- reserved fields and flags fixed to zero;
- exact length with no trailing bytes;
- CRC-32 comparison;
- non-empty hello and payload-free cancel;
- allocation-free C++ parser;
- single-frame incremental decoder that latches terminal failures;
- buffer clearing on rejection, cancellation and destruction;
- language-neutral vector shared by both implementations.

## Abuse cases

### Oversized or endless input

The decoder never buffers more than one maximum frame. A declared oversize or
an incoming chunk that exceeds the remaining capacity terminates parsing.

### Parser confusion and downgrade

Unknown versions, types, flags and reserved bits are denied. The decoder does
not scan for a new magic value after corruption and does not negotiate a
fallback format.

### Frame concatenation

Trailing bytes and a second frame are rejected. A caller creates a fresh
decoder only for a newly authorized local ceremony.

### Forged CRC

An attacker can recompute CRC-32. Therefore a valid checksum never
authenticates the sender. The later full fingerprint comparison is still
mandatory.

### Cancellation payload abuse

Cancel frames have no payload, so they cannot smuggle an operation or
free-form command. Future dispatch may only map this type to the fixed local
ceremony-cancellation transition.

### Secret transport

The codec is payload-agnostic and therefore cannot classify a secret by
itself. Callers are restricted to the public hello contract; tests and review
must reject any integration that places private keys, roots or tokens here.

## Residual risks

- denial of service by corrupting or withholding a frame;
- a caller bypassing domain validation after decode;
- incorrect lifecycle management of the decoder-owned view;
- compromised display or physical input during later confirmation;
- no physical ESP32-S3 execution evidence yet.

These risks prevent this framing layer from being treated as authentication or
production provisioning.
