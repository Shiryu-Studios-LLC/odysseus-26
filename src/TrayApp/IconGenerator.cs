#if NET8_0_OR_GREATER
#pragma warning disable CS0104
#endif

using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace ShirabiTray;

public enum TrayState
{
    Idle,
    Listening,
    Processing,
    Speaking,
    Error
}

public static class IconGenerator
{
    private static readonly Color[] StateColors =
    {
        Color.FromArgb(160, 160, 170),
        Color.FromArgb(80, 160, 255),
        Color.FromArgb(255, 180, 60),
        Color.FromArgb(100, 210, 130),
        Color.FromArgb(240, 70, 70),
    };

    public static Icon MakeIcon(TrayState state, int frame = 0)
    {
        using var bmp = new Bitmap(64, 64);
        using var g = Graphics.FromImage(bmp);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.Clear(Color.Transparent);

        var c = StateColors[(int)state];
        int cx = 32, cy = 32;

        switch (state)
        {
            case TrayState.Idle:
                DrawIdle(g, c, cx, cy);
                break;
            case TrayState.Listening:
                DrawListening(g, c, cx, cy, frame);
                break;
            case TrayState.Processing:
                DrawProcessing(g, c, cx, cy, frame);
                break;
            case TrayState.Speaking:
                DrawSpeaking(g, c, cx, cy, frame);
                break;
            case TrayState.Error:
                DrawError(g, c, cx, cy);
                break;
        }

        IntPtr hIcon = bmp.GetHicon();
        Icon icon = Icon.FromHandle(hIcon);
        return icon;
    }

    private static void DrawIdle(Graphics g, Color c, int cx, int cy)
    {
        using var brush = new SolidBrush(Color.FromArgb(40, c));
        using var pen = new Pen(Color.FromArgb(180, c), 2);
        g.FillEllipse(brush, 6, 6, 52, 52);
        g.DrawEllipse(pen, 6, 6, 52, 52);
        using var sail = new SolidBrush(Color.FromArgb(220, c));
        g.FillPolygon(sail, new[] { new Point(cx, 16), new Point(cx, 42), new Point(20, 42) });
        using var sail2 = new SolidBrush(Color.FromArgb(140, c));
        g.FillPolygon(sail2, new[] { new Point(cx, 22), new Point(cx, 42), new Point(44, 42) });
        using var wavePen = new Pen(Color.FromArgb(180, c), 3);
        g.DrawLines(wavePen, new[] { new Point(16, 46), new Point(24, 42), new Point(32, 46), new Point(40, 50), new Point(48, 46) });
    }

    private static void DrawListening(Graphics g, Color c, int cx, int cy, int frame)
    {
        double pulse = (Math.Sin(frame * 0.3) + 1) / 2;
        int radius = (int)(24 + 3 * pulse);
        int pr = radius + (int)(4 * pulse);

        using var ringPen = new Pen(Color.FromArgb(Math.Min(255, (int)(80 + 80 * pulse)), c), 2);
        g.DrawEllipse(ringPen, cx - pr, cy - pr, pr * 2, pr * 2);
        using var brush = new SolidBrush(Color.FromArgb(Math.Min(255, (int)(30 + 20 * pulse)), c));
        using var pen = new Pen(Color.FromArgb(200, c), 2);
        g.FillEllipse(brush, cx - radius, cy - radius, radius * 2, radius * 2);
        g.DrawEllipse(pen, cx - radius, cy - radius, radius * 2, radius * 2);
        using var micBrush = new SolidBrush(Color.FromArgb(230, c));
        FillRoundedRect(g, micBrush, 27, 18, 10, 14, 5);
        using var arcPen = new Pen(Color.FromArgb(230, c), 2);
        g.DrawArc(arcPen, 23, 28, 18, 14, 0, 180);
        g.DrawLine(arcPen, 32, 42, 32, 48);
        g.DrawLine(arcPen, 27, 48, 37, 48);
        for (int i = 0; i < 3; i++)
        {
            int wr = 10 + i * 5 + (int)(2 * pulse);
            int alpha = Math.Max(0, 180 - i * 60 - (int)(40 * pulse));
            using var wavePen = new Pen(Color.FromArgb(alpha, c), 2);
            g.DrawArc(wavePen, cx - wr, cy - wr + 6, wr * 2, wr * 2, -35, 70);
        }
    }

