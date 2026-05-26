using System.Collections.ObjectModel;
using System.Windows.Input;
using PokemonApp.Models;
using PokemonApp.Services;

namespace PokemonApp.ViewModels;

public class ChatViewModel : BaseViewModel
{
    private readonly ChatService _chatService;
    private readonly ChatHistoryService _historyService;
    private CancellationTokenSource? _streamCts;
    private Conversation? _currentConversation;
    private int _titleGenCount;          // 已生成标题的次数
    private int _nextTitleThreshold = 2; // 下次生成标题所需的消息轮数（2^n）

    public ObservableCollection<ChatMessage> Messages { get; } = new();

    private string _inputText = string.Empty;
    public string InputText
    {
        get => _inputText;
        set => SetProperty(ref _inputText, value);
    }

    private string _conversationTitle = string.Empty;
    public string ConversationTitle
    {
        get => _conversationTitle;
        set => SetProperty(ref _conversationTitle, value);
    }

    public ICommand SendCommand { get; }
    public ICommand StopCommand { get; }
    public ICommand NewChatCommand { get; }

    public ChatViewModel(ChatService chatService, ChatHistoryService historyService)
    {
        _chatService = chatService;
        _historyService = historyService;
        SendCommand = new Command(async () => await SendMessageAsync(), () => !IsBusy);
        StopCommand = new Command(() => _streamCts?.Cancel());
        NewChatCommand = new Command(async () => await StartNewChatAsync());

        // IsBusy 变化时刷新按钮状态
        PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(IsBusy))
                ((Command)SendCommand).ChangeCanExecute();
        };

        // 欢迎消息
        Messages.Add(new ChatMessage
        {
            Text = "你好，训练家！我是搬运小匠，可以帮你查询宝可梦数据和计算对战伤害。",
            IsUser = false
        });
    }

    /// <summary>
    /// 开始新对话
    /// </summary>
    public async Task StartNewChatAsync()
    {
        _currentConversation = null;
        ConversationTitle = string.Empty;
        _titleGenCount = 0;
        _nextTitleThreshold = 2;
        Messages.Clear();
        Messages.Add(new ChatMessage
        {
            Text = "你好，训练家！我是搬运小匠，可以帮你查询宝可梦数据和计算对战伤害。",
            IsUser = false
        });
    }

    /// <summary>
    /// 加载历史对话
    /// </summary>
    public async Task LoadConversationAsync(int conversationId)
    {
        Messages.Clear();

        var messages = await _historyService.GetMessagesAsync(conversationId);
        foreach (var msg in messages)
        {
            Messages.Add(new ChatMessage
            {
                Text = msg.Text,
                IsUser = msg.IsUser,
                Timestamp = msg.Timestamp
            });
        }

        _currentConversation = (await _historyService.GetConversationsAsync())
            .FirstOrDefault(c => c.Id == conversationId);
        ConversationTitle = _currentConversation?.Title ?? string.Empty;

        // 恢复标题生成计数器：根据已有消息轮数推算
        var rounds = Messages.Count(m => m.IsUser && !string.IsNullOrEmpty(m.Text));
        _titleGenCount = 0;
        _nextTitleThreshold = 2;
        while (_nextTitleThreshold <= rounds)
        {
            _titleGenCount++;
            _nextTitleThreshold = 2 << _titleGenCount;
        }
    }

    /// <summary>
    /// 当某条历史被删除时，如果是当前对话则重置
    /// </summary>
    public Task OnConversationDeletedAsync(int conversationId)
    {
        if (_currentConversation?.Id == conversationId)
            return StartNewChatAsync();
        return Task.CompletedTask;
    }

    private async Task GenerateTitleAsync()
    {
        try
        {
            if (_currentConversation == null) return;
            // 取全部消息来生成标题
            var msgs = Messages
                .Where(m => !string.IsNullOrEmpty(m.Text))
                .Select(m => new { role = m.IsUser ? "user" : "assistant", content = m.Text })
                .Cast<object>()
                .ToList();
            var title = await _chatService.GenerateTitleAsync(msgs);
            if (string.IsNullOrEmpty(title))
            {
                MainThread.BeginInvokeOnMainThread(() => ConversationTitle = "[标题生成返回空]");
                return;
            }
            _currentConversation.Title = title;
            await _historyService.UpdateConversationAsync(_currentConversation);
            MainThread.BeginInvokeOnMainThread(() => ConversationTitle = title);
            _titleGenCount++;
            _nextTitleThreshold = 2 << _titleGenCount; // 2^(n+1): 4, 8, 16, ...
        }
        catch (Exception ex)
        {
            MainThread.BeginInvokeOnMainThread(() => ConversationTitle = $"[标题错误: {ex.Message}]");
        }
    }

    private async Task SendMessageAsync()
    {
        var text = InputText?.Trim();
        if (string.IsNullOrEmpty(text)) return;

        // 如果是新对话，创建会话
        if (_currentConversation == null)
        {
            var title = text.Length > 30 ? text.Substring(0, 30) + "..." : text;
            _currentConversation = await _historyService.CreateConversationAsync(title);
        }

        // 添加用户消息
        Messages.Add(new ChatMessage { Text = text, IsUser = true });
        await _historyService.SaveMessageAsync(_currentConversation.Id, text, isUser: true);

        InputText = string.Empty;
        IsBusy = true;

        // 添加 AI 回复占位
        var aiMessage = new ChatMessage { Text = "", IsUser = false, IsStreaming = true };
        Messages.Add(aiMessage);

        _streamCts = new CancellationTokenSource();

        // 构建对话历史 context（不含当前消息和空的 AI 占位）
        var context = new List<object>();
        foreach (var msg in Messages)
        {
            if (msg == aiMessage || string.IsNullOrEmpty(msg.Text)) continue;
            context.Add(new { role = msg.IsUser ? "user" : "assistant", content = msg.Text });
        }
        // 最多保留最近 10 条，避免请求过大
        if (context.Count > 10)
            context = context.Skip(context.Count - 10).ToList();

        try
        {
            bool firstChunkSeen = false;
            await _chatService.SendMessageStreamAsync(
                text,
                context,
                chunk => MainThread.BeginInvokeOnMainThread(() =>
                {
                    if (!firstChunkSeen)
                    {
                        aiMessage.FinalizeProgress();
                        firstChunkSeen = true;
                    }
                    aiMessage.Text += chunk;
                }),
                onProgress: data => MainThread.BeginInvokeOnMainThread(() =>
                {
                    try
                    {
                        using var doc = System.Text.Json.JsonDocument.Parse(data);
                        var root = doc.RootElement;
                        var step = root.GetProperty("step").GetInt32();
                        var label = root.GetProperty("label").GetString() ?? "";
                        var detail = root.TryGetProperty("detail", out var d) ? d.GetString() ?? "" : "";
                        var status = root.TryGetProperty("status", out var s) ? s.GetString() ?? "" : "";
                        aiMessage.UpdateProgress(step, label, detail, status);
                    }
                    catch { }
                }),
                _streamCts.Token);

            // 流结束后也 finalize 一次（防止空响应时没调用过）
            MainThread.BeginInvokeOnMainThread(() => aiMessage.FinalizeProgress());

            // 保存 AI 回复
            await _historyService.SaveMessageAsync(_currentConversation.Id, aiMessage.Text, isUser: false);
            await _historyService.UpdateConversationAsync(_currentConversation);

            // 用户消息轮数（不含欢迎消息）
            var userRounds = Messages.Count(m => m.IsUser && !string.IsNullOrEmpty(m.Text));
            // 首次（标题未生成）或达到 2^n 轮时刷新标题
            if (userRounds >= 1 && (_titleGenCount == 0 || userRounds >= _nextTitleThreshold))
                _ = GenerateTitleAsync();
        }
        catch (TaskCanceledException)
        {
            // 用户手动停止
        }
        catch (HttpRequestException)
        {
            MainThread.BeginInvokeOnMainThread(() =>
            {
                aiMessage.Text = "无法连接到服务器，请检查网络连接。";
            });
        }
        catch (System.IO.IOException)
        {
            MainThread.BeginInvokeOnMainThread(() =>
            {
                aiMessage.Text = "连接中断，请重试。";
            });
        }
        catch (Exception ex)
        {
            MainThread.BeginInvokeOnMainThread(() =>
            {
                // 显示完整异常链，方便调试
                var msg = ex.GetType().Name + ": " + ex.Message;
                var inner = ex.InnerException;
                while (inner != null)
                {
                    msg += $"\n→ {inner.GetType().Name}: {inner.Message}";
                    inner = inner.InnerException;
                }
                msg += $"\n\nStackTrace:\n{ex.StackTrace}";
                aiMessage.Text = msg;
            });
        }
        finally
        {
            aiMessage.IsStreaming = false;
            IsBusy = false;
            _streamCts?.Dispose();
            _streamCts = null;
        }
    }
}
