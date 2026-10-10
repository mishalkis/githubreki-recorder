param($WingetId, $Exe = '', [int]$Seconds = 15)
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force out | Out-Null
$log = 'out/log.txt'
function Log($m) { "$(Get-Date -f HH:mm:ss) $m" | Tee-Object -Append $log }
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public class U {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Ansi)] public struct DM {
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string n;
    public short ver, size, extra; public int fields;
    public int x, y, orient, fo; public short color, dup, yres, tt, coll;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string fn;
    public short log; public int bpp, w, h, flags, freq, a, b, c, d, e, f;
  }
  [DllImport("user32.dll")] public static extern bool EnumDisplaySettings(string d, int m, ref DM dm);
  [DllImport("user32.dll")] public static extern int ChangeDisplaySettings(ref DM dm, int f);
}
'@
function Shot($name) {
  $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $bmp.Save("out/$name"); Log "shot $name $($b.Width)x$($b.Height)"
}
$t0 = Get-Date
Shot '00_start.png'
Log "user=$env:USERNAME session=$env:SESSIONNAME interactive=$([Environment]::UserInteractive)"
Log "winget: $((Get-Command winget -ErrorAction SilentlyContinue).Source)"

# разрешение
$dm = New-Object U+DM; $dm.size = [Runtime.InteropServices.Marshal]::SizeOf($dm)
[U]::EnumDisplaySettings($null, -1, [ref]$dm) | Out-Null
Log "current res $($dm.w)x$($dm.h)"
if ($dm.w -lt 1920) {
  $dm.w = 1920; $dm.h = 1080; $dm.fields = 0x80000 -bor 0x100000
  Log "ChangeDisplaySettings -> $([U]::ChangeDisplaySettings([ref]$dm, 0)) (0 = ok)"
  Start-Sleep 2
  Log "res after: $([System.Windows.Forms.SystemInformation]::VirtualScreen.Size)"
}

# установка
$ti = Get-Date
if (Get-Command winget -ErrorAction SilentlyContinue) {
  winget install --id $WingetId --silent --accept-package-agreements --accept-source-agreements 2>&1 | Tee-Object -Append $log
  Log "winget exit $LASTEXITCODE"
} else { Log 'winget missing' }
Log "install seconds: $([int]((Get-Date) - $ti).TotalSeconds)"

# ffmpeg
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { choco install ffmpeg -y --no-progress | Out-Null }
$dur = $Seconds + 10
$ff = Start-Process ffmpeg -ArgumentList "-y -f gdigrab -framerate 30 -i desktop -t $dur -c:v libx264 -preset ultrafast -pix_fmt yuv420p out/demo.mp4" -PassThru -RedirectStandardError out/ffmpeg.log -WindowStyle Hidden
Start-Sleep 2

# запуск
if (-not $Exe) {
  $name = ($WingetId -split '\.')[-1]
  $lnk = Get-ChildItem "$env:ProgramData\Microsoft\Windows\Start Menu", "$env:APPDATA\Microsoft\Windows\Start Menu" -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | Where-Object Name -like "*$name*" | Select-Object -First 1
  $Exe = $lnk.FullName; Log "shortcut: $Exe"
}
$p = Start-Process $Exe -PassThru
Start-Sleep 8
Shot '01_launched.png'
Get-Process | Where-Object MainWindowHandle -ne 0 | ForEach-Object {
  Log "window: $($_.ProcessName) '$($_.MainWindowTitle)'"
  if ($_.ProcessName -like "*$(($WingetId -split '\.')[-1])*") { [U]::ShowWindow($_.MainWindowHandle, 3) | Out-Null; [U]::SetForegroundWindow($_.MainWindowHandle) | Out-Null }
}
Start-Sleep ([Math]::Max(1, $Seconds - 8))
Shot '02_later.png'
$ff.WaitForExit(($dur + 30) * 1000) | Out-Null
Log "ffmpeg exit $($ff.ExitCode); total seconds: $([int]((Get-Date) - $t0).TotalSeconds)"