    private static void DrawProcessing(Graphics g, Color c, int cx, int cy, int frame)
    {
        int angle = frame * 8;
        using var pen = new Pen(Color.FromArgb(200, c), 3);
        g.DrawEllipse(pen, cx - 10, cy - 10, 20, 20);
        using var fill = new SolidBrush(Color.FromArgb(220, c));
        g.FillEllipse(fill, cx - 4, cy - 4, 8, 8);
        using var armPen = new Pen(Color.FromArgb(200, c), 3);
        for (int i = 0; i < 6; i++)
        {
            double rad = (angle + i * 60) * Math.PI / 180;
            int x1 = cx + (int)(10 * Math.Cos(rad));
            int y1 = cy + (int)(10 * Math.Sin(rad));
            int x2 = cx + (int)(14 * Math.Cos(rad));
            int y2 = cy + (int)(14 * Math.Sin(rad));
            g.DrawLine(armPen, x1, y1, x2, y2);
        }
        int ringAlpha = (int)(60 + 40 * Math.Sin(frame * 0.2));
        using var ringPen = new Pen(Color.FromArgb(ringAlpha, c), 1);
        g.DrawEllipse(ringPen, cx - 18, cy - 18, 36, 36);
    }

    private static void DrawSpeaking(Graphics g, Color c, int cx, int cy, int frame)
    {
        double pulse = (Math.Sin(frame * 0.4) + 1) / 2;
        using var brush = new SolidBrush(Color.FromArgb(30, c));
        using var pen = new Pen(Color.FromArgb(160, c), 2);
        g.FillEllipse(brush, 6, 6, 52, 52);
        g.DrawEllipse(pen, 6, 6, 52, 52);
        using var spkBrush = new SolidBrush(Color.FromArgb(230, c));
        g.FillPolygon(spkBrush, new[] { new Point(26, 26), new Point(26, 40), new Point(32, 40), new Point(38, 46), new Point(38, 20), new Point(32, 26) });
        for (int i = 0; i < 3; i++)
        {
            int wr = 8 + i * 6 + (int)(3 * pulse);
            int alpha = Math.Max(0, 200 - i * 70 - (int)(50 * pulse));
            using var wavePen = new Pen(Color.FromArgb(alpha, c), 2);
            g.DrawArc(wavePen, cx - wr, cy - wr, wr * 2, wr * 2, -40, 80);
        }
    }

    private static void DrawError(Graphics g, Color c, int cx, int cy)
    {
        using var brush = new SolidBrush(Color.FromArgb(40, c));
        using var pen = new Pen(Color.FromArgb(200, c), 2);
        g.FillEllipse(brush, 6, 6, 52, 52);
        g.DrawEllipse(pen, 6, 6, 52, 52);
        using var exBrush = new SolidBrush(Color.FromArgb(230, c));
        FillRoundedRect(g, exBrush, 29, 16, 6, 22, 2);
        g.FillEllipse(exBrush, 29, 42, 6, 6);
    }

    private static void FillRoundedRect(Graphics g, Brush brush, int x, int y, int w, int h, int r)
    {
        using var path = new GraphicsPath();
        path.AddArc(x, y, r * 2, r * 2, 180, 90);
        path.AddArc(x + w - r * 2, y, r * 2, r * 2, 270, 90);
        path.AddArc(x + w - r * 2, y + h - r * 2, r * 2, r * 2, 0, 90);
        path.AddArc(x, y + h - r * 2, r * 2, r * 2, 90, 90);
        path.CloseFigure();
        g.FillPath(brush, path);
    }
}
