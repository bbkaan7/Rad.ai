using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class Launcher {
    [STAThread]
    static void Main() {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            @"Desktop\sohbet_alpha\.venv\Scripts\pythonw.exe");
        if (!File.Exists(python)) {
            MessageBox.Show("The existing Python environment was not found. See README.md.", "Rad.ai");
            return;
        }
        try {
            Process.Start(new ProcessStartInfo {
                FileName = python,
                Arguments = "\"" + Path.Combine(folder, "main.py") + "\"",
                WorkingDirectory = folder,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            });
        } catch (Exception error) {
            MessageBox.Show(error.Message, "Rad.ai startup error");
        }
    }
}

