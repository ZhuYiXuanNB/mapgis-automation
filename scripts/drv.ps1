param(
  [string]$Proc = "W60_DTM",
  [string]$Steps = "wins"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
if (-not ("MgX" -as [type])) {
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public class MgX {
  [DllImport("user32.dll")] public static extern IntPtr GetMenu(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetSubMenu(IntPtr h, int pos);
  [DllImport("user32.dll")] public static extern int GetMenuItemCount(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetMenuItemRect(IntPtr hwnd, IntPtr hmenu, uint item, out RECT r);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetMenuStringW(IntPtr h, uint id, StringBuilder s, int n, uint flags);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll", EntryPoint="SendMessageW", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessageStr(IntPtr h, uint msg, IntPtr w, string l);
  [DllImport("user32.dll", EntryPoint="SendMessageW", CharSet=CharSet.Unicode)] public static extern IntPtr SendMsgSB(IntPtr h, uint msg, IntPtr w, StringBuilder l);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public struct POINT { public int X, Y; }
  public static string Text(IntPtr h) { var s=new StringBuilder(512); GetWindowTextW(h,s,512); return s.ToString(); }
  public static string Cls(IntPtr h) { var s=new StringBuilder(256); GetClassNameW(h,s,256); return s.ToString(); }
  public static void Click(int x, int y) {
    SetCursorPos(x, y); System.Threading.Thread.Sleep(80);
    mouse_event(0x0002,0,0,0,IntPtr.Zero); System.Threading.Thread.Sleep(40);
    mouse_event(0x0004,0,0,0,IntPtr.Zero); System.Threading.Thread.Sleep(120);
  }
  public static void RClick(int x, int y) {
    SetCursorPos(x, y); System.Threading.Thread.Sleep(80);
    mouse_event(0x0008,0,0,0,IntPtr.Zero); System.Threading.Thread.Sleep(50);
    mouse_event(0x0010,0,0,0,IntPtr.Zero); System.Threading.Thread.Sleep(150);
  }
  public static IntPtr Find(IntPtr parent, int id) {
    IntPtr f = IntPtr.Zero;
    EnumChildWindows(parent, (h,l) => { if (GetDlgCtrlID(h)==id) { f=h; return false; } return true; }, IntPtr.Zero);
    return f;
  }
  public static IntPtr FindEdit(IntPtr parent, int id) {
    IntPtr f = IntPtr.Zero;
    EnumChildWindows(parent, (h,l) => { if (GetDlgCtrlID(h)==id && Cls(h).Contains("Edit")) { f=h; return false; } return true; }, IntPtr.Zero);
    return f;
  }
  public static List<IntPtr> TopWindows(uint pid) {
    var l = new List<IntPtr>();
    EnumWindows((h,x) => { uint p; GetWindowThreadProcessId(h, out p); if (p==pid && IsWindowVisible(h)) l.Add(h); return true; }, IntPtr.Zero);
    return l;
  }
  public static IntPtr FindByTitle(uint pid, string sub) {
    IntPtr f = IntPtr.Zero;
    EnumWindows((h,l) => { uint p; GetWindowThreadProcessId(h, out p);
      if (p==pid && IsWindowVisible(h) && Text(h).Contains(sub)) { f=h; return false; }
      return true; }, IntPtr.Zero);
    return f;
  }
  public static List<string> Children(IntPtr parent) {
    var l = new List<string>();
    EnumChildWindows(parent, (h,x) => {
      RECT r; GetWindowRect(h, out r);
      l.Add(string.Format("hwnd={0} id={1} cls={2} rect={3},{4},{5},{6} text=[{7}]",
        h, GetDlgCtrlID(h), Cls(h), r.Left, r.Top, r.Right-r.Left, r.Bottom-r.Top, Text(h).Trim()));
      return true; }, IntPtr.Zero);
    return l;
  }
  public static void Shot(IntPtr h, string path) {
    RECT r; GetWindowRect(h, out r);
    int w=r.Right-r.Left, hh=r.Bottom-r.Top;
    if(w<=0||hh<=0) return;
    var b = new Bitmap(w,hh,PixelFormat.Format24bppRgb);
    using(var g=Graphics.FromImage(b)){ IntPtr dc=g.GetHdc(); PrintWindow(h,dc,2); g.ReleaseHdc(dc); }
    b.Save(path, ImageFormat.Png); b.Dispose();
  }
  public static int ComboCount(IntPtr h) { return (int)SendMessage(h, 0x0146, IntPtr.Zero, IntPtr.Zero); }
  public static string ComboText(IntPtr h, int i) { var sb=new StringBuilder(512); SendMsgSB(h,0x0148,(IntPtr)i,sb); return sb.ToString(); }
  public static string ListItemText(IntPtr h, int i) { var sb=new StringBuilder(512); SendMsgSB(h,0x0189,(IntPtr)i,sb); return sb.ToString(); }
}
"@ -ReferencedAssemblies System.Drawing
}

function Get-Target([string]$pat) {
  $p = Get-Process | Where-Object { $_.ProcessName -match $pat -and $_.MainWindowHandle -ne 0 }
  if (-not $p) { throw "no window for $pat" }
  return $p | Sort-Object StartTime -Descending | Select-Object -First 1
}

$t = Get-Target $Proc
$h = $t.MainWindowHandle
$script:Dlg = [IntPtr]::Zero
function Get-Dlg { if ($script:Dlg -ne [IntPtr]::Zero) { return $script:Dlg } else { return $h } }

foreach ($step in ($Steps -split ";")) {
  $s = $step.Trim(); if ($s -eq "") { continue }
  $i = $s.IndexOf(":"); $act = if ($i -ge 0) { $s.Substring(0,$i) } else { $s }; $arg = if ($i -ge 0) { $s.Substring($i+1) } else { "" }
  switch ($act) {
    "wins"    { foreach($w in [MgX]::TopWindows([uint32]$t.Id)) { "WIN hwnd=$w cls=$([MgX]::Cls($w)) title=[$([MgX]::Text($w))]" } }
    "use"     { $script:Dlg = [IntPtr][long]$arg; "target=$script:Dlg [$([MgX]::Text($script:Dlg))]" }
    "auto"    { $ws = [MgX]::TopWindows([uint32]$t.Id) | Where-Object { $_ -ne $h }; if ($ws.Count -eq 0) { "no dialog" } else { $script:Dlg = $ws[0]; "auto=$script:Dlg [$([MgX]::Text($script:Dlg))]" } }
    "findtitle" { $w = [MgX]::FindByTitle([uint32]$t.Id, $arg); if ($w -eq [IntPtr]::Zero) { "no window matching $arg" } else { $script:Dlg = $w; "found=$w [$([MgX]::Text($w))]" } }
    "dlg"     { $d = Get-Dlg; "dialog=$d [$([MgX]::Text($d))]"; [MgX]::Children($d) }
    "shot"    { $d = Get-Dlg; [MgX]::Shot($d, $arg); "shot $arg" }
    "shotmain"{ [MgX]::Shot($h, $arg); "shotmain $arg" }
    "bring"   { $d = Get-Dlg; [MgX]::SetWindowPos($d, [IntPtr]0, 0,0,0,0, 0x0043) | Out-Null; [MgX]::BringWindowToTop($d) | Out-Null; [MgX]::SetForegroundWindow($d) | Out-Null; Start-Sleep -Milliseconds 350; "brought" }
    "click"   { $a = $arg -split ","; [MgX]::Click([int]$a[0],[int]$a[1]); "click $arg" }
    "rclick"  { $a = $arg -split ","; [MgX]::RClick([int]$a[0],[int]$a[1]); "rclick $arg" }
    "dclick"  { $d = Get-Dlg; $r = New-Object MgX+RECT; [MgX]::GetWindowRect($d,[ref]$r) | Out-Null; $a = $arg -split ","; [MgX]::Click($r.Left+[int]$a[0], $r.Top+[int]$a[1]); "dclick $arg" }
    "ddclick" { $d = Get-Dlg; $r = New-Object MgX+RECT; [MgX]::GetWindowRect($d,[ref]$r) | Out-Null; $a = $arg -split ","; [MgX]::Click($r.Left+[int]$a[0], $r.Top+[int]$a[1]); Start-Sleep -Milliseconds 60; [MgX]::Click($r.Left+[int]$a[0], $r.Top+[int]$a[1]); "ddclick $arg" }
    "btn"     { $d = Get-Dlg; $c = [MgX]::Find($d,[int]$arg); if ($c -eq [IntPtr]::Zero) { "btn $arg NOT FOUND" } else { [MgX]::SendMessage($c,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null; "clicked $arg" } }
    "postbtn" { $d = Get-Dlg; $c = [MgX]::Find($d,[int]$arg); if ($c -eq [IntPtr]::Zero) { "btn $arg NOT FOUND" } else { [MgX]::PostMessage($d,0x0111,[IntPtr][int]$arg,$c) | Out-Null; "posted $arg" } }
    "set"     { $a = $arg -split "=",2; $d = Get-Dlg; $c = [MgX]::Find($d,[int]$a[0]); if ($c -eq [IntPtr]::Zero) { "ctrl $($a[0]) NOT FOUND" } else { [MgX]::SendMessageStr($c,0x000C,[IntPtr]::Zero,$a[1]) | Out-Null; "set $($a[0])=$($a[1])" } }
    "setedit" { $a = $arg -split "=",2; $d = Get-Dlg; $c = [MgX]::FindEdit($d,[int]$a[0]); if ($c -eq [IntPtr]::Zero) { "edit $($a[0]) NOT FOUND" } else { [MgX]::SendMessageStr($c,0x000C,[IntPtr]::Zero,$a[1]) | Out-Null; "setedit $($a[0])=$($a[1])" } }
    "cmd"     { [MgX]::PostMessage($h,0x0111,[IntPtr][int]$arg,[IntPtr]::Zero) | Out-Null; "cmd $arg" }
    "dlgcmd"  { $d = Get-Dlg; [MgX]::PostMessage($d,0x0111,[IntPtr][int]$arg,[IntPtr]::Zero) | Out-Null; "dlgcmd $arg" }
    "combo"   { $d = Get-Dlg; $c = [MgX]::Find($d,[int]$arg); $n = [MgX]::ComboCount($c); for ($k=0;$k -lt $n;$k++){ "  [$k] " + [MgX]::ComboText($c,$k) } }
    "comboi"  { $a = $arg -split ","; $d = Get-Dlg; $c = [MgX]::Find($d,[int]$a[0]); [MgX]::SendMessage($c,0x014E,[IntPtr][int]$a[1],[IntPtr]::Zero) | Out-Null; $wp = [IntPtr]([int](1 -shl 16) -bor [int]$a[0]); [MgX]::PostMessage($d,0x0111,$wp,$c) | Out-Null; "comboi $arg" }
    "listitems" { $d = Get-Dlg; $c = [MgX]::Find($d,[int]$arg); $n = [MgX]::SendMessage($c,0x018B,[IntPtr]::Zero,[IntPtr]::Zero).ToInt32(); "count=$n"; for($k=0;$k -lt $n;$k++){ "  [$k] " + [MgX]::ListItemText($c,$k) } }
    "rgb"     { $d = Get-Dlg; $n=[MgX]::Text([MgX]::Find($d,101)); $r=[MgX]::Text([MgX]::Find($d,1293)); $g=[MgX]::Text([MgX]::Find($d,1294)); $b=[MgX]::Text([MgX]::Find($d,1295)); "#$n R$r G$g B$b" }
    "colnum"  { $d = Get-Dlg; $c = [MgX]::Find($d,101); "color=" + [MgX]::Text($c) }
    "chk"     { $d = Get-Dlg; $c = [MgX]::Find($d,[int]$arg); "chk $arg = " + [MgX]::SendMessage($c,0x00F0,[IntPtr]::Zero,[IntPtr]::Zero).ToInt32() }
    "keys"    { [MgX]::SetForegroundWindow((Get-Dlg)) | Out-Null; Start-Sleep -Milliseconds 250; [System.Windows.Forms.SendKeys]::SendWait($arg); Start-Sleep -Milliseconds 250; "keys $arg" }
    "probe"   { $a = $arg -split ","; [MgX]::SetCursorPos([int]$a[0],[int]$a[1]) | Out-Null; Start-Sleep -Milliseconds 250; $pt = New-Object MgX+POINT; [MgX]::GetCursorPos([ref]$pt) | Out-Null; $w = [MgX]::WindowFromPoint($pt); "cursor=$($pt.X),$($pt.Y) win=[$([MgX]::Text($w))]" }
    "sleep"   { Start-Sleep -Milliseconds ([int]$arg); "sleep $arg" }
    default   { "unknown: $s" }
  }
}
