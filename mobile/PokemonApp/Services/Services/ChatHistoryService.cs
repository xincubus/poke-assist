using SQLite;
using PokemonApp.Models;

namespace PokemonApp.Services;

/// <summary>
/// 聊天历史数据库服务
/// </summary>
public class ChatHistoryService
{
    private readonly SQLiteAsyncConnection _database;

    public ChatHistoryService()
    {
        var dbPath = Path.Combine(FileSystem.AppDataDirectory, "chat_history.db");
        _database = new SQLiteAsyncConnection(dbPath);

        // 创建表
        _database.CreateTableAsync<Conversation>().Wait();
        _database.CreateTableAsync<StoredChatMessage>().Wait();
    }

    /// <summary>
    /// 创建新会话
    /// </summary>
    public async Task<Conversation> CreateConversationAsync(string title)
    {
        var conversation = new Conversation
        {
            Title = title,
            CreatedAt = DateTime.Now,
            UpdatedAt = DateTime.Now
        };
        await _database.InsertAsync(conversation);
        return conversation;
    }

    /// <summary>
    /// 获取所有会话（置顶优先，再按更新时间倒序）
    /// </summary>
    public async Task<List<Conversation>> GetConversationsAsync()
    {
        var all = await _database.Table<Conversation>().ToListAsync();
        return all
            .OrderByDescending(c => c.IsPinned)
            .ThenByDescending(c => c.UpdatedAt)
            .ToList();
    }

    /// <summary>
    /// 切换置顶状态
    /// </summary>
    public async Task TogglePinAsync(int conversationId)
    {
        var conv = await _database.GetAsync<Conversation>(conversationId);
        conv.IsPinned = !conv.IsPinned;
        await _database.UpdateAsync(conv);
    }

    /// <summary>
    /// 更新会话标题和时间
    /// </summary>
    public async Task UpdateConversationAsync(Conversation conversation)
    {
        conversation.UpdatedAt = DateTime.Now;
        await _database.UpdateAsync(conversation);
    }

    /// <summary>
    /// 删除会话及其所有消息
    /// </summary>
    public async Task DeleteConversationAsync(int conversationId)
    {
        await _database.Table<StoredChatMessage>()
            .Where(m => m.ConversationId == conversationId)
            .DeleteAsync();
        await _database.DeleteAsync<Conversation>(conversationId);
    }

    /// <summary>
    /// 保存消息
    /// </summary>
    public async Task SaveMessageAsync(int conversationId, string text, bool isUser)
    {
        var message = new StoredChatMessage
        {
            ConversationId = conversationId,
            Text = text,
            IsUser = isUser,
            Timestamp = DateTime.Now
        };
        await _database.InsertAsync(message);
    }

    /// <summary>
    /// 获取会话的所有消息
    /// </summary>
    public async Task<List<StoredChatMessage>> GetMessagesAsync(int conversationId)
    {
        return await _database.Table<StoredChatMessage>()
            .Where(m => m.ConversationId == conversationId)
            .OrderBy(m => m.Timestamp)
            .ToListAsync();
    }
}
