using SQLite;

namespace PokemonApp.Models;

/// <summary>
/// 存储的聊天消息
/// </summary>
[Table("chat_messages")]
public class StoredChatMessage
{
    [PrimaryKey, AutoIncrement]
    public int Id { get; set; }

    /// <summary>
    /// 所属会话 ID
    /// </summary>
    [Indexed]
    public int ConversationId { get; set; }

    /// <summary>
    /// 消息内容
    /// </summary>
    public string Text { get; set; } = string.Empty;

    /// <summary>
    /// 是否是用户消息
    /// </summary>
    public bool IsUser { get; set; }

    /// <summary>
    /// 时间戳
    /// </summary>
    public DateTime Timestamp { get; set; } = DateTime.Now;
}
