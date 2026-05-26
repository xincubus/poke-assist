namespace PokemonApp.Models;

public class TeamInfo
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public List<PokemonInfo> Members { get; set; } = new();
}
