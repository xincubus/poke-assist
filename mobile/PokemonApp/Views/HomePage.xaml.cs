using PokemonApp.Services;

namespace PokemonApp.Views;

public partial class HomePage : ContentPage
{
	private string? _lastLoadedUrl;

	// 轮询注入：确保页面 JS 跑完后再覆盖主题和隐藏元素
	private const string InjectJsTemplate = @"
(function(){{
  var theme = '{0}';
  var count = 0;
  var timer = setInterval(function(){{
    count++;
    try{{
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('theme', theme === 'light' ? 'light' : 'dark');
      var s = document.getElementById('__maui_inject');
      if(!s){{
        s = document.createElement('style');
        s.id = '__maui_inject';
        s.textContent = 'header,.footer,#feedback-modal{{display:none!important}}body{{padding-top:0!important}}';
        document.head.appendChild(s);
      }}
    }}catch(e){{}}
    if(count >= 10) clearInterval(timer);
  }}, 200);
}})()";

	public HomePage()
	{
		InitializeComponent();
		HomeWebView.Navigated += OnWebViewNavigated;
		HomeWebView.Navigating += OnWebViewNavigating;
		Application.Current!.RequestedThemeChanged += OnRequestedThemeChanged;
	}

	protected override void OnAppearing()
	{
		base.OnAppearing();

		var baseUrl = ApiConfig.BaseUrl.TrimEnd('/');
		var url = $"{baseUrl}/web/home/home.html";

		// 首次加载加时间戳绕过 WebView 缓存
		if (!Preferences.ContainsKey("home_cache_busted"))
		{
			url += $"?v={DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";
			Preferences.Set("home_cache_busted", true);
		}

		if (_lastLoadedUrl != url)
		{
			_lastLoadedUrl = url;
			ErrorOverlay.IsVisible = false;
			HomeWebView.Source = new UrlWebViewSource { Url = url };
		}
	}

	private async void OnWebViewNavigated(object? sender, WebNavigatedEventArgs e)
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
			await InjectThemeAndCss();
		}
	}

	private void OnWebViewNavigating(object? sender, WebNavigatingEventArgs e)
	{
		// 拦截 pokemonapp:// 自定义 scheme（预留扩展）
		if (e.Url.StartsWith("pokemonapp://"))
		{
			e.Cancel = true;
		}
	}

	private void OnRetryClicked(object? sender, EventArgs e)
	{
		_lastLoadedUrl = null;
		OnAppearing();
	}

	private async void OnRequestedThemeChanged(object? sender, AppThemeChangedEventArgs e)
	{
		await InjectThemeAndCss();
	}

	private async Task InjectThemeAndCss()
	{
		try
		{
			var theme = Application.Current?.RequestedTheme == AppTheme.Dark ? "" : "light";
			var js = string.Format(InjectJsTemplate, theme);
			await HomeWebView.EvaluateJavaScriptAsync(js);
		}
		catch
		{
			// 注入失败不阻塞页面
		}
	}
}
