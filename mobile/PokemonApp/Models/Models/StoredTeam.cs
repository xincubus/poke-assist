using SQLite;

namespace PokemonApp.Models;

[Table("teams")]
public class StoredTeam
{
    [PrimaryKey, AutoIncrement]
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    /// <summary>成员 StoredPokemon.Id，逗号分隔，最多6个</summary>
    public string MemberIds { get; set; } = string.Empty;

    [Ignore]
    public List<int> MemberIdList =>
        string.IsNullOrEmpty(MemberIds)
            ? new List<int>()
            : MemberIds.Split(',', StringSplitOptions.RemoveEmptyEntries)
                       .Select(int.Parse).ToList();

    [Ignore]
    public int MemberCount => MemberIdList.Count;
}
