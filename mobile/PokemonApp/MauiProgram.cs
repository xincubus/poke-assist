using Microsoft.Extensions.Logging;
using PokemonApp.Services;
using PokemonApp.ViewModels;
using PokemonApp.Views;

namespace PokemonApp;

public static class MauiProgram
{
	public static MauiApp CreateMauiApp()
	{
		var builder = MauiApp.CreateBuilder();
		builder
			.UseMauiApp<App>()
			.ConfigureFonts(fonts =>
			{
				fonts.AddFont("OpenSans-Regular.ttf", "OpenSansRegular");
				fonts.AddFont("OpenSans-Semibold.ttf", "OpenSansSemibold");
			});

		// Services - 每个 Service 用独立的 HttpClient
		// 使用 SocketsHttpHandler 避免 AndroidMessageHandler 把 IO 调度回主线程
		builder.Services.AddSingleton<AuthService>(_ =>
		{
			var client = new HttpClient(new SocketsHttpHandler());
			return new AuthService(client);
		});
		builder.Services.AddSingleton<ChatService>(_ =>
		{
			var client = new HttpClient(new SocketsHttpHandler()) { Timeout = TimeSpan.FromMinutes(2) };
			return new ChatService(client);
		});
		builder.Services.AddSingleton<ChatHistoryService>();
		builder.Services.AddSingleton<PokemonStorageService>();
		builder.Services.AddSingleton<PokemonDbService>(_ =>
		{
			var client = new HttpClient(new SocketsHttpHandler());
			return new PokemonDbService(client);
		});

		// ViewModels
		builder.Services.AddSingleton<ChatViewModel>();
		builder.Services.AddTransient<LoginViewModel>();
		builder.Services.AddTransient<RegisterViewModel>();
		builder.Services.AddTransient<PokemonViewModel>();
		builder.Services.AddTransient<TeamViewModel>();

		// Pages
		builder.Services.AddSingleton<ChatPage>();
		builder.Services.AddTransient<LoginPage>();
		builder.Services.AddTransient<RegisterPage>();
		builder.Services.AddTransient<PokemonListPage>();
		builder.Services.AddTransient<TeamListPage>();
		builder.Services.AddTransient<SettingsPage>();
		builder.Services.AddTransient<AddPokemonPage>();
		builder.Services.AddTransient<AddTeamPage>();
		builder.Services.AddTransient<DamageCalcPage>();
		builder.Services.AddTransient<DamageCalcTabPage>();

		// AppShell
		builder.Services.AddSingleton<AppShell>();

		// App
		builder.Services.AddSingleton<App>();

#if DEBUG
		builder.Logging.AddDebug();
#endif

		return builder.Build();
	}
}
