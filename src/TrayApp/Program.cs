using System.Windows.Forms;

namespace ShirabiTray;

static class Program
{
    [STAThread]
    static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        var tray = new TrayManager();
        tray.Start();

        Application.ThreadException += (_, e) =>
        {
            MessageBox.Show($"Tray error:\n{e.Exception.Message}", "Shirabi Tray",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        };

        Application.Run();

        tray.Stop();
    }
}
