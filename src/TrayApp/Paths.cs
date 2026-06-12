using System.Diagnostics;
using System.IO;

namespace ShirabiTray;

/// <summary>
/// Resolves all paths relative to the Shirabi installation directory.
/// Works from any drive letter — no hardcoded paths.
/// 
/// Expected layout (after clone):
///   Shirabi/
///     Shirabi.exe              ← or python -m uvicorn
///     app/
///       src/
///         TrayApp/             ← this project (after build, runs from Shirabi/)
///       static/
///       data/
///     companion/
///       Builds/Windows/
///         Shirabi Companion.exe
///     GPT-SoVITS/              ← optional, user installs separately
///       venv/Scripts/python.exe
///       api.py
///     Resoruces/
///       Shirabi Wakeword.onnx
/// </summary>
public static class Paths
{
    /// <summary>
    /// The root Shirabi installation directory.
    /// Auto-detected as the directory containing Shirabi.exe or the parent
    /// of the running process directory.
    /// </summary>
    public static string Root { get; } = DetectRoot();

    /// <summary>Shirabi Python app directory.</summary>
    public static string AppDir => Path.Combine(Root, "app");

    /// <summary>Static files served by the backend.</summary>
    public static string StaticDir => Path.Combine(AppDir, "static");

    /// <summary>Data directory (settings, DB, presets).</summary>
    public static string DataDir => Path.Combine(AppDir, "data");

    /// <summary>Companion executable (Unity build).</summary>
    public static string CompanionExe => Path.Combine(Root, "app", "companion", "Builds", "Windows", "Shirabi Companion.exe");

    /// <summary>Wake word ONNX model.</summary>
    public static string WakewordModel => Path.Combine(Root, "Resoruces", "Shirabi Wakeword.onnx");

    /// <summary>
    /// GPT-SoVITS directory. Tries multiple locations since users may
    /// install it in different places.
    /// </summary>
    public static string? GptSoVitsDir => FindGptSoVits();

    /// <summary>GPT-SoVITS Python executable.</summary>
    public static string? GptSoVitsPython =>
        GptSoVitsDir != null ? Path.Combine(GptSoVitsDir, "venv", "Scripts", "python.exe") : null;

    /// <summary>GPT-SoVITS API script.</summary>
    public static string? GptSoVitsApiScript =>
        GptSoVitsDir != null ? Path.Combine(GptSoVitsDir, "api.py") : null;

    /// <summary>TrayApp DLL (for self-update checks).</summary>
    public static string TrayAppDir => AppContext.BaseDirectory;

    private static string DetectRoot()
    {
        // 1. Check if Shirabi.exe exists next to the running process
        var exeDir = AppContext.BaseDirectory;
        if (File.Exists(Path.Combine(exeDir, "Shirabi.exe")))
            return exeDir;

        // 2. Check parent directory
        var parent = Directory.GetParent(exeDir)?.FullName;
        if (parent != null && File.Exists(Path.Combine(parent, "Shirabi.exe")))
            return parent;

        // 3. Check grandparent (if running from src/TrayApp/bin/...)
        var grandparent = Directory.GetParent(parent ?? "")?.FullName;
        if (grandparent != null && File.Exists(Path.Combine(grandparent, "Shirabi.exe")))
            return grandparent;

        // 4. Walk up looking for app/static directory (Shirabi project marker)
        var dir = new DirectoryInfo(exeDir);
        for (int i = 0; i < 5 && dir != null; i++)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "app", "static")))
                return dir.FullName;
            dir = dir.Parent;
        }

        // 5. Fallback: current directory
        return Environment.CurrentDirectory;
    }

    private static string? FindGptSoVits()
    {
        // Try common locations relative to Shirabi root
        string[] candidates =
        [
            Path.Combine(Root, "GPT-SoVITS"),
            Path.Combine(Root, "Elevenlabs Shirabi", "GPT-SoVITS"),
            Path.Combine(Root, "..", "GPT-SoVITS"),
        ];

        foreach (var path in candidates)
        {
            var resolved = Path.GetFullPath(path);
            if (Directory.Exists(resolved) && File.Exists(Path.Combine(resolved, "api.py")))
                return resolved;
        }

        return null;
    }
}
