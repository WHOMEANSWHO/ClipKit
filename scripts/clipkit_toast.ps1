param(
    [string]$Title = "Clip",
    [string]$Message = "Saved",
    [switch]$Toast,
    [switch]$Popup
)

$ErrorActionPreference = "Stop"
$Aumid = "ClipKit.Desktop"

function Xml-Escape([string]$text) {
    if ($null -eq $text) { return "" }
    return ($text.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;").Replace('"', "&quot;"))
}

function Register-ClipKitToastApp {
    $idPath = "HKCU:\Software\Classes\AppUserModelId\$Aumid"
    if (-not (Test-Path $idPath)) {
        New-Item -Path $idPath -Force | Out-Null
    }
    New-ItemProperty -Path $idPath -Name "DisplayName" -Value "ClipKit" -PropertyType String -Force | Out-Null
    $notifyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\$Aumid"
    if (-not (Test-Path $notifyPath)) {
        New-Item -Path $notifyPath -Force | Out-Null
    }
    New-ItemProperty -Path $notifyPath -Name "Enabled" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $notifyPath -Name "ShowInActionCenter" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $notifyPath -Name "AllowContentAboveLock" -Value 1 -PropertyType DWord -Force | Out-Null
}

function Show-WindowsToast([string]$heading, [string]$body) {
    $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    $null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime]

    $lines = @($body -split "@@") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    $textXml = "<text>" + (Xml-Escape $heading) + "</text>"
    foreach ($line in $lines) {
        $textXml += "<text>" + (Xml-Escape $line) + "</text>"
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
    $toast.ExpirationTime = [DateTimeOffset]::Now.AddSeconds(6)

    $notifiers = @(
        $Aumid,
        '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    )
    foreach ($id in $notifiers) {
        try {
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show($toast)
            return $true
        } catch {
            continue
        }
    }
    return $false
}

function Show-FormToast([string]$heading, [string]$body) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form = New-Object System.Windows.Forms.Form
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.BackColor = [System.Drawing.Color]::FromArgb(11, 19, 38)
    $form.Width = 420
    $form.Height = 108
    $form.Left = $screen.X + $screen.Width - $form.Width - 24
    $form.Top = $screen.Y + 24

    $accent = New-Object System.Windows.Forms.Panel
    $accent.BackColor = [System.Drawing.Color]::FromArgb(79, 70, 229)
    $accent.Dock = [System.Windows.Forms.DockStyle]::Left
    $accent.Width = 8
    $form.Controls.Add($accent)

    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text = $heading
    $titleLabel.ForeColor = [System.Drawing.Color]::FromArgb(195, 192, 255)
    $titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
    $titleLabel.AutoSize = $true
    $titleLabel.Left = 22
    $titleLabel.Top = 14
    $form.Controls.Add($titleLabel)

    $msgLabel = New-Object System.Windows.Forms.Label
    $msgLabel.Text = $body.Replace("@@", [Environment]::NewLine)
    $msgLabel.ForeColor = [System.Drawing.Color]::FromArgb(199, 196, 216)
    $msgLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10)
    $msgLabel.AutoSize = $false
    $msgLabel.Left = 22
    $msgLabel.Top = 44
    $msgLabel.Width = 380
    $msgLabel.Height = 48
    $form.Controls.Add($msgLabel)

    $form.Show()
    $form.BringToFront()
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.ElapsedMilliseconds -lt 2800) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 40
    }
    $form.Close()
    $form.Dispose()
}

try {
    if ($Toast) {
        Register-ClipKitToastApp
    }
} catch { }

if ($Toast) {
    try {
        $null = Show-WindowsToast $Title $Message
    } catch { }
}

if ($Popup) {
    Show-FormToast $Title $Message
}
