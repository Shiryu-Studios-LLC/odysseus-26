using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace ShirabiTray;

public class PopupForm : Form
{
    private readonly TrayManager _tray;

    private readonly Label _titleLabel;
    private readonly Label _stateLabel;
    private readonly Panel _servicesPanel;

    public PopupForm(TrayManager tray)
    {
        _tray = tray;

        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        Size = new Size(320, 360);
        BackColor = Color.FromArgb(0x1a, 0x1a, 0x2e);
        Font = new Font("Segoe UI", 10f);
        Padding = new Padding(0);

        // Position near system tray
        var screen = Screen.PrimaryScreen!.WorkingArea;
        Location = new Point(screen.Right - Width - 16, screen.Bottom - Height - 16);

        // Close on deactivate
        Deactivate += (_, _) => Close();

        // Header
        var header = new Panel
        {
            BackColor = Color.FromArgb(0x16, 0x21, 0x3e),
            Dock = DockStyle.Top,
            Height = 52,
            Padding = new Padding(16, 12, 16, 12),
        };
        _titleLabel = new Label
        {
            Text = "Shirabi",
            Font = new Font("Segoe UI", 14f, FontStyle.Bold),
            ForeColor = Color.FromArgb(0xe0, 0xe0, 0xe0),
            AutoSize = true,
            Location = new Point(16, 10),
        };
        _stateLabel = new Label
        {
            Text = "Starting...",
            Font = new Font("Segoe UI", 8.5f),
            ForeColor = Color.FromArgb(0x88, 0x88, 0x88),
            AutoSize = true,
            Location = new Point(16, 32),
        };
        header.Controls.Add(_titleLabel);
        header.Controls.Add(_stateLabel);

        // Services panel
        _servicesPanel = new Panel
        {
            Dock = DockStyle.Top,
            Height = 180,
            Padding = new Padding(16, 8, 16, 8),
        };
        _servicesPanel.Paint += OnServicesPaint;

        // URL label
        var urlLabel = new Label
        {
            Text = "http://127.0.0.1:7000",
            Font = new Font("Segoe UI", 8f),
            ForeColor = Color.FromArgb(0x6b, 0x8a, 0xff),
            Dock = DockStyle.Top,
            Height = 22,
            TextAlign = ContentAlignment.MiddleCenter,
            Cursor = Cursors.Hand,
        };
        urlLabel.Click += (_, _) => { _tray.OpenShirabi(); Close(); };

        // Separator
        var sep = new Panel { BackColor = Color.FromArgb(0x33, 0x33, 0x55), Dock = DockStyle.Top, Height = 1 };

        // Buttons panel
        var btnPanel = new Panel { Dock = DockStyle.Top, Height = 44, Padding = new Padding(12, 8, 12, 8) };
        var btnOpen = MakeButton("Open", Color.FromArgb(0x3b, 0x59, 0x98), (_, _) => { _tray.OpenShirabi(); Close(); });
        var btnRestart = MakeButton("Restart", Color.FromArgb(0x8b, 0x5e, 0x3c), (_, _) => _tray.RestartShirabi());
        var btnExit = MakeButton("Exit", Color.FromArgb(0xc0, 0x39, 0x2b), (_, _) => _tray.ExitAll());
        var btnLayout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1 };
        btnLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33f));
        btnLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33f));
        btnLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 34f));
        btnLayout.Controls.Add(btnOpen, 0, 0);
        btnLayout.Controls.Add(btnRestart, 1, 0);
        btnLayout.Controls.Add(btnExit, 2, 0);
        btnPanel.Controls.Add(btnLayout);

        // Build top-down order (Controls.Add in reverse dock order)
        Controls.Add(btnPanel);
        Controls.Add(sep);
        Controls.Add(urlLabel);
        Controls.Add(_servicesPanel);
        Controls.Add(header);
    }

    private void OnServicesPaint(object? sender, PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;

        // SERVICES label
        using var labelBrush = new SolidBrush(Color.FromArgb(0x66, 0x66, 0x88));
        using var labelFont = new Font("Segoe UI", 7f, FontStyle.Bold);
        g.DrawString("SERVICES", labelFont, labelBrush, 16, 6);

        int y = 26;
        // Status dots, labels, buttons are drawn as flat text — simple and functional
        DrawServiceRow(g, y, "Wake Word", _tray.WakewordRunning);
        DrawServiceRow(g, y + 44, "TTS Voice", _tray.SovitsOk);
        DrawServiceRow(g, y + 88, "Companion", _tray.CompanionRunning);
    }

    private void DrawServiceRow(Graphics g, int y, string label, bool running)
    {
        // Background
        using var bgBrush = new SolidBrush(Color.FromArgb(0x22, 0x22, 0x44));
        var rect = new Rectangle(12, y, 280, 36);
        FillRoundedRect(g, bgBrush, rect, 6);

        // Status dot
        var dotColor = running ? Color.FromArgb(0x4a, 0xde, 0x80) : Color.FromArgb(0x66, 0x66, 0x66);
        using var dotBrush = new SolidBrush(dotColor);
        g.FillEllipse(dotBrush, 24, y + 13, 10, 10);

        // Label
        var textColor = running ? Color.FromArgb(0x4a, 0xde, 0x80) : Color.FromArgb(0xaa, 0xaa, 0xaa);
        using var textBrush = new SolidBrush(textColor);
        using var textFont = new Font("Segoe UI", 9f);
        string statusText = running ? $"{label} — On" : $"{label} — Off";
        g.DrawString(statusText, textFont, textBrush, 40, y + 8);
    }

    private static Button MakeButton(string text, Color bgColor, EventHandler onClick)
    {
        var btn = new Button
        {
            Text = text,
            FlatStyle = FlatStyle.Flat,
            BackColor = bgColor,
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
            Dock = DockStyle.Fill,
            FlatAppearance = { BorderSize = 0 },
            Cursor = Cursors.Hand,
        };
        btn.Click += onClick;
        return btn;
    }

    private static void FillRoundedRect(Graphics g, Brush brush, Rectangle rect, int radius)
    {
        using var path = new GraphicsPath();
        path.AddArc(rect.Left, rect.Top, radius * 2, radius * 2, 180, 90);
        path.AddArc(rect.Right - radius * 2, rect.Top, radius * 2, radius * 2, 270, 90);
        path.AddArc(rect.Right - radius * 2, rect.Bottom - radius * 2, radius * 2, radius * 2, 0, 90);
        path.AddArc(rect.Left, rect.Bottom - radius * 2, radius * 2, radius * 2, 90, 90);
        path.CloseFigure();
        g.FillPath(brush, path);
    }
}
