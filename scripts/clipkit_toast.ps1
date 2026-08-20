param(
    [string]$Title = "Clip saved",
    [string]$Message = "",
    [switch]$Toast,
    [switch]$Popup
)

$ErrorActionPreference = "Continue"
$logPath = Join-Path $PSScriptRoot "clip-saved.log"
$lockPath = Join-Path $PSScriptRoot "clip-saved.lock"

if (Test-Path -LiteralPath $lockPath) {
    try {
        $age = (Get-Date) - (Get-Item -LiteralPath $lockPath).LastWriteTime
        if ($age.TotalSeconds -lt 2) {
            exit 0
        }
    } catch { }
}
try {
    Set-Content -LiteralPath $lockPath -Value (Get-Date -Format "o") -Encoding UTF8
} catch { }

function Write-ClipLog([string]$text) {
    try {
        $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text
        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    } catch { }
}

function Xml-Escape([string]$text) {
    if ($null -eq $text) { return "" }
    return ($text.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;").Replace('"', "&quot;"))
}

function Show-WindowsToast([string]$heading, [string]$body) {
    $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    $null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime]
    $textXml = "<text>" + (Xml-Escape $heading) + "</text>"
    if ($body) {
        $textXml += "<text>" + (Xml-Escape $body) + "</text>"
    }
    $xmlText = @"
<toast duration="short">
  <audio silent="true" />
  <visual>
    <binding template="ToastGeneric">
      $textXml
    </binding>
  </visual>
</toast>
"@
    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xmlText)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
    $toast.ExpirationTime = [DateTimeOffset]::Now.AddSeconds(5)
    $ids = @(
        "ClipKit.Clips",
        '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    )
    foreach ($id in $ids) {
        try {
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show($toast)
            Write-ClipLog ("Toast shown via " + $id)
            return $true
        } catch { }
    }
    return $false
}

function Show-MedalPopup([string]$heading) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    if (-not ("ClipKitNoActivateForm" -as [type])) {
        $code = @"
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public class ClipKitNoActivateForm : Form {
    const int WS_EX_NOACTIVATE = 0x08000000;
    const int WS_EX_TOPMOST = 0x00000008;
    const int WS_EX_TOOLWINDOW = 0x00000080;
    const int WS_EX_TRANSPARENT = 0x00000020;
    const uint SWP_NOSIZE = 0x0001;
    const uint SWP_NOMOVE = 0x0002;
    const uint SWP_NOACTIVATE = 0x0010;
    const uint SWP_SHOWWINDOW = 0x0040;
    static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);

    [DllImport("user32.dll")]
    static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter,
        int X, int Y, int cx, int cy, uint uFlags);

    protected override bool ShowWithoutActivation { get { return true; } }

    protected override CreateParams CreateParams {
        get {
            CreateParams cp = base.CreateParams;
            cp.ExStyle |= WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT;
            return cp;
        }
    }

    public void ShowPassive() {
        Show();
        SetWindowPos(Handle, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
    }
}
"@
        $refs = @(
            ([System.Windows.Forms.Form].Assembly.Location),
            "System.dll"
        )
        Add-Type -TypeDefinition $code -ReferencedAssemblies $refs -ErrorAction Stop
    }

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form = New-Object ClipKitNoActivateForm
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.ShowInTaskbar = $false
    $form.TopMost = $true
    $form.BackColor = [System.Drawing.Color]::FromArgb(18, 18, 18)
    $form.Width = 280
    $form.Height = 72
    $form.Left = $screen.X + $screen.Width - $form.Width - 28
    $form.Top = $screen.Y + 28

    $accent = New-Object System.Windows.Forms.Panel
    $accent.BackColor = [System.Drawing.Color]::FromArgb(46, 204, 113)
    $accent.Dock = [System.Windows.Forms.DockStyle]::Left
    $accent.Width = 6
    $form.Controls.Add($accent)

    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text = $heading.ToUpper()
    $titleLabel.ForeColor = [System.Drawing.Color]::White
    $titleLabel.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 14, [System.Drawing.FontStyle]::Bold)
    $titleLabel.AutoSize = $true
    $titleLabel.Left = 22
    $titleLabel.Top = 22
    $form.Controls.Add($titleLabel)

    $form.ShowPassive()
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.ElapsedMilliseconds -lt 2200) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 40
    }
    $form.Close()
    $form.Dispose()
    Write-ClipLog ("Popup shown: " + $heading)
}

$didPopup = $false
$didToast = $false
if ($Popup -or -not $Toast) {
    try {
        Show-MedalPopup $Title
        $didPopup = $true
    } catch {
        Write-ClipLog ("Popup failed: " + $_.Exception.Message)
    }
}

if ($Toast -or -not $didPopup) {
    try {
        $didToast = Show-WindowsToast $Title $Message
    } catch {
        Write-ClipLog ("Toast failed: " + $_.Exception.Message)
    }
}

if (-not $didPopup -and -not $didToast) {
    Write-ClipLog "No clip-saved notice could be shown"
    exit 1
}
