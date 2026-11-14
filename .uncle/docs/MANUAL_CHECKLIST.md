# Manual checklist

### MC-200
- Exclusive resources: none
- Depends on: none
- Exact action: In a disposable hosted Debian sandbox with OCaml absent and passwordless sudo available, manually invoke `UNCLE_HOSTED=1 python3 scripts/lib/toolchain_install.py <commands> <record>`, substituting a commands file containing `ocaml -version` and a sandbox-local output path. Observe the terminal throughout installation for password, authentication, or package-confirmation prompts.
- Expected result: Installation completes without requesting credentials or interactive confirmation; sudo and package installation remain non-interactive. If the required sandbox is unavailable, record BLOCKED-SETUP rather than passing this observation.
- Actual result: 
- Status: NOT RUN

### MC-300
- Exclusive resources: sandbox:hosted-debian-package-state
- Depends on: none
- Exact action: In a disposable hosted Debian sandbox with OCaml absent, apt-get available and passwordless sudo enabled, manually invoke `UNCLE_HOSTED=1 python3 scripts/lib/toolchain_install.py <commands> <record>` using a commands file containing `ocaml -version` and a fresh record output path. Observe the live terminal interaction through completion; if the sandbox is unavailable, record BLOCKED-SETUP.
- Expected result: The installer installs the mapped ocaml package without requesting a password or interactive confirmation and records the installation outcome. Installation finishes within the shared 300-second deadline, allowing bounded process cleanup if a timeout occurs.
- Actual result: 
- Status: NOT RUN
