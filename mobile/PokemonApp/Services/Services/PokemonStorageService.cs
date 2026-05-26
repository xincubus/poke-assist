using SQLite;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using PokemonApp.Models;

namespace PokemonApp.Services;

public class PokemonStorageService
{
    private readonly SQLiteAsyncConnection _db;
    private readonly HttpClient _httpClient;

    public PokemonStorageService()
    {
        var dbPath = Path.Combine(FileSystem.AppDataDirectory, "chat_history.db");
        _db = new SQLiteAsyncConnection(dbPath);
        _db.CreateTableAsync<StoredPokemon>().Wait();
        _db.CreateTableAsync<StoredTeam>().Wait();
        _httpClient = new HttpClient { BaseAddress = new Uri(ApiConfig.BaseUrl), Timeout = TimeSpan.FromSeconds(10) };
    }

    // --- Pokemon ---
    public Task<List<StoredPokemon>> GetAllPokemonsAsync() =>
        _db.Table<StoredPokemon>().ToListAsync();

    public async Task SavePokemonAsync(StoredPokemon pokemon)
    {
        if (pokemon.Id == 0)
            await _db.InsertAsync(pokemon);
        else
            await _db.UpdateAsync(pokemon);
        _ = SyncPokemonToServerAsync();
    }

    public async Task DeletePokemonAsync(int id)
    {
        await _db.DeleteAsync<StoredPokemon>(id);
        _ = SyncPokemonToServerAsync();
    }

    // --- Team ---
    public Task<List<StoredTeam>> GetAllTeamsAsync() =>
        _db.Table<StoredTeam>().ToListAsync();

    public async Task SaveTeamAsync(StoredTeam team)
    {
        if (team.Id == 0)
            await _db.InsertAsync(team);
        else
            await _db.UpdateAsync(team);
        _ = SyncTeamsToServerAsync();
    }

    public async Task DeleteTeamAsync(int id)
    {
        await _db.DeleteAsync<StoredTeam>(id);
        _ = SyncTeamsToServerAsync();
    }

    public Task<StoredTeam?> GetTeamAsync(int id) =>
        _db.FindAsync<StoredTeam>(id);

    // --- Server Sync ---
    private async Task SyncPokemonToServerAsync()
    {
        try
        {
            var token = await SecureStorage.GetAsync("token");
            if (string.IsNullOrEmpty(token)) return;

            var all = await GetAllPokemonsAsync();
            var payload = new
            {
                pokemon = all.Select(p => new
                {
                    name = p.Name, name_en = p.NameEn,
                    base_hp = p.BaseHp, base_attack = p.BaseAttack, base_defense = p.BaseDefense,
                    base_sp_attack = p.BaseSpAttack, base_sp_defense = p.BaseSpDefense, base_speed = p.BaseSpeed,
                    ev_hp = p.EvHp, ev_attack = p.EvAttack, ev_defense = p.EvDefense,
                    ev_sp_attack = p.EvSpAttack, ev_sp_defense = p.EvSpDefense, ev_speed = p.EvSpeed,
                    nature = p.Nature, ability = p.Ability, item = p.Item,
                    move1 = p.Move1, move2 = p.Move2, move3 = p.Move3, move4 = p.Move4,
                }).ToList()
            };
            var request = new HttpRequestMessage(HttpMethod.Post, "/api/user/pokemon/sync")
            {
                Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
            };
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            await _httpClient.SendAsync(request);
        }
        catch { }
    }

    private async Task SyncTeamsToServerAsync()
    {
        try
        {
            var token = await SecureStorage.GetAsync("token");
            if (string.IsNullOrEmpty(token)) return;

            var allTeams = await GetAllTeamsAsync();
            var allPokemon = await GetAllPokemonsAsync();
            var pokemonMap = allPokemon.ToDictionary(p => p.Id, p => p.Name);

            var payload = new
            {
                teams = allTeams.Select(t => new
                {
                    name = t.Name,
                    members = t.MemberIdList
                        .Where(id => pokemonMap.ContainsKey(id))
                        .Select(id => pokemonMap[id])
                        .ToList()
                }).ToList()
            };
            var request = new HttpRequestMessage(HttpMethod.Post, "/api/user/teams/sync")
            {
                Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
            };
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            await _httpClient.SendAsync(request);
        }
        catch { }
    }
}
