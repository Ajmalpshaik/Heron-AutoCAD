using System.Windows.Media;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The Heron brand colours and font, the same as Heron AI for Revit
    /// (Heron AI docs/brand/README.md). Every window colour comes from here:
    /// a shade is one of these at an opacity, never a new colour.
    /// </summary>
    internal static class HeronBrand
    {
        public static readonly Color Ink = Color.FromRgb(0x0F, 0x0F, 0x10);
        public static readonly Color Mist = Color.FromRgb(0xF7, 0xF5, 0xF2);
        public static readonly Color Accent = Color.FromRgb(0xFD, 0x64, 0x1A);
        /// <summary>Only as the light end of an Accent gradient, never alone.</summary>
        public static readonly Color AccentLight = Color.FromRgb(0xFF, 0x9A, 0x5C);
        public static readonly Color Surface = Color.FromRgb(0x1B, 0x1B, 0x1F);
        public static readonly Color Success = Color.FromRgb(0x3E, 0xCF, 0x8E);
        public static readonly Color Warning = Color.FromRgb(0xF5, 0xA5, 0x24);
        public static readonly Color Error = Color.FromRgb(0xFF, 0x5A, 0x4E);
        public static readonly Color White = Color.FromRgb(0xFF, 0xFF, 0xFF);
        /// <summary>Only as a see-through shadow, never solid.</summary>
        public static readonly Color Shadow = Color.FromRgb(0x00, 0x00, 0x00);

        /// <summary>Manrope first; Segoe UI where Manrope is not installed.</summary>
        public const string FontList = "Manrope, Segoe UI";

        /// <summary>A brand colour seen through: 0xFF solid, 0x00 invisible.</summary>
        public static Color At(Color colour, byte alpha) => Color.FromArgb(alpha, colour.R, colour.G, colour.B);

        /// <summary>A frozen brush, safe to share between windows and threads.</summary>
        public static SolidColorBrush Brush(Color colour)
        {
            var brush = new SolidColorBrush(colour);
            brush.Freeze();
            return brush;
        }
    }
}
