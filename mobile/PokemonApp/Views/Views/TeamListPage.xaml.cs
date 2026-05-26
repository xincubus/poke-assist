using PokemonApp.Models;
using PokemonApp.ViewModels;

namespace PokemonApp.Views;

public partial class TeamListPage : ContentPage
{
    private readonly TeamViewModel _vm;

    public TeamListPage(TeamViewModel vm)
    {
        _vm = vm;
        InitializeComponent();
        BindingContext = _vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.LoadAsync();
    }

    private async void GoToPokemon(object? sender, EventArgs e) =>
        await Shell.Current.GoToAsync("//pokemon");

    private async void OnAddClicked(object? sender, EventArgs e) =>
        await Shell.Current.GoToAsync("addteam");

    private async void OnTeamTapped(object? sender, TappedEventArgs e)
    {
        if (sender is VisualElement el && el.BindingContext is StoredTeam t)
            await Shell.Current.GoToAsync($"addteam?id={t.Id}");
    }

    private async void OnTeamLongPressed(object? sender, TappedEventArgs e)
    {
        if (sender is VisualElement el && el.BindingContext is StoredTeam t)
        {
            bool confirm = await DisplayAlert("删除", $"确定删除队伍 {t.Name}？", "删除", "取消");
            if (confirm) await _vm.DeleteAsync(t);
        }
    }
}
