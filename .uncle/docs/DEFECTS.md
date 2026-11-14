# Defects

## None. Setup needed: provide a disposable Debian host or container with OCaml absent and passwordless sudo, then rerun MC-200.

- **Status:** BLOCKED-SETUP
- **Evidence:** `uname -s` printed Darwin. `command -v docker` printed nothing. `docker info` failed and the shell printed 'nodocker'.
- **Expected result:** Installation completes without requesting credentials or interactive confirmation; sudo and package installation remain non-interactive. If the required sandbox is unavailable, record BLOCKED-SETUP rather than passing this observation.
- **Actual result:** The sandbox is unavailable. The host is Darwin (macOS), not Debian. Docker is not installed and no container runtime responded. The observation was not performed.

## None. Setup action needed: provide a disposable Debian/Ubuntu sandbox (VM or container) with apt-get, passwordless sudo and OCaml absent, then rerun MC-300.

- **Status:** BLOCKED-SETUP
- **Evidence:** uname -s printed Darwin. `which` reported apt-get not found, ocaml not found and docker not found. Only /usr/bin/sudo exists.
- **Expected result:** The installer installs the mapped ocaml package without a password or interactive confirmation, records the outcome, and finishes within the 300-second deadline.
- **Actual result:** Not performed. The host is Darwin (macOS) with no apt-get, no ocaml, and no docker. A Debian sandbox with apt-get and passwordless sudo is unavailable.
