using System.Text;
using System.Text.Json;
using PokemonApp.Models;

namespace PokemonApp.Services;

/// <summary>
/// 通过后端 API 查询宝可梦数据库（搜索宝可梦、招式、道具、性格等）
/// </summary>
public class PokemonDbService
{
    private readonly HttpClient _http;
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    // 25个性格，按增加能力值分组排序（攻击→防御→特攻→特防→速度→无增减）
    public static readonly List<string> AllNatures = new()
    {
        // +攻击
        "怕寂寞（+攻击，-防御）",
        "固执（+攻击，-特攻）",
        "顽皮（+攻击，-特防）",
        "勇敢（+攻击，-速度）",
        // +防御
        "大胆（+防御，-攻击）",
        "淘气（+防御，-特攻）",
        "乐天（+防御，-特防）",
        "悠闲（+防御，-速度）",
        // +特攻
        "内敛（+特攻，-攻击）",
        "慢吞吞（+特攻，-防御）",
        "马虎（+特攻，-特防）",
        "冷静（+特攻，-速度）",
        // +特防
        "温和（+特防，-攻击）",
        "温顺（+特防，-防御）",
        "慎重（+特防，-特攻）",
        "自大（+特防，-速度）",
        // +速度
        "胆小（+速度，-攻击）",
        "急躁（+速度，-防御）",
        "爽朗（+速度，-特攻）",
        "天真（+速度，-特防）",
        // 无增减
        "勤奋",
        "坦率",
        "害羞",
        "浮躁",
        "认真"
    };

    public PokemonDbService(HttpClient http)
    {
        _http = http;
        _http.BaseAddress = new Uri(ApiConfig.BaseUrl);
    }

    /// <summary>搜索宝可梦（中英日名称模糊匹配），返回最多20条</summary>
    public async Task<List<PokemonSearchResult>> SearchPokemonsAsync(string keyword)
    {
        if (string.IsNullOrWhiteSpace(keyword)) return new();
        try
        {
            var resp = await _http.GetAsync($"/api/pokemon/search?keyword={Uri.EscapeDataString(keyword)}");
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                var result = JsonSerializer.Deserialize<PokemonSearchResponse>(json,
                    JsonOpts);
                return result?.Results ?? new();
            }
        }
        catch { }
        return new();
    }

    /// <summary>通过图鉴编号获取宝可梦完整数据</summary>
    public async Task<PokemonSearchResult?> GetPokemonByIdAsync(int pokedexId)
    {
        try
        {
            var resp = await _http.GetAsync($"/api/pokemon/{pokedexId}");
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                return JsonSerializer.Deserialize<PokemonSearchResult>(json,
                    JsonOpts);
            }
        }
        catch { }
        return null;
    }

    /// <summary>查询宝可梦对应的 Mega 石道具名（若为 Mega 形态）</summary>
    public async Task<string?> GetMegaStoneAsync(int pokemonId)
    {
        try
        {
            var resp = await _http.GetAsync($"/api/pokemon/{pokemonId}/mega-stone");
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("item_name", out var val) && val.ValueKind == JsonValueKind.String)
                    return val.GetString();
            }
        }
        catch { }
        return null;
    }

    /// <summary>搜索招式（中英日名称模糊匹配）</summary>
    public async Task<List<MoveSearchResult>> SearchMovesAsync(string keyword, int pokedexId = 0)
    {
        if (string.IsNullOrWhiteSpace(keyword)) return new();
        try
        {
            var endpoint = pokedexId > 0
                ? $"/api/moves/search?keyword={Uri.EscapeDataString(keyword)}&pokedex_id={pokedexId}"
                : $"/api/moves/search?keyword={Uri.EscapeDataString(keyword)}";
            var resp = await _http.GetAsync(endpoint);
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                var result = JsonSerializer.Deserialize<MoveSearchResponse>(json,
                    JsonOpts);
                return result?.Results ?? new();
            }
        }
        catch { }
        return new();
    }

    /// <summary>搜索道具</summary>
    public async Task<List<ItemSearchResult>> SearchItemsAsync(string keyword)
    {
        if (string.IsNullOrWhiteSpace(keyword)) return new();
        try
        {
            var resp = await _http.GetAsync($"/api/items/search?keyword={Uri.EscapeDataString(keyword)}");
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                var result = JsonSerializer.Deserialize<ItemSearchResponse>(json,
                    JsonOpts);
                return result?.Results ?? new();
            }
        }
        catch { }
        return new();
    }

    /// <summary>翻译招式英文名→中文名</summary>
    public async Task<string> TranslateMoveAsync(string nameEn)
    {
        if (string.IsNullOrWhiteSpace(nameEn)) return nameEn;
        var results = await SearchMovesAsync(nameEn);
        var match = results.FirstOrDefault(r =>
            string.Equals(r.NameEn, nameEn, StringComparison.OrdinalIgnoreCase));
        return match?.NameZh ?? nameEn;
    }

    /// <summary>翻译道具英文名→中文名</summary>
    public async Task<string> TranslateItemAsync(string nameEn)
    {
        if (string.IsNullOrWhiteSpace(nameEn)) return nameEn;
        var results = await SearchItemsAsync(nameEn);
        var match = results.FirstOrDefault(r =>
            string.Equals(r.NameEn, nameEn, StringComparison.OrdinalIgnoreCase));
        return match?.NameZh ?? nameEn;
    }

    /// <summary>翻译特性英文名→中文名</summary>
    public async Task<string> TranslateAbilityAsync(string nameEn)
    {
        if (string.IsNullOrWhiteSpace(nameEn)) return nameEn;
        try
        {
            var resp = await _http.GetAsync($"/api/translate?names={Uri.EscapeDataString(nameEn)}&table=abilities");
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("translations", out var translations))
                {
                    if (translations.TryGetProperty(nameEn, out var zhName) && zhName.ValueKind == JsonValueKind.String)
                        return zhName.GetString() ?? nameEn;
                }
            }
        }
        catch { }
        return nameEn;
    }

    /// <summary>批量翻译英文名→中文名</summary>
    public async Task<Dictionary<string, string>> TranslateBatchAsync(IEnumerable<string> namesEn, string table)
    {
        var names = namesEn.Where(n => !string.IsNullOrWhiteSpace(n)).Distinct().ToList();
        if (names.Count == 0) return new();
        try
        {
            var namesParam = string.Join(",", names);
            var resp = await _http.GetAsync($"/api/translate?names={Uri.EscapeDataString(namesParam)}&table={table}");
            if (resp.IsSuccessStatusCode)
            {
                var json = await resp.Content.ReadAsStringAsync();
                var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("translations", out var translations))
                {
                    var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                    foreach (var name in names)
                    {
                        if (translations.TryGetProperty(name, out var zhName) && zhName.ValueKind == JsonValueKind.String)
                            result[name] = zhName.GetString() ?? name;
                        else
                            result[name] = name;
                    }
                    return result;
                }
            }
        }
        catch { }
        return names.ToDictionary(n => n, n => n);
    }
}

