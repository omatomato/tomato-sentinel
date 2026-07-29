# Security policy

Tomato Sentinel is pre-release software and must not be used to protect
production environments or execute security operations.

## Reporting

Do not disclose suspected vulnerabilities, credentials, private camera
addresses, captured identifiers or exploit details in a public issue.

The repository is public. Do not post sensitive reports in issues or
discussions. Use GitHub's private vulnerability-reporting interface when it is
available for this repository; otherwise contact the repository owner
privately through GitHub before sharing details. A dedicated security contact
and coordinated-disclosure process remain release blockers.

## Security baseline

- Deny by default.
- Never execute model-generated free-form actions.
- Never expose or test third-party targets.
- Never commit secrets or production evidence.
- Treat all upstream code and binary artifacts as untrusted until reviewed.
- Keep R3 functionality outside the executable product.
- Use only synthetic, recorded-with-consent or owned test data.

## Supported versions

No released version is currently supported. Security fixes on the default
branch receive priority during the foundation phase.
