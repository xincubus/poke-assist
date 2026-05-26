using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;

namespace PokemonApp.Models;

public class ChatMessage : INotifyPropertyChanged
{
    private static readonly Regex MarkdownLinkRegex = new(@"\[([^\]]+)\]\(([^)]+)\)", RegexOptions.Compiled);

    private string _text = string.Empty;
    public string Text
    {
        get => _text;
        set
        {
            if (_text != value)
            {
                _text = value;
                OnPropertyChanged();
                OnPropertyChanged(nameof(DisplayHtml));
                OnPropertyChanged(nameof(HasLinks));
                OnPropertyChanged(nameof(ShowProgressSeparator));
            }
        }
    }

    /// <summary>
    /// 将 Text 中的 markdown 链接 [text](url) 转为 HTML <a> 标签，
    /// 供 Label TextType="Html" 使用
    /// </summary>
    public string DisplayHtml
    {
        get
        {
            if (string.IsNullOrEmpty(_text)) return string.Empty;
            // 先转义 HTML 特殊字符
            var escaped = _text
                .Replace("&", "&amp;")
                .Replace("<", "&lt;")
                .Replace(">", "&gt;")
                .Replace("\n", "<br/>");
            // 替换 markdown 链接为 <a> 标签
            return MarkdownLinkRegex.Replace(escaped,
                "<a href=\"$2\" style=\"color:#3498db;text-decoration:underline;\">$1</a>");
        }
    }

    /// <summary>
    /// 提取 Text 中第一个 markdown 链接的 URL（用于导航）
    /// </summary>
    public static string? ExtractFirstUrl(string text)
    {
        var match = MarkdownLinkRegex.Match(text);
        return match.Success ? match.Groups[2].Value : null;
    }

    /// <summary>
    /// 检查文本是否包含 markdown 链接
    /// </summary>
    public bool HasLinks => MarkdownLinkRegex.IsMatch(_text);

    private bool _isStreaming;
    public bool IsStreaming
    {
        get => _isStreaming;
        set
        {
            if (_isStreaming != value)
            {
                _isStreaming = value;
                OnPropertyChanged();
            }
        }
    }

    private bool _isSelectable;
    /// <summary>
    /// 是否处于"选择文本"模式（用只读 Editor 替代 Label，支持原生文本选择）
    /// </summary>
    public bool IsSelectable
    {
        get => _isSelectable;
        set
        {
            if (_isSelectable != value)
            {
                _isSelectable = value;
                OnPropertyChanged();
                OnPropertyChanged(nameof(IsNotSelectable));
            }
        }
    }

    /// <summary>
    /// IsSelectable 的反转，用于 XAML 绑定控制 Label 可见性
    /// </summary>
    public bool IsNotSelectable => !_isSelectable;

    /// <summary>
    /// 纯文本版本（去掉 markdown 链接语法，保留链接文字），供选择文本模式使用
    /// </summary>
    public string PlainText
    {
        get
        {
            if (string.IsNullOrEmpty(_text)) return string.Empty;
            return MarkdownLinkRegex.Replace(_text, "$1");
        }
    }

    public bool IsUser { get; set; }
    public DateTime Timestamp { get; set; } = DateTime.Now;

    /// <summary>
    /// 管线进度步骤（如 "✓ 识别意图：伤害计算"）
    /// </summary>
    public ObservableCollection<string> ProgressSteps { get; } = new();

    /// <summary>
    /// 原始进度数据，按 step 号索引，用于 active→done 转换
    /// </summary>
    private readonly Dictionary<int, (string label, string detail, string status)> _progressRaw = new();

    /// <summary>
    /// 是否有进度步骤需要显示
    /// </summary>
    public bool HasProgress => ProgressSteps.Count > 0;

    /// <summary>
    /// 是否显示进度和正文之间的分隔线（两者都有内容时才显示）
    /// </summary>
    public bool ShowProgressSeparator => HasProgress && !string.IsNullOrEmpty(_text);

    private string FormatStep(int step, string label, string detail, string status)
    {
        bool isPlanTask = step >= 50 && step < 60;
        string icon;
        if (isPlanTask)
        {
            var taskNum = step - 49;
            icon = status == "done" ? $"①②③④⑤⑥⑦⑧"[taskNum - 1].ToString() : $"{taskNum}";
        }
        else
        {
            icon = status == "done" ? "✓" : "◌";
        }
        var prefix = isPlanTask ? "    " : "";
        return string.IsNullOrEmpty(detail)
            ? $"{prefix}{icon} {label}"
            : $"{prefix}{icon} {label}：{detail}";
    }

    /// <summary>
    /// 添加或更新进度步骤
    /// </summary>
    public void UpdateProgress(int step, string label, string detail, string status)
    {
        _progressRaw[step] = (label, detail, status);
        RebuildProgressSteps();
        OnPropertyChanged(nameof(HasProgress));
        OnPropertyChanged(nameof(ShowProgressSeparator));
    }

    /// <summary>
    /// 按 step 编号升序重建显示列表（step 不再是连续的 1/2/3/4，可能是 1/11/12/91/93 等）
    /// </summary>
    private void RebuildProgressSteps()
    {
        var ordered = _progressRaw.OrderBy(kv => kv.Key).ToList();
        // 构建显示列表（含任务规划分组标题）
        var display = new List<string>();
        bool planHeaderInserted = false;
        foreach (var kv in ordered)
        {
            if (kv.Key >= 50 && kv.Key < 60 && !planHeaderInserted)
            {
                planHeaderInserted = true;
                display.Add("📋 任务规划");
            }
            var (label, detail, status) = kv.Value;
            display.Add(FormatStep(kv.Key, label, detail, status));
        }
        // 同步到 ProgressSteps
        while (ProgressSteps.Count < display.Count) ProgressSteps.Add(string.Empty);
        while (ProgressSteps.Count > display.Count) ProgressSteps.RemoveAt(ProgressSteps.Count - 1);
        for (int i = 0; i < display.Count; i++)
        {
            if (ProgressSteps[i] != display[i]) ProgressSteps[i] = display[i];
        }
    }

    /// <summary>
    /// 收尾：把残留的 active 步骤全部转为 done
    /// </summary>
    public void FinalizeProgress()
    {
        var changed = false;
        foreach (var step in _progressRaw.Keys.ToList())
        {
            var (label, detail, status) = _progressRaw[step];
            if (status == "active")
            {
                _progressRaw[step] = (label, detail, "done");
                changed = true;
            }
        }
        if (changed) RebuildProgressSteps();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    protected void OnPropertyChanged([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
