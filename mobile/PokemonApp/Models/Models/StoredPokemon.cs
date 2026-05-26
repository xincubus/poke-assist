using SQLite;

namespace PokemonApp.Models;

[Table("pokemons")]
public class StoredPokemon
{
    [PrimaryKey, AutoIncrement]
    public int Id { get; set; }

    // 基本信息
    public int PokedexId { get; set; }          // 图鉴编号（用于查图片）
    public string Name { get; set; } = string.Empty;
    public string NameEn { get; set; } = string.Empty;
    public string NameJa { get; set; } = string.Empty;
    public string ImageUrl { get; set; } = string.Empty;
    public string Type1 { get; set; } = string.Empty;
    public string Type2 { get; set; } = string.Empty;

    // 种族值（从数据库自动填充）
    public int BaseHp { get; set; }
    public int BaseAttack { get; set; }
    public int BaseDefense { get; set; }
    public int BaseSpAttack { get; set; }
    public int BaseSpDefense { get; set; }
    public int BaseSpeed { get; set; }

    // 个体值（默认31）
    public int IvHp { get; set; } = 31;
    public int IvAttack { get; set; } = 31;
    public int IvDefense { get; set; } = 31;
    public int IvSpAttack { get; set; } = 31;
    public int IvSpDefense { get; set; } = 31;
    public int IvSpeed { get; set; } = 31;

    // 努力值（默认0）
    public int EvHp { get; set; } = 0;
    public int EvAttack { get; set; } = 0;
    public int EvDefense { get; set; } = 0;
    public int EvSpAttack { get; set; } = 0;
    public int EvSpDefense { get; set; } = 0;
    public int EvSpeed { get; set; } = 0;

    // 配置
    public string Nature { get; set; } = "勤奋";
    public string Ability { get; set; } = string.Empty;
    public string Item { get; set; } = string.Empty;

    // 配招（4个槽）
    public string Move1 { get; set; } = string.Empty;
    public string Move2 { get; set; } = string.Empty;
    public string Move3 { get; set; } = string.Empty;
    public string Move4 { get; set; } = string.Empty;

    // 特性列表（逗号分隔，用于下拉）
    [Ignore]
    public string Ability1 { get; set; } = string.Empty;
    [Ignore]
    public string Ability2 { get; set; } = string.Empty;
    [Ignore]
    public string HiddenAbility { get; set; } = string.Empty;

    [Ignore]
    public int EvTotal => EvHp + EvAttack + EvDefense + EvSpAttack + EvSpDefense + EvSpeed;
}
