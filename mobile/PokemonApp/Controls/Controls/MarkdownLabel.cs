using System.Text.RegularExpressions;

namespace PokemonApp.Controls;

/// <summary>
/// 支持 markdown 链接 [text](url) 内联点击的 Label 控件。
/// 普通文本渲染为 Span，链接渲染为蓝色下划线 Span 并绑定 TapGestureRecognizer。
/// </summary>
public class MarkdownLabel : ContentView
{
    private static readonly Regex MarkdownLinkRegex =
        new(@"\[([^\]]+)\]\(([^)]+)\)", RegexOptions.Compiled);

    public static readonly BindableProperty MarkdownTextProperty =
        BindableProperty.Create(
            nameof(MarkdownText), typeof(string), typeof(MarkdownLabel),
            string.Empty, propertyChanged: OnTextRelatedChanged);

    public static readonly BindableProperty TextColorProperty =
        BindableProperty.Create(
            nameof(TextColor), typeof(Color), typeof(MarkdownLabel),
            Colors.Black, propertyChanged: OnTextRelatedChanged);

    public static readonly BindableProperty FontSizeProperty =
        BindableProperty.Create(
            nameof(FontSize), typeof(double), typeof(MarkdownLabel),
            15.0, propertyChanged: OnTextRelatedChanged);

    public static readonly BindableProperty LinkColorProperty =
        BindableProperty.Create(
            nameof(LinkColor), typeof(Color), typeof(MarkdownLabel),
            Color.FromArgb("#3498db"), propertyChanged: OnTextRelatedChanged);

    /// <summary>
    /// 链接被点击时触发，参数为 URL 字符串
    /// </summary>
    public event EventHandler<string>? LinkClicked;

    private readonly Label _label;

    public string MarkdownText
    {
        get => (string)GetValue(MarkdownTextProperty);
        set => SetValue(MarkdownTextProperty, value);
    }

    public Color TextColor
    {
        get => (Color)GetValue(TextColorProperty);
        set => SetValue(TextColorProperty, value);
    }

    public double FontSize
    {
        get => (double)GetValue(FontSizeProperty);
        set => SetValue(FontSizeProperty, value);
    }

    public Color LinkColor
    {
        get => (Color)GetValue(LinkColorProperty);
        set => SetValue(LinkColorProperty, value);
    }

    public MarkdownLabel()
    {
        _label = new Label { LineBreakMode = LineBreakMode.WordWrap };
        Content = _label;
    }

    private static void OnTextRelatedChanged(BindableObject bindable, object oldValue, object newValue)
    {
        ((MarkdownLabel)bindable).RebuildFormattedText();
    }

    private void RebuildFormattedText()
    {
        var text = MarkdownText ?? string.Empty;
        var fs = new FormattedString();

        int lastIndex = 0;
        foreach (Match match in MarkdownLinkRegex.Matches(text))
        {
            // 链接前的普通文本
            if (match.Index > lastIndex)
            {
                fs.Spans.Add(new Span
                {
                    Text = text[lastIndex..match.Index],
                    TextColor = TextColor,
                    FontSize = FontSize
                });
            }

            // 链接 Span（蓝色 + 下划线 + 可点击）
            var linkText = match.Groups[1].Value;
            var linkUrl = match.Groups[2].Value;

            var linkSpan = new Span
            {
                Text = linkText,
                TextColor = LinkColor,
                TextDecorations = TextDecorations.Underline,
                FontSize = FontSize
            };

            var tap = new TapGestureRecognizer();
            var capturedUrl = linkUrl; // 闭包捕获
            tap.Tapped += (_, _) => LinkClicked?.Invoke(this, capturedUrl);
            linkSpan.GestureRecognizers.Add(tap);

            fs.Spans.Add(linkSpan);
            lastIndex = match.Index + match.Length;
        }

        // 尾部剩余文本
        if (lastIndex < text.Length)
        {
            fs.Spans.Add(new Span
            {
                Text = text[lastIndex..],
                TextColor = TextColor,
                FontSize = FontSize
            });
        }

        _label.FormattedText = fs;
    }
}
