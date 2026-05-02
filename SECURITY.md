# Security Policy

## Supported versions

Security fixes are prioritized for the current default development branch (`main` or `master`, depending on repository configuration).

Older commits, forks, and unpublished local modifications should be treated as unsupported unless maintainers explicitly state otherwise.

## Reporting a vulnerability

Please do not open public GitHub issues for suspected security problems.

Preferred reporting path:

1. Use GitHub's private vulnerability reporting for this repository if it is enabled.
2. If private reporting is not available, contact a maintainer through a non-public channel and include `arclink` in the subject or opening line.

Please include as much of the following as you can:

- A clear description of the issue and affected component(s)
- Reproduction steps or a proof of concept
- Impact assessment, including any privilege or data exposure concerns
- Version, branch, or commit information
- Any suggested mitigation if you already have one

## Response expectations

- We aim to acknowledge new reports within 5 business days.
- We aim to provide status updates as investigation progresses.
- We prefer coordinated disclosure after a fix or mitigation is available.

## Scope guidance

The most security-sensitive areas in this repository are likely to include:

- Installer and bootstrap scripts
- Service definitions and runtime configuration
- Authentication, access, and secret-handling paths
- External integrations and webhook surfaces

If you are unsure whether something is security-sensitive, report it privately anyway.
