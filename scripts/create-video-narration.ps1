$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$narrationDir = Join-Path $root 'frontend/videos-raw/narration'
New-Item -ItemType Directory -Path $narrationDir -Force | Out-Null

$clips = @(
  @{
    Name = '01-landing-page-the-pitch-logged-out'
    Lines = @(
      'Welcome to Bootcamp Connect, a private network for people learning together.'
      'Software developers and business developers can find collaborators from their own course.'
      'Create a profile, see why people match, and start a conversation only when both sides agree.'
    )
  },
  @{
    Name = '02-registration-login-and-magic-link'
    Lines = @(
      'Getting started takes just a name, email address and password.'
      'Complete your role and add a skill before the matching area unlocks.'
      'You can return with your password or request a secure sign-in link by email.'
    )
  },
  @{
    Name = '03-profile-building-one-from-nothing'
    Lines = @(
      'A useful profile starts with the kind of work you do and the skills you bring.'
      'Add interests, a short introduction and the kind of partner you hope to find.'
      'These details help explain each match, so you can decide whether to reach out.'
    )
  },
  @{
    Name = '04-matching-and-search'
    Lines = @(
      'Matches are ranked around shared skills, interests and goals.'
      'Each card shows the reason for the match, so the ranking is easy to understand.'
      'Search by name or use the filters to narrow the cohort, then send a connection request.'
    )
  },
  @{
    Name = '05-connection-requests-two-windows'
    Lines = @(
      'A connection begins with a request and a clear choice for the person receiving it.'
      'They can accept or decline. Until they accept, there is no conversation to open.'
      'Once both people agree, the connection is mutual and messaging becomes available.'
    )
  },
  @{
    Name = '07-live-messaging-two-windows'
    Lines = @(
      'Here, two connected people are using the same private thread in separate windows.'
      'New messages arrive live without refreshing the page, and unread counts update with the thread.'
      'The conversation is saved, so its history is still available after a reload.'
    )
  },
  @{
    Name = '08-notifications'
    Lines = @(
      'The notification badge keeps new activity visible as you move around the app.'
      'Open an item to go straight to the related connection, message or project.'
      'Mark everything read to clear the count while keeping the notification history.'
    )
  },
  @{
    Name = '09-project-ideas-board'
    Lines = @(
      'Business developers can post project ideas and describe the skills they need.'
      'Software developers can search the board, open a project and express interest.'
      'The author can see who is interested and how many people want to help.'
    )
  },
  @{
    Name = '10-admin-screens'
    Lines = @(
      'The admin area provides a protected view of accounts and platform activity.'
      'Authorized admins can manage shared courses, skills and interests.'
      'An audit log records administrative changes for later review.'
    )
  }
)

function Format-SrtTime([double]$Seconds) {
  $milliseconds = [int][math]::Round($Seconds * 1000)
  $hours = [math]::Floor($milliseconds / 3600000)
  $milliseconds %= 3600000
  $minutes = [math]::Floor($milliseconds / 60000)
  $milliseconds %= 60000
  $seconds = [math]::Floor($milliseconds / 1000)
  $milliseconds %= 1000
  return ('{0:00}:{1:00}:{2:00},{3:000}' -f $hours, $minutes, $seconds, $milliseconds)
}

function Get-WaveDuration([string]$Path) {
  $stream = [System.IO.File]::OpenRead($Path)
  $reader = [System.IO.BinaryReader]::new($stream)
  try {
    [void]$reader.ReadBytes(12) # RIFF header and WAVE marker
    $byteRate = 0
    $dataSize = 0
    while ($stream.Position + 8 -le $stream.Length) {
      $chunk = [System.Text.Encoding]::ASCII.GetString($reader.ReadBytes(4))
      $size = $reader.ReadInt32()
      if ($chunk -eq 'fmt ') {
        [void]$reader.ReadBytes(8) # format, channels, sample rate
        $byteRate = $reader.ReadInt32()
        [void]$stream.Seek($size - 12, [System.IO.SeekOrigin]::Current)
      } elseif ($chunk -eq 'data') {
        $dataSize = $size
        break
      } else {
        [void]$stream.Seek($size, [System.IO.SeekOrigin]::Current)
      }
      if ($size % 2) { [void]$stream.Seek(1, [System.IO.SeekOrigin]::Current) }
    }
    if ($byteRate -le 0 -or $dataSize -le 0) { throw "Could not read WAV duration: $Path" }
    return $dataSize / $byteRate
  } finally {
    $reader.Dispose()
    $stream.Dispose()
  }
}

$voice = New-Object -ComObject SAPI.SpVoice
$hazel = $voice.GetVoices() | Where-Object { $_.GetDescription() -like '*Hazel*English (Great Britain)*' } | Select-Object -First 1
if (-not $hazel) { throw 'The Microsoft Hazel British English SAPI voice is not installed.' }
$voice.Voice = $hazel
$voice.Rate = -1
$voice.Volume = 92

foreach ($clip in $clips) {
  $wav = Join-Path $narrationDir ($clip.Name + '.wav')
  $srt = Join-Path $narrationDir ($clip.Name + '.srt')
  $fileStream = New-Object -ComObject SAPI.SpFileStream
  $fileStream.Open($wav, 3, $false) # SSFMCreateForWrite
  $voice.AudioOutputStream = $fileStream
  [void]$voice.Speak(($clip.Lines -join ' '), 0)
  $fileStream.Close()

  $duration = Get-WaveDuration $wav
  $weights = @($clip.Lines | ForEach-Object { [regex]::Matches($_, '\S+').Count })
  $totalWords = ($weights | Measure-Object -Sum).Sum
  $pauseAllowance = [math]::Min(0.55 * ($clip.Lines.Count - 1), $duration * 0.08)
  $speechDuration = $duration - $pauseAllowance
  $at = 0.0
  $entries = for ($i = 0; $i -lt $clip.Lines.Count; $i++) {
    $segment = $speechDuration * $weights[$i] / $totalWords
    if ($i -gt 0) { $at += $pauseAllowance / ($clip.Lines.Count - 1) }
    $start = $at
    $at += $segment
    "{0}`r`n{1} --> {2}`r`n{3}`r`n" -f ($i + 1), (Format-SrtTime $start), (Format-SrtTime $at), $clip.Lines[$i]
  }
  [System.IO.File]::WriteAllText($srt, ($entries -join "`r`n"), [System.Text.UTF8Encoding]::new($false))
  Write-Host ('Narrated {0} ({1:N1}s)' -f $clip.Name, $duration)
}

$voice = $null
[GC]::Collect()
[GC]::WaitForPendingFinalizers()
