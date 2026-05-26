using System.Text;
using System.Text.Json;
using PokemonApp.Models;

namespace PokemonApp.Services;

/// <summary>
/// 用户认证服务
/// </summary>
public class AuthService
{
    private readonly HttpClient _httpClient;

    public AuthService(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.BaseAddress = new Uri(ApiConfig.BaseUrl);
    }

    public async Task<UserInfo?> LoginAsync(string username, string password)
    {
        var content = new StringContent(
            JsonSerializer.Serialize(new { username, password }),
            Encoding.UTF8, "application/json");

        var response = await _httpClient.PostAsync("/api/auth/login", content);
        if (!response.IsSuccessStatusCode) return null;

        var json = await response.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<UserInfo>(json, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        });
    }

    public async Task<bool> RegisterAsync(string username, string password)
    {
        var content = new StringContent(
            JsonSerializer.Serialize(new { username, password }),
            Encoding.UTF8, "application/json");

        var response = await _httpClient.PostAsync("/api/auth/register", content);
        return response.IsSuccessStatusCode;
    }
}
