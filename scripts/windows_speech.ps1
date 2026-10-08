param(
    [ValidateSet('voices', 'speak')][string]$Action = 'voices',
    [string]$RequestPath,
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Speech
if ($Action -eq 'voices') {
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $voices = @($synth.GetInstalledVoices() | Where-Object Enabled | ForEach-Object {
            @{ id = $_.VoiceInfo.Name; label = $_.VoiceInfo.Name; language = $_.VoiceInfo.Culture.Name }
        })
        ConvertTo-Json -InputObject $voices -Depth 4 -Compress
    } finally { $synth.Dispose() }
    exit 0
}
if (-not $RequestPath -or -not $OutputPath) { throw 'RequestPath and OutputPath are required.' }
$request = Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
# Handle progress in C# because callbacks run outside PowerShell's runspace.
Add-Type -ReferencedAssemblies System.Speech -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Speech.Synthesis;
using System.Speech.AudioFormat;
public class StudioSpeechBoundary {
    public string text;
    public int position;
    public int length;
    public double start;
}
public static class StudioWindowsSpeech {
    public static StudioSpeechBoundary[] Speak(string text, string voice, int rate, string output) {
        var words = new List<StudioSpeechBoundary>();
        using (var synth = new SpeechSynthesizer()) {
            synth.SelectVoice(voice);
            synth.Rate = rate;
            // System.Speech's SAPI progress clock uses 16 kHz for these desktop
            // voices. Render at the same rate; resampling here offsets events.
            synth.SetOutputToWaveFile(output, new SpeechAudioFormatInfo(16000, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
            synth.SpeakProgress += (sender, e) => {
                lock (words) {
                    words.Add(new StudioSpeechBoundary {
                        text = text.Substring(e.CharacterPosition, e.CharacterCount),
                        position = e.CharacterPosition, length = e.CharacterCount,
                        start = e.AudioPosition.TotalSeconds
                    });
                }
            };
            synth.Speak(text);
            synth.SetOutputToNull();
        }
        lock (words) { return words.ToArray(); }
    }
}
'@
$result = [StudioWindowsSpeech]::Speak([string]$request.text, [string]$request.voice, [int]$request.rate, $OutputPath)
ConvertTo-Json -InputObject @($result) -Depth 4 -Compress
