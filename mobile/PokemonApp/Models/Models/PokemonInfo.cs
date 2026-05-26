namespace PokemonApp.Models;

public class PokemonInfo
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public string ImageUrl { get; set; } = string.Empty;
    public int Hp { get; set; }
    public int Attack { get; set; }
    public int Defense { get; set; }
    public int SpAttack { get; set; }
    public int SpDefense { get; set; }
    public int Speed { get; set; }
    public string Nature { get; set; } = string.Empty;
    public string Ability { get; set; } = string.Empty;
    public string Item { get; set; } = string.Empty;
}
