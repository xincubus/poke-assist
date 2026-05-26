using PokemonApp.Services;

namespace PokemonApp;

public partial class App : Application
{
	public App(AppShell appShell)
	{
		InitializeComponent();
		MainPage = appShell;
		_ = RestoreSettingsAsync();
	}

	private static async Task RestoreSettingsAsync()
	{
		var model = await SecureStorage.GetAsync("selected_model");
		if (!string.IsNullOrEmpty(model))
			ApiConfig.SelectedModel = model;

		var toolModel = await SecureStorage.GetAsync("selected_tool_model");
		if (!string.IsNullOrEmpty(toolModel))
			ApiConfig.SelectedToolModel = toolModel;
	}
}