// --- 搜索结果模型 ---

public class PokemonSearchResult
{
    public int Id { get; set; }
    public int PokedexId { get; set; }
    public string NameZh { get; set; } = string.Empty;
    public string NameEn { get; set; } = string.Empty;
    public string NameNcp { get; set; } = string.Empty;
    public string NameJa { get; set; } = string.Empty;
    public string ImageOfficialArtwork { get; set; } = string.Empty;
    public string Type1 { get; set; } = string.Empty;
    public string Type2 { get; set; } = string.Empty;
    public string Type1Zh { get; set; } = string.Empty;
    public string Type1Color { get; set; } = string.Empty;
    public string Type2Zh { get; set; } = string.Empty;
    public string Type2Color { get; set; } = string.Empty;
    public int Hp { get; set; }
    public int Attack { get; set; }
    public int Defense { get; set; }
    public int SpAttack { get; set; }
    public int SpDefense { get; set; }
    public int Speed { get; set; }
    public string Ability1Name { get; set; } = string.Empty;
    public string Ability2Name { get; set; } = string.Empty;
    public string HiddenAbilityName { get; set; } = string.Empty;

    public string DisplayName => string.IsNullOrEmpty(NameZh) ? NameEn : NameZh;
}

public class PokemonSearchResponse
{
    public List<PokemonSearchResult> Results { get; set; } = new();
}

public class MoveSearchResult
{
    public int Id { get; set; }
    public string NameZh { get; set; } = string.Empty;
    public string NameEn { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty;
    public string DamageClass { get; set; } = string.Empty;
    public int? Power { get; set; }
    public string DisplayName => string.IsNullOrEmpty(NameZh) ? NameEn : NameZh;
}

public class MoveSearchResponse
{
    public List<MoveSearchResult> Results { get; set; } = new();
}

public class ItemSearchResult
{
    public int Id { get; set; }
    public string NameZh { get; set; } = string.Empty;
    public string NameEn { get; set; } = string.Empty;
    public string DisplayName => string.IsNullOrEmpty(NameZh) ? NameEn : NameZh;
}

public class ItemSearchResponse
{
    public List<ItemSearchResult> Results { get; set; } = new();
}
