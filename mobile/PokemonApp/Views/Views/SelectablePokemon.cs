using System.ComponentModel;
using PokemonApp.Models;

namespace PokemonApp.Views;

/// <summary>宝可梦选择项，带选中状态</summary>
public class SelectablePokemon : INotifyPropertyChanged
{
    public StoredPokemon Pokemon { get; }
    public int Id => Pokemon.Id;
    public string Name => Pokemon.Name;
    public string ImageUrl => Pokemon.ImageUrl;

    private bool _isSelected;
    public bool IsSelected
    {
        get => _isSelected;
        set
        {
            _isSelected = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsSelected)));
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(SelectionColor)));
        }
    }

    public Color SelectionColor => IsSelected ? Color.FromArgb("#5B75F5") : Color.FromArgb("#FFFFFF");

    public SelectablePokemon(StoredPokemon pokemon, bool selected = false)
    {
        Pokemon = pokemon;
        _isSelected = selected;
    }

    public event PropertyChangedEventHandler? PropertyChanged;
}
