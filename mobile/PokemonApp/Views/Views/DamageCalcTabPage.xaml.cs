using System.Text.Json;
using PokemonApp.Models;
using PokemonApp.Services;

namespace PokemonApp.Views;

public partial class DamageCalcTabPage : ContentPage
{
	private string? _lastLoadedUrl;
	private readonly PokemonStorageService _storageService;
	private readonly PokemonDbService _db;

	// 英文性格名 → 中文性格名
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

	public DamageCalcTabPage(PokemonStorageService storageService, PokemonDbService db)
	{
		_storageService = storageService;
		_db = db;
		InitializeComponent();
		CalcWebView.Navigated += OnWebViewNavigated;
		CalcWebView.Navigating += OnWebViewNavigating;
	}

	protected override void OnAppearing()
	{
		base.OnAppearing();

		var baseUrl = ApiConfig.BaseUrl.TrimEnd('/');
		var url = $"{baseUrl}/cale/mobile.html";

		// 首次安装打开时加时间戳强制绕过 WebView 缓存
		if (!Preferences.ContainsKey("calc_cache_busted"))
		{
			url += $"?v={DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";
			Preferences.Set("calc_cache_busted", true);
		}

		if (_lastLoadedUrl != url)
		{
			_lastLoadedUrl = url;
			ErrorOverlay.IsVisible = false;
			CalcWebView.Source = new UrlWebViewSource { Url = url };
		}
	}

	private void OnWebViewNavigated(object? sender, WebNavigatedEventArgs e)
	{
		if (e.Result != WebNavigationResult.Success)
		{
			ErrorOverlay.IsVisible = true;
			ErrorLabel.Text = $"无法连接到服务器\n{_lastLoadedUrl}\n\n请检查：\n1. API 服务是否已启动\n2. 设置页中服务器地址是否正确\n3. 设备与服务器是否在同一网络";
			_lastLoadedUrl = null;
		}
		else
		{
			ErrorOverlay.IsVisible = false;
		}
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

	private void OnRetryClicked(object? sender, EventArgs e)
	{
		_lastLoadedUrl = null;
		OnAppearing();
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

			// MAUI EvaluateJavaScriptAsync 返回带转义引号的 JSON（{\"name\":...}），不是外层包裹的字符串
			// 不能用 JsonSerializer.Deserialize<string>(raw)，必须用字符串替换去掉转义
			// 参考：调试时 Step1 显示 raw 以 {\" 开头（char 123,92,34），确认是直接转义的 JSON 对象
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

			// 翻译性格
			var natureEn = config.GetProperty("nature").GetString() ?? "Hardy";
			var natureZh = NatureMap.TryGetValue(natureEn, out var n) ? n : natureEn;

			// 翻译特性、道具、招式（英文→中文）
			var abilityEn = config.GetProperty("ability").GetString() ?? "";
			var itemEn = config.GetProperty("item").GetString() ?? "";
			var move1En = config.GetProperty("move1").GetString() ?? "";
			var move2En = config.GetProperty("move2").GetString() ?? "";
			var move3En = config.GetProperty("move3").GetString() ?? "";
			var move4En = config.GetProperty("move4").GetString() ?? "";

			// 批量翻译（3个并发请求）
			var abilityTask = _db.TranslateAbilityAsync(abilityEn);
			var itemTask = _db.TranslateBatchAsync(new[] { itemEn }, "items");
			var movesTask = _db.TranslateBatchAsync(new[] { move1En, move2En, move3En, move4En }, "moves");
			await Task.WhenAll(abilityTask, itemTask, movesTask);

			var abilityZh = abilityTask.Result;
			var itemZh = itemTask.Result.GetValueOrDefault(itemEn, itemEn);
			var move1Zh = movesTask.Result.GetValueOrDefault(move1En, move1En);
			var move2Zh = movesTask.Result.GetValueOrDefault(move2En, move2En);
			var move3Zh = movesTask.Result.GetValueOrDefault(move3En, move3En);
			var move4Zh = movesTask.Result.GetValueOrDefault(move4En, move4En);

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
				Ability = abilityZh,
				Item = itemZh,
				Move1 = move1Zh,
				Move2 = move2Zh,
				Move3 = move3Zh,
				Move4 = move4Zh,
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
