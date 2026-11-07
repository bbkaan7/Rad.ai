using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
[assembly: System.Reflection.AssemblyTitle("Rad.ai")]
[assembly: System.Reflection.AssemblyProduct("Rad.ai")]
[assembly: System.Reflection.AssemblyVersion("0.1.15.0")]
[assembly: System.Reflection.AssemblyFileVersion("0.1.15.0")]
static class Launcher {
    [STAThread] static void Main() {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(folder, @".venv\Scripts\pythonw.exe");
        if (!File.Exists(python)) python = Path.GetFullPath(Path.Combine(folder, @"..\..\.venv\Scripts\pythonw.exe"));
        if (!File.Exists(python)) {
            MessageBox.Show("Install requirements in a .venv environment first. See README.md.", "Rad.ai");
            return;
        }
        try {
            Process.Start(new ProcessStartInfo {
                FileName=python, Arguments="\""+Path.Combine(folder,"main.py")+"\"",
                WorkingDirectory=folder, UseShellExecute=false, CreateNoWindow=true,
                WindowStyle=ProcessWindowStyle.Hidden
            });
        } catch (Exception error) { MessageBox.Show(error.Message,"Rad.ai"); }
    }
}
