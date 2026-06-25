# Security Policy

## Supported versions

Ratebook is pre-release. There are no tagged releases yet, so security fixes
land on `main` and only the latest commit on `main` is supported. If you are
running Ratebook, track `main` and update before reporting — a finding may
already be fixed.

| Version            | Supported |
| ------------------ | --------- |
| Latest `main`      | ✅        |
| Older commits      | ❌        |

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue, pull
request, or discussion for anything that could expose users to risk.

Use **GitHub Private Vulnerability Reporting**:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Fill in the advisory form with as much detail as you can: affected package
   (e.g. `ratebook`, `ratebook-data`, `ratebook-mcp`, `ratebook-ts`,
   `ratebook-homeassistant`), the version/commit you tested, reproduction steps,
   and the impact you observed.

If the "Report a vulnerability" button is not visible, the maintainer (@cbetz)
needs to enable Private Vulnerability Reporting for the repository — please open
a normal issue asking for it to be turned on (without including any sensitive
details), and we will enable it so you can file the report privately.

### What to expect

- **Acknowledgement** within 7 days that the report was received.
- An initial **assessment** (severity, whether it reproduces, intended fix
  direction) within 14 days.
- We will keep you updated as a fix is developed, and we will credit you in the
  advisory once it is published, unless you ask us not to.

Because this is a volunteer-maintained pre-release project, these are
good-faith targets rather than contractual guarantees. Thank you for reporting
responsibly.

## Why input handling matters here

Two Ratebook components run **inside the user's trust boundary** and process
input the user did not necessarily author:

- **`ratebook-mcp`** — the MCP server runs as a tool that an LLM agent can call,
  with arguments the model (and ultimately untrusted content the model has read)
  supplies. It also reads tariff data files.
- **`ratebook-homeassistant`** — the Home Assistant integration runs in the
  user's home automation host and consumes tariff data and configuration.

Reports about input handling in these components are especially valuable — for
example: a crafted MCP tool argument that triggers unexpected file access,
resource exhaustion, or code paths it should not reach; malformed tariff or
URDB data that crashes or hangs the engine; a parsing path that could be coerced
into reading or writing outside its intended scope; or any way the data plant
(`ratebook-data`) could be steered into fetching or writing somewhere it
shouldn't. The rate engine itself is deterministic and offline, so engine
findings tend to be about robustness against malformed input rather than network
exposure.
