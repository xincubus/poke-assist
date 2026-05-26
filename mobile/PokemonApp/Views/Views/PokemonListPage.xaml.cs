using PokemonApp.Models;
using PokemonApp.ViewModels;

namespace PokemonApp.Views;

public partial class PokemonListPage : ContentPage
{
    private readonly PokemonViewModel _vm;

    public PokemonListPage(PokemonViewModel vm)
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

    private async void GoToTeams(object? sender, EventArgs e) =>
        await Shell.Current.GoToAsync("//teams");

    private async void OnAddClicked(object? sender, EventArgs e) =>
        await Shell.Current.GoToAsync("addpokemon");

    private async void OnPokemonTapped(object? sender, TappedEventArgs e)
    {
        if (sender is VisualElement el && el.BindingContext is StoredPokemon p)
            await Shell.Current.GoToAsync($"addpokemon?id={p.Id}");
    }
}
