using PokemonApp.Services;

namespace PokemonApp.Views;

public partial class SettingsPage : ContentPage
{
    // Picker 选项 → 实际 model ID（空字符串 = 服务器默认）
    private static readonly string[] ModelIds =
    [
        "",                              // 服务器默认
        "claude-haiku-4-5-20251001",     // Haiku
        "claude-sonnet-4-6",             // Sonnet
    ];

    public SettingsPage()
    {
        InitializeComponent();
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        var username = await SecureStorage.GetAsync("username");
        UsernameLabel.Text = username ?? "训练家";
        ServerUrlEntry.Text = ApiConfig.BaseUrl;

        // 恢复已保存的模型选择
        var savedModel = await SecureStorage.GetAsync("selected_model") ?? "";
        ModelPicker.SelectedIndex = Array.IndexOf(ModelIds, savedModel) is int i && i >= 0 ? i : 0;

        var savedToolModel = await SecureStorage.GetAsync("selected_tool_model") ?? "";
        ToolModelPicker.SelectedIndex = Array.IndexOf(ModelIds, savedToolModel) is int j && j >= 0 ? j : 0;

        // 监听变更，实时保存
        ModelPicker.SelectedIndexChanged += OnModelPickerChanged;
        ToolModelPicker.SelectedIndexChanged += OnToolModelPickerChanged;
        ServerUrlEntry.TextChanged += OnServerUrlChanged;
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        ModelPicker.SelectedIndexChanged -= OnModelPickerChanged;
        ToolModelPicker.SelectedIndexChanged -= OnToolModelPickerChanged;
        ServerUrlEntry.TextChanged -= OnServerUrlChanged;
    }

    private async void OnModelPickerChanged(object? sender, EventArgs e)
    {
        var idx = ModelPicker.SelectedIndex;
        var modelId = idx >= 0 && idx < ModelIds.Length ? ModelIds[idx] : "";
        ApiConfig.SelectedModel = modelId;
        await SecureStorage.SetAsync("selected_model", modelId);
    }

    private async void OnToolModelPickerChanged(object? sender, EventArgs e)
    {
        var idx = ToolModelPicker.SelectedIndex;
        var modelId = idx >= 0 && idx < ModelIds.Length ? ModelIds[idx] : "";
        ApiConfig.SelectedToolModel = modelId;
        await SecureStorage.SetAsync("selected_tool_model", modelId);
    }

    private void OnServerUrlChanged(object? sender, TextChangedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(e.NewTextValue))
            ApiConfig.BaseUrl = e.NewTextValue.TrimEnd('/');
    }

    private async void OnLogout(object? sender, EventArgs e)
    {
        SecureStorage.RemoveAll();
        await Shell.Current.GoToAsync("//login");
    }
}
