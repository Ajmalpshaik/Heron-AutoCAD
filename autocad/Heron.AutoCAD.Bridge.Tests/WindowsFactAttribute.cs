using System.Runtime.InteropServices;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// A test that needs Windows itself: the current-user named pipe the bridge
/// serves only works there. Elsewhere it is reported skipped, with the reason,
/// instead of timing out (issue #102). Windows CI runs it as a normal test.
/// </summary>
public sealed class WindowsFactAttribute : FactAttribute
{
    public WindowsFactAttribute()
    {
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            Skip = "Needs Windows: a real named pipe with a current-user ACL.";
    }
}
