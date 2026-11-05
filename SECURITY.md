# Security policy

- Supported: the latest release tag and the `main` branch. Older tags are not patched; pull by digest and
  move forward.
- Report a vulnerability in this repository (Dockerfile, workflows, scripts) privately through GitHub
  Security Advisories for `geminishkv/cdxgen-distroless`. Do not open a public issue for it.
- Vulnerabilities in cdxgen itself belong to <https://github.com/CycloneDX/cdxgen/security>; in the
  distroless base - to <https://github.com/GoogleContainerTools/distroless>.
- Before every release the security pipeline scans a linux/amd64 build of the same Dockerfile and pinned
  inputs (Trivy, severity gate on Critical and High with a fix available). Published images are signed with
  cosign and ship SBOM and provenance attestations; the GHCR image also carries a signed GitHub build
  provenance attestation. Verification commands are in README.md.
