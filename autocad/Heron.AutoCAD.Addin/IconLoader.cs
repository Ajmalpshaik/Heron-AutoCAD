using System;
using System.IO;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Ribbon pictures from the Resources folder beside the DLL, the same PNGs
    /// Heron uses in Revit. A missing picture gives null, never an exception:
    /// a button without an icon still works.
    /// </summary>
    internal static class IconLoader
    {
        private static string Folder => Path.Combine(Path.GetDirectoryName(typeof(IconLoader).Assembly.Location) ?? "", "Resources");

        public static ImageSource? Large(string name) => Load(name, 32);

        public static ImageSource? Small(string name) => Load(name, 16);

        /// <summary>Any size, e.g. the 64 px heron in a window's title bar.</summary>
        public static ImageSource? Sized(string name, int pixels) => Load(name, pixels);

        private static ImageSource? Load(string name, int size)
        {
            try
            {
                var path = Path.Combine(Folder, name + ".png");
                if (!File.Exists(path)) return null;
                var image = new BitmapImage();
                image.BeginInit();
                image.UriSource = new Uri(path, UriKind.Absolute);
                image.DecodePixelWidth = size;
                image.DecodePixelHeight = size;
                image.CacheOption = BitmapCacheOption.OnLoad;
                image.EndInit();
                image.Freeze();
                return image;
            }
            catch (Exception ex)
            {
                HeronLog.Error("Icon " + name, ex);
                return null;
            }
        }
    }
}
