param($Demo)
$ErrorActionPreference = 'Continue'
if ($Demo -notmatch '^[a-z0-9-]+$') { throw 'bad demo name' }
$cfg = Get-Content "demos/$Demo.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$WingetId = $cfg.winget_id
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
winget install --id $WingetId --silent --accept-package-agreements --accept-source-agreements 2>&1 | Tee-Object -Append $log
Log "winget exit $LASTEXITCODE; install seconds: $([int]((Get-Date) - $ti).TotalSeconds)"

# входные файлы и подготовка
foreach ($f in $cfg.inputs) { New-Item -ItemType Directory -Force C:\demo | Out-Null; Copy-Item "demos/inputs/$f" C:\demo\ -Recurse -Force; Log "input $f" }
foreach ($c in $cfg.pre) { Log "pre: $c"; try { Invoke-Expression $c } catch { Log "pre failed: $_" } }

# ffmpeg и python
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { choco install ffmpeg -y --no-progress | Out-Null }
python -m pip install -q pywinauto pillow 2>&1 | Out-Null

python scripts/run_demo.py "demos/$Demo.json" 2>&1 | Tee-Object -Append $log
Log "total seconds: $([int]((Get-Date) - $t0).TotalSeconds)"
