# Packaging and GitHub installation

`install.sh` detects macOS, apt-based Linux (including WSL), and Windows Git
Bash/MSYS/Cygwin. Native PowerShell users run `install.ps1`. Both download from
`unclehq/uncle` on GitHub by default and support a selected repository and ref.
Install Homebrew or Scoop first. Do not run Homebrew as root. Linux installation
uses root or sudo for apt; package construction itself does not require root.

## Homebrew

`Formula/uncle.rb` is a HEAD-only formula that works as a GitHub tap:

```sh
brew tap unclehq/uncle https://github.com/unclehq/uncle.git
brew install --HEAD unclehq/uncle/uncle
```

The bootstrap instead generates a stable formula in the local
`unclehq/github-install` tap. Its URL contains the resolved commit and its hash
matches the archive fetched over HTTPS. Rerunning the bootstrap rebuilds that
formula and installs/reinstalls it. Local-source installs keep their archive in
the generated tap so Homebrew can reinstall it after temporary files are gone.

The installer refuses to overwrite a pre-existing generated-tap name unless it
has the installer's ownership marker. The template has no placeholder release
URL or all-zero checksum. Formula generation is in
`scripts/install/build-package.py`; package dependencies are in the formula.

## Debian and Ubuntu

The bootstrap fetches a detached GitHub revision, builds an architecture-neutral
`.deb`, and uses `apt-get install` on its absolute path. Apt resolves the
runtime dependencies declared in `packaging/debian/control`. This is a local
Debian package installation, not a published apt repository.

To build a package without installing it (requires Python 3 and `dpkg-deb`):

```sh
python3 scripts/install/build-package.py deb --source "$PWD" --output /tmp/uncle-packages
sudo apt install /tmp/uncle-packages/uncle_*_all.deb
```

Files live under `/usr/lib/uncle`; `/usr/bin/uncle` links to its launcher.
The package records root ownership without requiring a privileged build.
`VERSION` supplies the base version; the Git commit timestamp and abbreviated
SHA identify development builds. `--version 1.2.3` sets a package release version.
Use `sudo apt remove uncle` to uninstall. Updates come from rerunning the
bootstrap; apt cannot discover newer GitHub commits on its own.

## Windows / Scoop

`install.ps1` resolves a GitHub ref using the public API, downloads that commit's
ZIP, computes its SHA-256, and fills `packaging/windows/scoop.json`. It writes a
local `uncle-github` Scoop bucket and installs or updates the package through
Scoop. API rate limits or failed downloads stop before the installed application
is changed. The bucket name is protected by an ownership marker.

The package declares Scoop dependencies for Git, Python, jq, and gh. Its
PowerShell shim locates Scoop's Git Bash and Python, preserves the calling
project directory, and passes arguments/exit codes through. The private
`python3` shell wrapper avoids relying on Windows Python executable aliases.
Curses is optional; install `windows-curses` into Scoop Python for the full UI.
Agent CLIs still need to be available to Git Bash and authenticated separately.

`-SourceDir` packages a local checkout, retaining its ZIP in Scoop's
`cache/uncle-source` directory. Rerun the installer to change refs or update;
`scoop uninstall uncle` removes the application. No WinGet listing is required.

## Payload and tests

Local builds use an explicit payload list and reject symlinks. They exclude
Git metadata, `.uncle` state, unrelated root files, and Python bytecode. GitHub
archives represent repository contents at the selected commit; do not commit
secrets or local workflow state. Package builds never modify project approvals.

Run portable checks:

```sh
bash -n install.sh
bash -n scripts/install/homebrew.sh
ruby -c Formula/uncle.rb
python3 scripts/tests/install-test.py
```

On Windows, also run `scripts/tests/install-windows-test.ps1`. Tests use temporary
files and fake package managers; the Debian extraction test uses real
`dpkg-deb` when available. `.github/workflows/installers.yml` additionally
installs the local checkout on macOS, Ubuntu, and Windows, tests the installed
launcher outside the checkout, and uploads the Debian build as a CI artifact.
Native jobs must pass before treating a new installer revision as validated on
those platforms. The workflow does not publish a GitHub release or submit a
package to a public registry.
