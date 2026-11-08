using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Effects;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// What every Heron window is made of - the same as Heron for Revit's
    /// HeronWindowStyle (D-45): a Surface card with rounded corners and one
    /// shadow, a coloured strip along its top edge, an Ink header with the
    /// orange heron and "Heron  subtitle", an ✕, Ink insets, Mist text at 92,
    /// 72 and 55 per cent, and flat brand buttons. Orange is active and never
    /// danger, Warning is a warning, Error is danger, Success is a rail that
    /// still holds. Nothing here touches the AutoCAD API.
    /// </summary>
    internal static class HeronWindowStyle
    {
        internal static readonly Color CardColour = HeronBrand.Surface;
        internal static readonly Color HeaderColour = HeronBrand.Ink;
        internal static readonly Color InsetColour = HeronBrand.Ink;

        internal static readonly Color TextPrimary = HeronBrand.At(HeronBrand.Mist, 0xEB);
        internal static readonly Color TextSecondary = HeronBrand.At(HeronBrand.Mist, 0xB8);
        internal static readonly Color TextMuted = HeronBrand.At(HeronBrand.Mist, 0x8C);

        internal static readonly Color AccentColour = HeronBrand.Accent;
        internal static readonly Color WarnColour = HeronBrand.Warning;
        internal static readonly Color DangerColour = HeronBrand.Error;
        internal static readonly Color QuietColour = HeronBrand.At(HeronBrand.Mist, 0x8C);
        internal static readonly Color SafeColour = HeronBrand.Success;

        internal const double Gutter = 22;
        internal const string BodyFont = HeronBrand.FontList;
        internal const string MonoFont = "Consolas";

        /// <summary>A finished Heron window, with its top strip kept so its colour can change.</summary>
        internal sealed class Shell
        {
            private bool _closing;

            internal Shell(Window window, Border strip)
            {
                Window = window;
                AccentStrip = strip;
                window.Closing += (s, e) => _closing = true;
            }

            internal Window Window { get; }
            internal Border AccentStrip { get; }

            /// <summary>Once only: Esc and a Cancel button can both ask at the same moment.</summary>
            internal void Close()
            {
                if (_closing) return;
                _closing = true;
                try { Window.Close(); }
                catch (Exception ex) { HeronLog.Error("A Heron window would not close", ex); }
            }
        }

        /// <summary>
        /// Builds the window around <paramref name="body"/>. The bold half of the
        /// title is always "Heron"; <paramref name="subtitle"/> is the grey half.
        /// Esc and the ✕ both run <paramref name="onClose"/>.
        /// </summary>
        internal static Shell Build(string subtitle, double cardWidth, UIElement body, Color accent, Action onClose)
        {
            var strip = new Border { Height = 3, CornerRadius = new CornerRadius(14, 14, 0, 0), Background = new SolidColorBrush(accent) };
            var window = new Window
            {
                Width = cardWidth + 24,
                SizeToContent = SizeToContent.Height,
                WindowStyle = WindowStyle.None,
                ResizeMode = ResizeMode.NoResize,
                ShowInTaskbar = false,
                AllowsTransparency = true,
                Background = Brushes.Transparent,
                FontFamily = new FontFamily(BodyFont),
                Title = "Heron - " + subtitle,
                WindowStartupLocation = WindowStartupLocation.CenterOwner,
            };

            var stack = new DockPanel { LastChildFill = true };
            DockPanel.SetDock(strip, Dock.Top);
            stack.Children.Add(strip);
            var content = new StackPanel();
            content.Children.Add(TitleBar(window, subtitle, onClose));
            content.Children.Add(body);
            stack.Children.Add(content);

            var card = new Border
            {
                Background = new SolidColorBrush(CardColour),
                BorderBrush = new SolidColorBrush(HeronBrand.At(HeronBrand.White, 0x38)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(14),
                Child = stack,
                Effect = new DropShadowEffect { BlurRadius = 24, ShadowDepth = 6, Direction = 270, Opacity = 0.5, Color = HeronBrand.Shadow },
            };
            window.Content = new Border { Padding = new Thickness(12), Child = card };
            window.KeyDown += (s, e) =>
            {
                if (e.Key != Key.Escape) return;
                e.Handled = true;
                onClose();
            };
            return new Shell(window, strip);
        }

        private static UIElement TitleBar(Window window, string subtitle, Action onClose)
        {
            UIElement badge = new Border
            {
                Width = 26,
                Height = 26,
                CornerRadius = new CornerRadius(7),
                Background = new SolidColorBrush(AccentColour),
                VerticalAlignment = VerticalAlignment.Center,
                Child = new TextBlock
                {
                    Text = "H",
                    FontFamily = new FontFamily(BodyFont),
                    FontSize = 14,
                    FontWeight = FontWeights.Bold,
                    Foreground = new SolidColorBrush(HeronBrand.Ink),
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center,
                },
            };
            // THE HERON ITSELF, the orange 3D heron of the connected button; the
            // lettered tile stays as the fallback.
            var heron = IconLoader.Sized("BridgeConnected", 64);
            if (heron != null) badge = new Image { Source = heron, Width = 30, Height = 30, VerticalAlignment = VerticalAlignment.Center };

            var title = new TextBlock { Margin = new Thickness(11, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            title.Inlines.Add(new Run("Heron") { FontSize = 14, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(TextPrimary) });
            title.Inlines.Add(new Run("     " + subtitle) { FontSize = 13, Foreground = new SolidColorBrush(TextMuted) });

            var left = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
            left.Children.Add(badge);
            left.Children.Add(title);

            var close = new Button
            {
                Content = "✕",
                Width = 30,
                Height = 26,
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Center,
                Foreground = new SolidColorBrush(TextSecondary),
                FontSize = 12,
                Cursor = Cursors.Hand,
                Focusable = false,
                Template = FlatButtonTemplate(HeronBrand.At(HeronBrand.White, 0x24), 7),
            };
            close.Click += (s, e) => onClose();

            var bar = new Grid { Height = 54 };
            bar.Children.Add(left);
            bar.Children.Add(close);
            var host = new Border { Background = new SolidColorBrush(HeaderColour), Padding = new Thickness(Gutter, 0, 12, 0), Child = bar };
            // No title bar of Windows' own, so dragging the header moves it.
            host.MouseLeftButtonDown += (s, e) =>
            {
                try { if (e.ButtonState == MouseButtonState.Pressed) window.DragMove(); }
                catch (InvalidOperationException) { /* released mid-drag */ }
            };
            return host;
        }

        /// <summary>The strip along the bottom that the action buttons sit in.</summary>
        internal static Border Footer(UIElement content) => new Border
        {
            Margin = new Thickness(0, 20, 0, 0),
            Padding = new Thickness(Gutter - 10, 13, Gutter, 13),
            Background = new SolidColorBrush(HeaderColour),
            CornerRadius = new CornerRadius(0, 0, 13, 13),
            Child = content,
        };

        internal static TextBlock Caption(string text) => new TextBlock
        {
            Text = text,
            FontFamily = new FontFamily(BodyFont),
            FontSize = 10.5,
            FontWeight = FontWeights.SemiBold,
            Foreground = new SolidColorBrush(TextMuted),
            Margin = new Thickness(2, 15, 0, 0),
        };

        internal static TextBlock Body(string text, Color colour, double size) => new TextBlock
        {
            Text = text,
            FontFamily = new FontFamily(BodyFont),
            FontSize = size,
            Foreground = new SolidColorBrush(colour),
            TextWrapping = TextWrapping.Wrap,
            LineHeight = size + 7,
        };

        /// <summary>A path or an identifier, in its own inset box.</summary>
        internal static UIElement PathLine(string path) => new Border
        {
            Margin = new Thickness(0, 7, 0, 0),
            Padding = new Thickness(14, 10, 14, 10),
            CornerRadius = new CornerRadius(10),
            Background = new SolidColorBrush(InsetColour),
            Child = new TextBlock
            {
                Text = path,
                FontFamily = new FontFamily(MonoFont),
                FontSize = 11.5,
                Foreground = new SolidColorBrush(TextSecondary),
                TextWrapping = TextWrapping.Wrap,
                LineHeight = 17,
            },
        };

        /// <summary>Ink text on a lit button, as the status design does.</summary>
        internal static Button PrimaryButton(string label, Color fill) => new Button
        {
            Content = label,
            FontFamily = new FontFamily(BodyFont),
            FontSize = 13,
            FontWeight = FontWeights.SemiBold,
            Foreground = new SolidColorBrush(HeronBrand.Ink),
            Padding = new Thickness(18, 9, 18, 10),
            Margin = new Thickness(9, 0, 0, 0),
            Cursor = Cursors.Hand,
            Template = SolidButtonTemplate(fill),
        };

        internal static Button GhostButton(string label) => new Button
        {
            Content = label,
            FontFamily = new FontFamily(BodyFont),
            FontSize = 13,
            Foreground = new SolidColorBrush(TextSecondary),
            Padding = new Thickness(16, 9, 16, 10),
            Cursor = Cursors.Hand,
            Template = OutlineButtonTemplate(),
        };

        internal static Button FlatButton(string label, double fontSize) => new Button
        {
            Content = label,
            Foreground = new SolidColorBrush(TextSecondary),
            FontFamily = new FontFamily(BodyFont),
            FontSize = fontSize,
            Padding = new Thickness(10, 6, 10, 7),
            Cursor = Cursors.Hand,
            VerticalAlignment = VerticalAlignment.Center,
            Template = FlatButtonTemplate(HeronBrand.At(HeronBrand.White, 0x18), 8),
        };

        /// <summary>
        /// A choice that is a whole card: a heading and a note, Ink inset,
        /// an orange border while the keyboard is on it (the Keep question).
        /// </summary>
        internal static Button ChoiceButton(UIElement content)
        {
            var border = new FrameworkElementFactory(typeof(Border), TemplateRoot);
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(10));
            border.SetValue(Border.BackgroundProperty, new SolidColorBrush(InsetColour));
            border.SetValue(Border.BorderThicknessProperty, new Thickness(1.5));
            border.SetValue(Border.BorderBrushProperty, new SolidColorBrush(HeronBrand.At(HeronBrand.White, 0x1E)));
            border.SetValue(Border.PaddingProperty, new TemplateBindingExtension(Control.PaddingProperty));
            var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
            presenter.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Left);
            border.AppendChild(presenter);
            var template = new ControlTemplate(typeof(Button)) { VisualTree = border };
            var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
            hover.Setters.Add(new Setter(Border.BackgroundProperty, new SolidColorBrush(HeronBrand.At(HeronBrand.White, 0x10)), TemplateRoot));
            template.Triggers.Add(hover);
            var focus = new Trigger { Property = UIElement.IsKeyboardFocusedProperty, Value = true };
            focus.Setters.Add(new Setter(Border.BorderBrushProperty, new SolidColorBrush(AccentColour), TemplateRoot));
            template.Triggers.Add(focus);
            return new Button
            {
                Content = content,
                Padding = new Thickness(14, 10, 14, 11),
                Margin = new Thickness(0, 8, 0, 0),
                Cursor = Cursors.Hand,
                HorizontalContentAlignment = HorizontalAlignment.Left,
                Template = template,
            };
        }

        // ----- button templates (written out, so AutoCAD's theme cannot change them) -----

        private const string TemplateRoot = "HeronButtonRoot";

        internal static ControlTemplate SolidButtonTemplate(Color fill)
        {
            var template = new ControlTemplate(typeof(Button)) { VisualTree = TemplateBorder(new SolidColorBrush(fill), 9) };
            var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
            hover.Setters.Add(new Setter(UIElement.OpacityProperty, 0.87));
            template.Triggers.Add(hover);
            var pressed = new Trigger { Property = System.Windows.Controls.Primitives.ButtonBase.IsPressedProperty, Value = true };
            pressed.Setters.Add(new Setter(UIElement.OpacityProperty, 0.70));
            template.Triggers.Add(pressed);
            return template;
        }

        internal static ControlTemplate OutlineButtonTemplate()
        {
            var border = TemplateBorder(Brushes.Transparent, 9);
            border.SetValue(Border.BorderThicknessProperty, new Thickness(1));
            border.SetValue(Border.BorderBrushProperty, new SolidColorBrush(HeronBrand.At(HeronBrand.White, 0x3A)));
            var template = new ControlTemplate(typeof(Button)) { VisualTree = border };
            var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
            hover.Setters.Add(new Setter(Border.BackgroundProperty, new SolidColorBrush(HeronBrand.At(HeronBrand.White, 0x16)), TemplateRoot));
            template.Triggers.Add(hover);
            return template;
        }

        internal static ControlTemplate FlatButtonTemplate(Color hoverColour, double radius)
        {
            var template = new ControlTemplate(typeof(Button)) { VisualTree = TemplateBorder(Brushes.Transparent, radius) };
            var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
            hover.Setters.Add(new Setter(Border.BackgroundProperty, new SolidColorBrush(hoverColour), TemplateRoot));
            template.Triggers.Add(hover);
            return template;
        }

        private static FrameworkElementFactory TemplateBorder(Brush background, double radius)
        {
            var border = new FrameworkElementFactory(typeof(Border), TemplateRoot);
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(radius));
            border.SetValue(Border.BackgroundProperty, background);
            border.SetValue(Border.PaddingProperty, new TemplateBindingExtension(Control.PaddingProperty));
            var content = new FrameworkElementFactory(typeof(ContentPresenter));
            content.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center);
            content.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            border.AppendChild(content);
            return border;
        }
    }
}
