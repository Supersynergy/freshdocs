# Security

Freshdocs reads public documentation sources and stores indexed snippets in a local SQLite database.

## Supported Versions

Security fixes target the latest released version.

## Reporting

Report vulnerabilities privately through GitHub Security Advisories for:

https://github.com/Supersynergy/freshdocs/security/advisories/new

If advisories are not enabled yet, open a minimal issue without exploit details:

https://github.com/Supersynergy/freshdocs/issues

## Local Data

By default Freshdocs stores data in:

```text
~/.freshdocs/
```

Use `FRESHDOCS_HOME`, `FRESHDOCS_REGISTRY`, `FRESHDOCS_STATE`, and `FRESHDOCS_DB` to isolate data for tests, private projects, or CI.

## Network Boundary

`freshdocs sync` performs network fetches. `freshdocs context` can run from the local cache after docs are synced.

Freshdocs does not send project source code to a hosted service.
