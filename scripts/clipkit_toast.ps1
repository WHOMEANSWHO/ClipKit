param(
    [string]$Title = "Clip saved",
    [string]$Message = "",
    [switch]$Toast,
    [switch]$Popup
)

$ErrorActionPreference = "Stop"

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
            return
        } catch { }
    }
}

function Show-MedalPopup([string]$heading) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    if (-not ("ClipKitNoActivateForm" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Windows.Forms;
public class ClipKitNoActivateForm : Form {
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override CreateParams CreateParams {
        get {
            CreateParams cp = base.CreateParams;
            cp.ExStyle |= 0x08000000;
            cp.ExStyle |= 0x00000008;
            cp.ExStyle |= 0x00000080;
            return cp;
        }
    }
}
"@
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

    $form.Show()
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.ElapsedMilliseconds -lt 2500) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 40
    }
    $form.Close()
    $form.Dispose()
}

if ($Toast) {
    try { Show-WindowsToast $Title $Message } catch { }
}

if ($Popup -or -not $Toast) {
    Show-MedalPopup $Title
}
