using System.Collections.ObjectModel;
using System.ComponentModel;
using PokemonApp.Models;
using PokemonApp.Services;

namespace PokemonApp.Views;

[QueryProperty(nameof(TeamId), "id")]
public partial class AddTeamPage : ContentPage, INotifyPropertyChanged
{
    private readonly PokemonStorageService _storage;
    private StoredTeam _team = new();

    public string PageTitle => _team.Id == 0 ? "创建队伍" : "编辑队伍";

    private string _teamName = string.Empty;
    public string TeamName
    {
        get => _teamName;
        set { _teamName = value; OnPropertyChanged(nameof(TeamName)); }
    }

    public ObservableCollection<SelectablePokemon> AllPokemons { get; } = new();

    public string TeamId
    {
        set
        {
            if (int.TryParse(value, out var id) && id > 0)
                LoadTeam(id);
        }
    }

    public AddTeamPage(PokemonStorageService storage)
    {
        _storage = storage;
        InitializeComponent();
        BindingContext = this;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await LoadPokemons();
    }

    private async Task LoadPokemons()
    {
        var pokemons = await _storage.GetAllPokemonsAsync();
        var selectedIds = _team.MemberIdList;
        AllPokemons.Clear();
        foreach (var p in pokemons)
            AllPokemons.Add(new SelectablePokemon(p, selectedIds.Contains(p.Id)));
    }

    private async void LoadTeam(int id)
    {
        var team = await _storage.GetTeamAsync(id);
        if (team != null)
        {
            _team = team;
            TeamName = team.Name;
            OnPropertyChanged(nameof(PageTitle));
            await LoadPokemons();
        }
    }

    private void OnPokemonTapped(object sender, TappedEventArgs e)
    {
        if (sender is VisualElement el && el.BindingContext is SelectablePokemon sp)
        {
            var selectedCount = AllPokemons.Count(p => p.IsSelected);
            if (!sp.IsSelected && selectedCount >= 6)
            {
                DisplayAlert("提示", "每支队伍最多6只宝可梦", "确定");
                return;
            }
            sp.IsSelected = !sp.IsSelected;
        }
    }

    private async void OnSaveClicked(object sender, EventArgs e)
    {
        if (string.IsNullOrWhiteSpace(TeamName))
        {
            await DisplayAlert("提示", "请输入队伍名称", "确定");
            return;
        }
        _team.Name = TeamName;
        _team.MemberIds = string.Join(",", AllPokemons.Where(p => p.IsSelected).Select(p => p.Id));
        await _storage.SaveTeamAsync(_team);
        await Shell.Current.GoToAsync("..");
    }

    public new event PropertyChangedEventHandler? PropertyChanged;
    protected void OnPropertyChanged(string name) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
