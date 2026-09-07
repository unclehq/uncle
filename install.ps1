# Windows installer: GitHub source -> hash-pinned Scoop package.
[CmdletBinding()]
param(
    [string]$Repo = 'unclehq/uncle',
    [string]$Ref = 'main',
    [string]$SourceDir = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if ($Repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' -or $Repo.Contains('..')) { throw 'Invalid GitHub repository.' }
if ($Ref -notmatch '^[A-Za-z0-9][A-Za-z0-9_./-]*$' -or $Ref.Contains('..')) { throw 'Invalid GitHub ref.' }
if ($env:OS -ne 'Windows_NT') { throw 'Use install.sh on macOS or Linux.' }
if ($SourceDir) {
    $SourceDir = (Resolve-Path $SourceDir).Path
    if (!(Test-Path (Join-Path $SourceDir 'packaging/windows/scoop.json'))) { throw 'Not an Uncle source checkout.' }
}
Write-Host "Installer: Scoop; source: $Repo ($Ref)"
if ($DryRun) { return }
if (!(Get-Command scoop -ErrorAction SilentlyContinue)) {
    throw 'Install Scoop from https://scoop.sh in a normal user PowerShell, then rerun install.ps1.'
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$work = Join-Path ([IO.Path]::GetTempPath()) ('uncle-install-' + [Guid]::NewGuid().ToString('N'))
$scoopRoot = if ($env:SCOOP) { $env:SCOOP } else { Join-Path $HOME 'scoop' }
New-Item -ItemType Directory -Path $work | Out-Null
try {
    if ($SourceDir) {
        # Local packages use the same allowlist as the Debian/Homebrew builder.
        $source = $SourceDir
        $archive = Join-Path $work 'uncle.zip'
        # Scoop's 7-Zip extraction moves contents up in place. The wrapper
        # must not share a name with the launcher file inside it.
        $stage = Join-Path $work 'uncle-package'
        New-Item -ItemType Directory -Path $stage | Out-Null
        $names = @('uncle','uncle_tui.py','scripts','prompts','lib','OUTPUT_RULES.md','README.md','uncle.png','LICENSE','VERSION','packaging','install.sh','install.ps1','Formula')
        foreach ($name in $names) {
            $item = Join-Path $source $name
            if (!(Test-Path $item)) { throw "Missing payload: $name" }
            $links = @(Get-Item $item; Get-ChildItem $item -Recurse -Force) |
                Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
            if ($links) { throw "Symlink/junction in package input: $name" }
            Copy-Item $item $stage -Recurse
        }
        Get-ChildItem $stage -Directory -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force
        Get-ChildItem $stage -File -Recurse -Filter *.pyc | Remove-Item -Force
        Compress-Archive -Path $stage -DestinationPath $archive
        # Keep the local archive alive for Scoop's future reinstall/cache lookup.
        $localCache = Join-Path $scoopRoot 'cache\uncle-source'
        New-Item -ItemType Directory -Force $localCache | Out-Null
        $version = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
        $saved = Join-Path $localCache "uncle-$version.zip"
        Copy-Item $archive $saved
        $url = [Uri]::new($saved, [UriKind]::Absolute).AbsoluteUri
        $extractDir = 'uncle-package'
        $version = '0.0.0-local' + $version
    } else {
        $headers = @{ 'User-Agent' = 'uncle-installer'; 'Accept' = 'application/vnd.github+json' }
        $encodedRef = [Uri]::EscapeDataString($Ref)
        $commit = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/$Repo/commits/$encodedRef"
        $sha = [string]$commit.sha
        if ($sha -notmatch '^[a-f0-9]{40}$') { throw 'GitHub did not return a commit SHA.' }
        $url = "https://github.com/$Repo/archive/$sha.zip"
        $archive = Join-Path $work 'uncle.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive
        Expand-Archive -Path $archive -DestinationPath $work
        $extractDir = ($Repo.Split('/')[1]) + '-' + $sha
        $source = Join-Path $work $extractDir
        $baseVersion = (Get-Content (Join-Path $source 'VERSION') -Raw).Trim()
        if ($baseVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid VERSION in source.' }
        $date = ([DateTime]$commit.commit.committer.date).ToUniversalTime().ToString('yyyyMMddHHmmss')
        $version = $baseVersion + '-git' + $date + '.' + $sha.Substring(0,12)
    }
    $manifest = Get-Content (Join-Path $source 'packaging/windows/scoop.json') -Raw | ConvertFrom-Json
    $manifest.version = $version
    $manifest.url = $url
    $manifest.hash = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest.extract_dir = $extractDir
    # A generated local bucket gives Scoop normal install/update/uninstall
    # ownership. It has no remote: rerunning this installer refreshes its pin.
    $bucket = Join-Path $scoopRoot 'buckets\uncle-github'
    $marker = Join-Path $bucket '.uncle-generated'
    if ((Test-Path $bucket) -and !(Test-Path $marker)) { throw 'Existing uncle-github bucket is not owned by this installer.' }
    New-Item -ItemType Directory -Force (Join-Path $bucket 'bucket') | Out-Null
    Set-Content $marker 'Generated by Uncle install.ps1' -Encoding ASCII
    $manifest | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $bucket 'bucket\uncle.json') -Encoding UTF8
    $installed = Join-Path $scoopRoot 'apps\uncle\current\install.json'
    if (Test-Path $installed) {
        $origin = Get-Content $installed -Raw | ConvertFrom-Json
        if ($origin.bucket -ne 'uncle-github') { throw 'Uncle is managed by a different Scoop source. Uninstall it explicitly before switching.' }
        & scoop update uncle --force
        $scoopOK = $?
    } else {
        & scoop install uncle-github/uncle
        $scoopOK = $?
    }
    if (!$scoopOK -or ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0)) {
        throw "Scoop failed (exit $LASTEXITCODE)."
    }
    Write-Host 'Uncle installed. Authenticate your agent CLIs, then run uncle in your project.'
} finally {
    Remove-Item $work -Recurse -Force
}
