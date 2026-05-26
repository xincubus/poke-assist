using System.Text.Json;
using PokemonApp.Models;
using PokemonApp.Services;

namespace PokemonApp.Views;

[QueryProperty(nameof(CalcUrl), "url")]
public partial class DamageCalcPage : ContentPage
{
    private string _calcUrl = string.Empty;
    private readonly PokemonStorageService _storageService;
    private readonly PokemonDbService _db;

    private static readonly Dictionary<string, string> NatureMap = new()
    {
        {"Adamant","固执"},{"Bashful","害羞"},{"Bold","大胆"},{"Brave","勇敢"},
        {"Calm","温和"},{"Careful","慎重"},{"Docile","坦率"},{"Gentle","温顺"},
        {"Hardy","勤奋"},{"Hasty","急躁"},{"Impish","淘气"},{"Jolly","爽朗"},
        {"Lax","乐天"},{"Lonely","怕寂寞"},{"Mild","慢吞吞"},{"Modest","内敛"},
        {"Naive","天真"},{"Naughty","顽皮"},{"Quiet","冷静"},{"Quirky","浮躁"},
        {"Rash","马虎"},{"Relaxed","悠闲"},{"Sassy","自大"},{"Serious","认真"},
        {"Timid","胆小"}
    };

    public string CalcUrl
    {
        get => _calcUrl;
        set
        {
            _calcUrl = value;
            LoadCalcUrl(value);
        }
    }

    public DamageCalcPage()
    {
        InitializeComponent();
        _storageService = new PokemonStorageService();
        var client = new HttpClient { BaseAddress = new Uri(ApiConfig.BaseUrl) };
        _db = new PokemonDbService(client);
        CalcWebView.Navigating += OnWebViewNavigating;
    }

    private void LoadCalcUrl(string url)
    {
        if (string.IsNullOrEmpty(url)) return;
        CalcWebView.Source = new UrlWebViewSource { Url = url };
    }

    private void OnWebViewNavigating(object? sender, WebNavigatingEventArgs e)
    {
        var url = e.Url;
        if (url.StartsWith("pokemonapp://save/"))
        {
            e.Cancel = true;
            var pnumStr = url.Substring("pokemonapp://save/".Length);
            if (int.TryParse(pnumStr, out int pnum))
            {
                _ = SavePokemonFromCalcAsync(pnum);
            }
        }
    }

    private async void OnBackClicked(object? sender, EventArgs e)
    {
        await Shell.Current.GoToAsync("..");
    }

    private async Task SavePokemonFromCalcAsync(int pnum)
    {
        try
        {
            var raw = await CalcWebView.EvaluateJavaScriptAsync($"getPokemonConfig({pnum})");
            if (string.IsNullOrEmpty(raw) || raw == "null" || raw == "undefined")
            {
                await DisplayAlert("错误", "无法获取宝可梦配置", "确定");
                return;
            }

            var json = raw.Replace("\\\"", "\"");
            var config = JsonSerializer.Deserialize<JsonElement>(json);
            var nameEn = config.GetProperty("name").GetString() ?? "";
            if (string.IsNullOrEmpty(nameEn))
            {
                await DisplayAlert("提示", "请先选择一只宝可梦", "确定");
                return;
            }

            // 通过 API 搜索宝可梦，获取中文名、图片、种族值等
            var nameZh = nameEn;
            var imageUrl = "";
            var pokedexId = 0;
            var searchResults = await _db.SearchPokemonsAsync(nameEn);
            var match = searchResults.FirstOrDefault(r =>
                string.Equals(r.NameEn, nameEn, StringComparison.OrdinalIgnoreCase));
            if (match != null)
            {
                nameZh = string.IsNullOrEmpty(match.NameZh) ? nameEn : match.NameZh;
                pokedexId = match.PokedexId;
                if (!string.IsNullOrEmpty(match.ImageOfficialArtwork))
                {
                    imageUrl = match.ImageOfficialArtwork.StartsWith("http")
                        ? match.ImageOfficialArtwork
                        : $"{ApiConfig.BaseUrl}/static/{match.ImageOfficialArtwork}";
                }
            }

            var natureEn = config.GetProperty("nature").GetString() ?? "Hardy";
            var natureZh = NatureMap.TryGetValue(natureEn, out var n) ? n : natureEn;

            var pokemon = new StoredPokemon
            {
                Name = nameZh,
                NameEn = nameEn,
                PokedexId = pokedexId,
                ImageUrl = imageUrl,
                Type1 = match?.Type1Zh ?? "",
                Type2 = match?.Type2Zh ?? "",
                BaseHp = match?.Hp ?? 0,
                BaseAttack = match?.Attack ?? 0,
                BaseDefense = match?.Defense ?? 0,
                BaseSpAttack = match?.SpAttack ?? 0,
                BaseSpDefense = match?.SpDefense ?? 0,
                BaseSpeed = match?.Speed ?? 0,
                Nature = natureZh,
                Ability = config.GetProperty("ability").GetString() ?? "",
                Item = config.GetProperty("item").GetString() ?? "",
                Move1 = config.GetProperty("move1").GetString() ?? "",
                Move2 = config.GetProperty("move2").GetString() ?? "",
                Move3 = config.GetProperty("move3").GetString() ?? "",
                Move4 = config.GetProperty("move4").GetString() ?? "",
                EvHp = config.GetProperty("ev_hp").GetInt32(),
                EvAttack = config.GetProperty("ev_at").GetInt32(),
                EvDefense = config.GetProperty("ev_df").GetInt32(),
                EvSpAttack = config.GetProperty("ev_sa").GetInt32(),
                EvSpDefense = config.GetProperty("ev_sd").GetInt32(),
                EvSpeed = config.GetProperty("ev_sp").GetInt32(),
            };

            await _storageService.SavePokemonAsync(pokemon);
            await DisplayAlert("成功", $"已保存 {nameZh} 到我的宝可梦", "确定");
        }
        catch (Exception ex)
        {
            await DisplayAlert("错误", $"保存失败: {ex.Message}", "确定");
        }
    }
}
