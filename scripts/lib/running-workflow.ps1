# Native Windows process command lines include arguments that MSYS ps omits.
$ErrorActionPreference = 'Stop'
try {
    foreach ($process in Get-CimInstance Win32_Process -ErrorAction Stop) {
        if (!$process.CommandLine) { continue }
        $parts = @([regex]::Matches($process.CommandLine, '"[^"]*"|[^\s"]+') | ForEach-Object { $_.Value.Trim('"') })
        if (!$parts.Count) { continue }
        $first = [IO.Path]::GetFileName($parts[0])
        $driver = '^(stagegate|change-workflow)\.sh$'
        if ($first -match $driver) { Write-Output $process.ProcessId; continue }
        if ($first -notmatch '^(bash|sh|zsh|dash)(\.exe)?$') { continue }
        # Only the script argument counts, never an editor/grep or a -c string.
        if ($parts.Count -lt 2) { continue }
        foreach ($arg in $parts[1..($parts.Count - 1)]) {
            if ($arg -eq '-c' -or $arg -eq '-lc') { break }
            if ($arg.StartsWith('-')) { continue }
            if ([IO.Path]::GetFileName($arg) -match $driver) { Write-Output $process.ProcessId }
            break
        }
    }
} catch {
    Write-Error "Cannot inspect running workflows: $_"
    exit 2
}
