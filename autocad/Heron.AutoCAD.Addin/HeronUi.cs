using System.Windows;
using System.Windows.Controls;
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
        public static readonly Color Surface = Color.FromRgb(0x1B, 0x1B, 0x1F);
        public static readonly Color Success = Color.FromRgb(0x3E, 0xCF, 0x8E);
        public static readonly Color Warning = Color.FromRgb(0xF5, 0xA5, 0x24);
        public static readonly Color Error = Color.FromRgb(0xFF, 0x5A, 0x4E);
        public static readonly Color White = Color.FromRgb(0xFF, 0xFF, 0xFF);

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

    /// <summary>The few look-and-feel pieces the Heron windows share.</summary>
    internal static class HeronUi
    {
        public static readonly Brush Ink = HeronBrand.Brush(HeronBrand.Ink);
        public static readonly Brush Muted = HeronBrand.Brush(HeronBrand.At(HeronBrand.Ink, 0xB8));   // 72 %
        public static readonly Brush Line = HeronBrand.Brush(HeronBrand.At(HeronBrand.Ink, 0x24));    // 14 %
        public static readonly Brush OffFill = HeronBrand.Brush(HeronBrand.At(HeronBrand.Ink, 0x14)); // 8 %
        public static readonly Brush Mist = HeronBrand.Brush(HeronBrand.Mist);
        public static readonly Brush Accent = HeronBrand.Brush(HeronBrand.Accent);
        public static readonly Brush Success = HeronBrand.Brush(HeronBrand.Success);
        public static readonly Brush Error = HeronBrand.Brush(HeronBrand.Error);

        public static Window NewWindow(string title, double width) => new Window
        {
            Title = title,
            Width = width,
            SizeToContent = SizeToContent.Height,
            ResizeMode = ResizeMode.NoResize,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            ShowInTaskbar = false,
            FontFamily = new FontFamily(HeronBrand.FontList),
            Background = Mist,
        };

        public static TextBlock Text(string text, double size = 13, FontWeight? weight = null, Brush? color = null) => new TextBlock
        {
            Text = text,
            FontSize = size,
            FontWeight = weight ?? FontWeights.Normal,
            Foreground = color ?? Ink,
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 0, 0, 6),
        };

        public static Button Button(string text, bool isDefault = false, bool isCancel = false) => new Button
        {
            Content = text,
            MinWidth = 96,
            Padding = new Thickness(14, 5, 14, 5),
            Margin = new Thickness(8, 0, 0, 0),
            IsDefault = isDefault,
            IsCancel = isCancel,
        };

        /// <summary>
        /// A switch card. A padlock that lets Heron change the drawing shows ON in
        /// the brand's Error colour - the state to notice - and never green, which
        /// would read as "safe". A switch whose ON is the safe side (Ask to Keep)
        /// shows ON in Success. OFF is a faint grey chip.
        /// </summary>
        public static Border Card(string name, bool on, string onText, string offText, bool onIsSafe = false)
        {
            var chip = new Border
            {
                Background = on ? (onIsSafe ? Success : Error) : OffFill,
                CornerRadius = new CornerRadius(3),
                Padding = new Thickness(6, 1, 6, 1),
                Margin = new Thickness(0, 0, 10, 0),
                VerticalAlignment = VerticalAlignment.Top,
                Child = new TextBlock { Text = on ? "ON" : "OFF", FontSize = 11, FontWeight = FontWeights.Bold, Foreground = on ? Ink : Muted },
            };
            var words = new StackPanel();
            words.Children.Add(Text(name, 13, FontWeights.SemiBold));
            var detail = Text(on ? onText : offText, 12, null, Muted);
            detail.Margin = new Thickness(0);
            words.Children.Add(detail);
            var row = new DockPanel();
            DockPanel.SetDock(chip, Dock.Left);
            row.Children.Add(chip);
            row.Children.Add(words);
            return new Border
            {
                BorderBrush = Line,
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(6),
                Padding = new Thickness(10, 8, 10, 8),
                Margin = new Thickness(0, 0, 0, 6),
                Child = row,
            };
        }

        public static StackPanel Buttons(params Button[] buttons)
        {
            var panel = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 12, 0, 0) };
            foreach (var b in buttons) panel.Children.Add(b);
            return panel;
        }
    }
}
