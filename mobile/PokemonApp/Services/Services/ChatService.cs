using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using PokemonApp.Models;

namespace PokemonApp.Services;

/// <summary>
/// 聊天服务
/// </summary>
public class ChatService
{
    private readonly HttpClient _httpClient;

    public ChatService(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.BaseAddress = new Uri(ApiConfig.BaseUrl);
        _httpClient.Timeout = TimeSpan.FromMinutes(5);
    }

    private static async Task<string?> GetTokenAsync()
    {
        try { return await SecureStorage.GetAsync("token"); }
        catch { return null; }
    }

    /// <summary>
    /// 根据对话内容生成标题
    /// </summary>
    public async Task<string?> GenerateTitleAsync(List<object> messages)
    {
        try
        {
            var payload = new { messages };
            var requestBody = new StringContent(
                JsonSerializer.Serialize(payload),
                Encoding.UTF8, "application/json");
            var response = await _httpClient.PostAsync("/api/chat/title", requestBody);
            if (!response.IsSuccessStatusCode) return null;
            var json = await response.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("success", out var ok) && ok.GetBoolean()
                && doc.RootElement.TryGetProperty("title", out var t))
                return t.GetString();
        }
        catch { }
        return null;
    }

    /// <summary>
    /// SSE 流式发送消息，每收到一个字符就回调 onChunkReceived
    /// 整个网络 IO 在后台线程执行，避免 NetworkOnMainThreadException
    /// </summary>
    public async Task SendMessageStreamAsync(string message, List<object>? context, Action<string> onChunkReceived, Action<string>? onProgress = null, CancellationToken ct = default, Action<string>? onThinking = null)
    {
        await Task.Run(async () =>
        {
            var payload = new Dictionary<string, object> { { "message", message }, { "platform", "mobile" } };
            if (context != null && context.Count > 0)
                payload["context"] = context;
            if (!string.IsNullOrEmpty(ApiConfig.SelectedModel))
                payload["model"] = ApiConfig.SelectedModel;
            if (!string.IsNullOrEmpty(ApiConfig.SelectedToolModel))
                payload["tool_model"] = ApiConfig.SelectedToolModel;

            var requestBody = new StringContent(
                JsonSerializer.Serialize(payload),
                Encoding.UTF8, "application/json");

            var request = new HttpRequestMessage(HttpMethod.Post, "/api/chat/stream")
            {
                Content = requestBody
            };
            var token = await GetTokenAsync();
            if (!string.IsNullOrEmpty(token))
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);

            var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync();
                throw new HttpRequestException($"HTTP {(int)response.StatusCode}: {body}");
            }

            using var stream = await response.Content.ReadAsStreamAsync();
            using var reader = new StreamReader(stream, Encoding.UTF8);

            var currentEventType = "";

            while (!reader.EndOfStream)
            {
                ct.ThrowIfCancellationRequested();

                var line = await reader.ReadLineAsync();
                if (line == null) break;

                // 跳过 SSE 注释行（心跳）和空行
                if (string.IsNullOrEmpty(line) || line.StartsWith(":")) continue;

                // 解析 event: 行
                if (line.StartsWith("event: "))
                {
                    currentEventType = line.Substring(7);
                    continue;
                }

                // SSE 格式: "data: 内容"
                if (!line.StartsWith("data: ")) continue;

                var data = line.Substring(6); // 去掉 "data: " 前缀

                // 结束标记
                if (data == "[DONE]") break;

                // 进度事件
                if (currentEventType == "progress")
                {
                    currentEventType = "";
                    try
                    {
                        onProgress?.Invoke(data);
                    }
                    catch { }
                    continue;
                }

                // 思考事件（LLM reasoning 内容）
                if (currentEventType == "thinking")
                {
                    currentEventType = "";
                    try
                    {
                        onThinking?.Invoke(data);
                    }
                    catch { }
                    continue;
                }

                // 其他未知事件：丢弃，避免当成正文
                if (!string.IsNullOrEmpty(currentEventType))
                {
                    currentEventType = "";
                    continue;
                }
                currentEventType = "";

                // 服务端用 json.dumps(char) 发送，需要反序列化去掉引号
                try
                {
                    var decoded = JsonSerializer.Deserialize<string>(data);
                    onChunkReceived(decoded ?? data);
                }
                catch
                {
                    onChunkReceived(data);
                }
            }
        }, ct);
    }
}
