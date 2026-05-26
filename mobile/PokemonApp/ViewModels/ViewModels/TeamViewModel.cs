using System.Collections.ObjectModel;
using PokemonApp.Models;
using PokemonApp.Services;

namespace PokemonApp.ViewModels;

public class TeamViewModel : BaseViewModel
{
    private readonly PokemonStorageService _storage;
    public ObservableCollection<StoredTeam> Teams { get; } = new();

    public TeamViewModel(PokemonStorageService storage)
    {
        _storage = storage;
    }

    public async Task LoadAsync()
    {
        var list = await _storage.GetAllTeamsAsync();
        Teams.Clear();
        foreach (var t in list) Teams.Add(t);
    }

    public async Task DeleteAsync(StoredTeam team)
    {
        await _storage.DeleteTeamAsync(team.Id);
        Teams.Remove(team);
    }
}
