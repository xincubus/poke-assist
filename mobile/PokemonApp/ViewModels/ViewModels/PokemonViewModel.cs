using System.Collections.ObjectModel;
using PokemonApp.Models;
using PokemonApp.Services;

namespace PokemonApp.ViewModels;

public class PokemonViewModel : BaseViewModel
{
    private readonly PokemonStorageService _storage;
    public ObservableCollection<StoredPokemon> Pokemons { get; } = new();

    public PokemonViewModel(PokemonStorageService storage)
    {
        _storage = storage;
    }

    public async Task LoadAsync()
    {
        var list = await _storage.GetAllPokemonsAsync();
        Pokemons.Clear();
        foreach (var p in list) Pokemons.Add(p);
    }

    public async Task DeleteAsync(StoredPokemon pokemon)
    {
        await _storage.DeletePokemonAsync(pokemon.Id);
        Pokemons.Remove(pokemon);
    }
}
