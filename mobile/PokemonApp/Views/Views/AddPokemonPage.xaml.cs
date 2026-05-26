using System.Collections.ObjectModel;
using System.ComponentModel;
using PokemonApp.Models;
using PokemonApp.Services;
#if ANDROID
using Android.Text;
using Android.Widget;
#endif

namespace PokemonApp.Views;

[QueryProperty(nameof(PokemonId), "id")]
public partial class AddPokemonPage : ContentPage, INotifyPropertyChanged
{
    private readonly PokemonStorageService _storage;
    private readonly PokemonDbService _db;
    private StoredPokemon _pokemon = new();
    private CancellationTokenSource? _searchCts;
    private CancellationTokenSource? _itemSearchCts;
    private CancellationTokenSource? _moveSearchCts;
    private bool _suppressSearch;      // 选中后抑制搜索
    private bool _suppressItemSearch;  // 道具选中后抑制搜索
    private bool _suppressMoveSearch;  // 招式选中后抑制搜索

    // --- 基本信息 ---
    public string PageTitle => _pokemon.Id == 0 ? "添加宝可梦" : "编辑宝可梦";

    private bool _hasPokemon;
    public bool HasPokemon { get => _hasPokemon; set { _hasPokemon = value; OnProp(); } }

    private string _searchKeyword = string.Empty;
    public string SearchKeyword { get => _searchKeyword; set { _searchKeyword = value; OnProp(); } }

    private bool _isSearching;
    public bool IsSearching { get => _isSearching; set { _isSearching = value; OnProp(); } }

    private bool _showDropdown;
    public bool ShowDropdown { get => _showDropdown; set { _showDropdown = value; OnProp(); } }

    public ObservableCollection<PokemonSearchItem> SearchResults { get; } = new();

    // --- 选中宝可梦展示 ---
    private string _selectedImageUrl = string.Empty;
    public string SelectedImageUrl { get => _selectedImageUrl; set { _selectedImageUrl = value; OnProp(); } }
    private string _selectedNameZh = string.Empty;
    public string SelectedNameZh { get => _selectedNameZh; set { _selectedNameZh = value; OnProp(); } }
    private string _selectedNameEn = string.Empty;
    public string SelectedNameEn { get => _selectedNameEn; set { _selectedNameEn = value; OnProp(); } }
    private string _selectedType1 = string.Empty;
    public string SelectedType1 { get => _selectedType1; set { _selectedType1 = value; OnProp(); OnProp(nameof(HasType1)); } }
    private string _selectedType2 = string.Empty;
    public string SelectedType2 { get => _selectedType2; set { _selectedType2 = value; OnProp(); OnProp(nameof(HasType2)); } }
    public bool HasType1 => !string.IsNullOrEmpty(SelectedType1);
    public bool HasType2 => !string.IsNullOrEmpty(SelectedType2);

    private Color _type1Color = Color.FromArgb("#5B75F5");
    public Color Type1Color { get => _type1Color; set { _type1Color = value; OnProp(); } }
    private Color _type2Color = Color.FromArgb("#888888");
    public Color Type2Color { get => _type2Color; set { _type2Color = value; OnProp(); } }

    // --- 种族值 ---
    private int _baseHp, _baseAtk, _baseDef, _baseSpAtk, _baseSpDef, _baseSpd;
    public int BaseHp { get => _baseHp; set { _baseHp = value; OnProp(); OnProp(nameof(BaseAbilityHp)); RecalcStats(); } }
    public int BaseAttack { get => _baseAtk; set { _baseAtk = value; OnProp(); OnProp(nameof(BaseAbilityAttack)); RecalcStats(); } }
    public int BaseDefense { get => _baseDef; set { _baseDef = value; OnProp(); OnProp(nameof(BaseAbilityDefense)); RecalcStats(); } }
    public int BaseSpAttack { get => _baseSpAtk; set { _baseSpAtk = value; OnProp(); OnProp(nameof(BaseAbilitySpAttack)); RecalcStats(); } }
    public int BaseSpDefense { get => _baseSpDef; set { _baseSpDef = value; OnProp(); OnProp(nameof(BaseAbilitySpDefense)); RecalcStats(); } }
    public int BaseSpeed { get => _baseSpd; set { _baseSpd = value; OnProp(); OnProp(nameof(BaseAbilitySpeed)); RecalcStats(); } }

    // --- 基础能力值（种族值+31）---
    public int BaseAbilityHp => BaseHp + 31;
    public int BaseAbilityAttack => BaseAttack + 31;
    public int BaseAbilityDefense => BaseDefense + 31;
    public int BaseAbilitySpAttack => BaseSpAttack + 31;
    public int BaseAbilitySpDefense => BaseSpDefense + 31;
    public int BaseAbilitySpeed => BaseSpeed + 31;

    // --- 个体值（固定31，不显示在UI）---
    private int _ivHp = 31, _ivAtk = 31, _ivDef = 31, _ivSpAtk = 31, _ivSpDef = 31, _ivSpd = 31;
    public int IvHp { get => _ivHp; set { _ivHp = value; OnProp(); } }
    public int IvAttack { get => _ivAtk; set { _ivAtk = value; OnProp(); } }
    public int IvDefense { get => _ivDef; set { _ivDef = value; OnProp(); } }
    public int IvSpAttack { get => _ivSpAtk; set { _ivSpAtk = value; OnProp(); } }
    public int IvSpDefense { get => _ivSpDef; set { _ivSpDef = value; OnProp(); } }
    public int IvSpeed { get => _ivSpd; set { _ivSpd = value; OnProp(); } }

    // --- 能力点数（原努力值，单项最大32，总和最大66）---
    private int _evHp, _evAtk, _evDef, _evSpAtk, _evSpDef, _evSpd;
    public int EvHp { get => _evHp; set { _evHp = Clamp(value, 0, 32); OnProp(); RecalcStats(); } }
    public int EvAttack { get => _evAtk; set { _evAtk = Clamp(value, 0, 32); OnProp(); RecalcStats(); } }
    public int EvDefense { get => _evDef; set { _evDef = Clamp(value, 0, 32); OnProp(); RecalcStats(); } }
    public int EvSpAttack { get => _evSpAtk; set { _evSpAtk = Clamp(value, 0, 32); OnProp(); RecalcStats(); } }
    public int EvSpDefense { get => _evSpDef; set { _evSpDef = Clamp(value, 0, 32); OnProp(); RecalcStats(); } }
    public int EvSpeed { get => _evSpd; set { _evSpd = Clamp(value, 0, 32); OnProp(); RecalcStats(); } }

    public int EvTotal => EvHp + EvAttack + EvDefense + EvSpAttack + EvSpDefense + EvSpeed;
    public string EvTotalText => $"能力点数总和：{EvTotal}/66";
    public Color EvTotalColor => EvTotal > 66 ? Colors.Red : Color.FromArgb("#888888");

    // --- 实际能力值（Lv50简化计算）---
    private int _statHp, _statAtk, _statDef, _statSpAtk, _statSpDef, _statSpd;
    public int StatHp { get => _statHp; private set { _statHp = value; OnProp(); } }
    public int StatAttack { get => _statAtk; private set { _statAtk = value; OnProp(); } }
    public int StatDefense { get => _statDef; private set { _statDef = value; OnProp(); } }
    public int StatSpAttack { get => _statSpAtk; private set { _statSpAtk = value; OnProp(); } }
    public int StatSpDefense { get => _statSpDef; private set { _statSpDef = value; OnProp(); } }
    public int StatSpeed { get => _statSpd; private set { _statSpd = value; OnProp(); } }

    // --- 能力值颜色（性格增减）---
    private static Color DefaultStatColor =>
        Application.Current?.RequestedTheme == AppTheme.Dark ? Colors.White : Colors.Black;
    private Color _statAtkColor, _statDefColor, _statSpAtkColor, _statSpDefColor, _statSpdColor;
    public Color StatAttackColor { get => _statAtkColor; private set { _statAtkColor = value; OnProp(); } }
    public Color StatDefenseColor { get => _statDefColor; private set { _statDefColor = value; OnProp(); } }
    public Color StatSpAttackColor { get => _statSpAtkColor; private set { _statSpAtkColor = value; OnProp(); } }
    public Color StatSpDefenseColor { get => _statSpDefColor; private set { _statSpDefColor = value; OnProp(); } }
    public Color StatSpeedColor { get => _statSpdColor; private set { _statSpdColor = value; OnProp(); } }

    // --- 性格 ---
    public List<string> AllNatures => PokemonDbService.AllNatures;
    private string _selectedNature = "勤奋";
    public string SelectedNature { get => _selectedNature; set { _selectedNature = value; OnProp(); RecalcStats(); } }

    // --- 特性 ---
    public ObservableCollection<string> AvailableAbilities { get; } = new();
    private string _selectedAbility = string.Empty;
    public string SelectedAbility { get => _selectedAbility; set { _selectedAbility = value; OnProp(); } }

    // --- 道具 ---
    private string _itemSearchKeyword = string.Empty;
    public string ItemSearchKeyword { get => _itemSearchKeyword; set { _itemSearchKeyword = value; OnProp(); } }
    private bool _showItemDropdown;
    public bool ShowItemDropdown { get => _showItemDropdown; set { _showItemDropdown = value; OnProp(); } }
    public ObservableCollection<ItemSearchResult> ItemResults { get; } = new();

    // --- 配招 ---
    private string _moveSearch1 = string.Empty, _moveSearch2 = string.Empty,
                   _moveSearch3 = string.Empty, _moveSearch4 = string.Empty;
    public string MoveSearch1 { get => _moveSearch1; set { _moveSearch1 = value; OnProp(); } }
    public string MoveSearch2 { get => _moveSearch2; set { _moveSearch2 = value; OnProp(); } }
    public string MoveSearch3 { get => _moveSearch3; set { _moveSearch3 = value; OnProp(); } }
    public string MoveSearch4 { get => _moveSearch4; set { _moveSearch4 = value; OnProp(); } }

    private bool _showMove1, _showMove2, _showMove3, _showMove4;
    public bool ShowMoveDropdown1 { get => _showMove1; set { _showMove1 = value; OnProp(); } }
    public bool ShowMoveDropdown2 { get => _showMove2; set { _showMove2 = value; OnProp(); } }
    public bool ShowMoveDropdown3 { get => _showMove3; set { _showMove3 = value; OnProp(); } }
    public bool ShowMoveDropdown4 { get => _showMove4; set { _showMove4 = value; OnProp(); } }

    public ObservableCollection<MoveSearchResult> MoveResults1 { get; } = new();
    public ObservableCollection<MoveSearchResult> MoveResults2 { get; } = new();
    public ObservableCollection<MoveSearchResult> MoveResults3 { get; } = new();
    public ObservableCollection<MoveSearchResult> MoveResults4 { get; } = new();

    // QueryProperty
    public string PokemonId
    {
        set { if (int.TryParse(value, out var id) && id > 0) LoadExistingAsync(id); }
    }

    public AddPokemonPage(PokemonStorageService storage, PokemonDbService db)
    {
        _storage = storage;
        _db = db;
        InitializeComponent();
        BindingContext = this;

#if ANDROID
        // 直接在 Android 原生层监听文本变化，绕过 MAUI TextChanged 的 suppress 问题
        SetupNativeTextWatcher(MoveSearch1Entry, MoveResults1, v => ShowMoveDropdown1 = v);
        SetupNativeTextWatcher(MoveSearch2Entry, MoveResults2, v => ShowMoveDropdown2 = v);
        SetupNativeTextWatcher(MoveSearch3Entry, MoveResults3, v => ShowMoveDropdown3 = v);
        SetupNativeTextWatcher(MoveSearch4Entry, MoveResults4, v => ShowMoveDropdown4 = v);
#endif
    }

    // 记录 MAUI TextChanged 最近一次搜索的关键词，用于 Android 原生 TextWatcher 去重
    private string _lastMauiSearchKw = string.Empty;

#if ANDROID

    private void SetupNativeTextWatcher(Entry entry, ObservableCollection<MoveSearchResult> results, Action<bool> setVisible)
    {
        entry.HandlerChanged += (_, _) =>
        {
            if (entry.Handler?.PlatformView is Android.Widget.EditText editText)
            {
                editText.AddTextChangedListener(new NativeTextWatcher(text =>
                {
                    var kw = text.Trim();
                    // 如果 MAUI TextChanged 已经处理了相同关键词的搜索，跳过
                    if (kw == _lastMauiSearchKw) return;
            
                    _ = SearchMoveAsync(kw, results, setVisible, _moveSearchCts, skipSuppress: true);
                }));
            }
        };
    }

    private class NativeTextWatcher : Java.Lang.Object, ITextWatcher
    {
        private readonly Action<string> _onTextChanged;
        public NativeTextWatcher(Action<string> onTextChanged) => _onTextChanged = onTextChanged;
        public void BeforeTextChanged(Java.Lang.ICharSequence s, int start, int count, int after) { }
        public void OnTextChanged(Java.Lang.ICharSequence s, int start, int before, int count) { }
        public void AfterTextChanged(IEditable s) => _onTextChanged?.Invoke(s?.ToString() ?? "");
    }
#endif

    private async void LoadExistingAsync(int id)
    {
        var list = await _storage.GetAllPokemonsAsync();
        var p = list.FirstOrDefault(x => x.Id == id);
        if (p == null) return;
        // 先保存原始值（ApplyPokemonData 会清空 _pokemon 的 Item/Moves）
        var savedNature = p.Nature;
        var savedAbility = p.Ability;
        var savedItem = p.Item;
        var savedMove1 = p.Move1;
        var savedMove2 = p.Move2;
        var savedMove3 = p.Move3;
        var savedMove4 = p.Move4;

        _pokemon = p;

        // 填充 UI（ApplyPokemonData 会清空 Item/Moves，所以先调用它）
        SearchKeyword = p.Name;
        ApplyPokemonData(p.PokedexId, p.Name, p.NameEn, p.ImageUrl, p.Type1, p.Type2, "", "",
            p.BaseHp, p.BaseAttack, p.BaseDefense, p.BaseSpAttack, p.BaseSpDefense, p.BaseSpeed,
            p.Ability1, p.Ability2, p.HiddenAbility);

        // ApplyPokemonData 之后再设置努力值、性格、特性、道具、招式
        IvHp = p.IvHp; IvAttack = p.IvAttack; IvDefense = p.IvDefense;
        IvSpAttack = p.IvSpAttack; IvSpDefense = p.IvSpDefense; IvSpeed = p.IvSpeed;
        EvHp = p.EvHp; EvAttack = p.EvAttack; EvDefense = p.EvDefense;
        EvSpAttack = p.EvSpAttack; EvSpDefense = p.EvSpDefense; EvSpeed = p.EvSpeed;
        SelectedNature = AllNatures.FirstOrDefault(n => NatureName(n) == savedNature) ?? savedNature;
        // 特性：如果 AvailableAbilities 为空（数据库没有特性列表），直接用保存的特性
        if (AvailableAbilities.Count == 0 && !string.IsNullOrEmpty(savedAbility))
        {
            AvailableAbilities.Add(savedAbility);
        }
        SelectedAbility = savedAbility;
        // 道具和招式：直接设置搜索框和模型字段
        _suppressItemSearch = true;
        ItemSearchKeyword = savedItem;
        _pokemon.Item = savedItem;
        _suppressMoveSearch = true;
        MoveSearch1 = savedMove1; _pokemon.Move1 = savedMove1;
        _suppressMoveSearch = true;
        MoveSearch2 = savedMove2; _pokemon.Move2 = savedMove2;
        _suppressMoveSearch = true;
        MoveSearch3 = savedMove3; _pokemon.Move3 = savedMove3;
        _suppressMoveSearch = true;
        MoveSearch4 = savedMove4; _pokemon.Move4 = savedMove4;
        OnProp(nameof(PageTitle));
    }

    // --- 宝可梦搜索 ---
    private async void OnSearchTextChanged(object sender, Microsoft.Maui.Controls.TextChangedEventArgs e)
    {
        if (_suppressSearch) { _suppressSearch = false; return; }

        var kw = e.NewTextValue?.Trim() ?? string.Empty;
        if (kw.Length < 1) { ShowDropdown = false; return; }

        _searchCts?.Cancel();
        _searchCts = new CancellationTokenSource();
        var token = _searchCts.Token;

        try
        {
            await Task.Delay(300, token);
        }
        catch (TaskCanceledException) { return; }

        IsSearching = true;

        try
        {
            var results = await _db.SearchPokemonsAsync(kw);
            if (token.IsCancellationRequested) { IsSearching = false; return; }

            SearchResults.Clear();
            foreach (var r in results)
                SearchResults.Add(new PokemonSearchItem
                {
                    PokemonId = r.Id,
                    PokedexId = r.PokedexId,
                    NameZh = r.NameZh,
                    NameEn = r.NameEn,
                    NameJa = r.NameJa,
                    ImageUrl = BuildImageUrl(r.ImageOfficialArtwork),
                    Type1 = r.Type1Zh, Type2 = r.Type2Zh,
                    Type1Color = r.Type1Color, Type2Color = r.Type2Color,
                    BaseHp = r.Hp, BaseAttack = r.Attack, BaseDefense = r.Defense,
                    BaseSpAttack = r.SpAttack, BaseSpDefense = r.SpDefense, BaseSpeed = r.Speed,
                    Ability1 = r.Ability1Name, Ability2 = r.Ability2Name, HiddenAbility = r.HiddenAbilityName
                });
            ShowDropdown = SearchResults.Count > 0;
        }
        catch (Exception)
        {
            // 搜索异常静默处理
        }
        finally
        {
            IsSearching = false;
        }
    }

    private async void OnPokemonSelected(object sender, SelectionChangedEventArgs e)
    {
        if (e.CurrentSelection.FirstOrDefault() is not PokemonSearchItem item) return;
        ShowDropdown = false;
        _suppressSearch = true;
        SearchKeyword = item.NameZh;
        ApplyPokemonData(item.PokedexId, item.NameZh, item.NameEn, item.ImageUrl,
            item.Type1, item.Type2, item.Type1Color, item.Type2Color,
            item.BaseHp, item.BaseAttack, item.BaseDefense,
            item.BaseSpAttack, item.BaseSpDefense, item.BaseSpeed,
            item.Ability1, item.Ability2, item.HiddenAbility);

        // Mega 形态自动填充 Mega 石
        var megaStone = await _db.GetMegaStoneAsync(item.PokemonId);
        if (!string.IsNullOrEmpty(megaStone))
        {
            _suppressItemSearch = true;
            ItemSearchKeyword = megaStone;
            _pokemon.Item = megaStone;
        }

        if (sender is CollectionView cv) cv.SelectedItem = null;
    }

    private void ApplyPokemonData(int pokedexId, string nameZh, string nameEn, string imageUrl,
        string type1, string type2, string type1Color, string type2Color,
        int hp, int atk, int def, int spAtk, int spDef, int spd,
        string ab1, string ab2, string abH)
    {
        _pokemon.PokedexId = pokedexId;
        _pokemon.Name = nameZh;
        _pokemon.NameEn = nameEn;
        _pokemon.ImageUrl = imageUrl;
        _pokemon.Type1 = type1; _pokemon.Type2 = type2;
        _pokemon.BaseHp = hp; _pokemon.BaseAttack = atk; _pokemon.BaseDefense = def;
        _pokemon.BaseSpAttack = spAtk; _pokemon.BaseSpDefense = spDef; _pokemon.BaseSpeed = spd;
        _pokemon.Ability1 = ab1; _pokemon.Ability2 = ab2; _pokemon.HiddenAbility = abH;

        SelectedImageUrl = imageUrl;
        SelectedNameZh = nameZh;
        SelectedNameEn = nameEn;
        SelectedType1 = type1;
        SelectedType2 = type2;
        Type1Color = string.IsNullOrEmpty(type1Color) ? Color.FromArgb("#5B75F5") : Color.FromArgb(type1Color);
        Type2Color = string.IsNullOrEmpty(type2Color) ? Color.FromArgb("#888888") : Color.FromArgb(type2Color);
        // 直接赋私有字段，避免每个 setter 触发 RecalcStats()（否则先设 HP 时其他值还是 0）
        _baseHp = hp; _baseAtk = atk; _baseDef = def;
        _baseSpAtk = spAtk; _baseSpDef = spDef; _baseSpd = spd;
        OnProp(nameof(BaseHp)); OnProp(nameof(BaseAttack)); OnProp(nameof(BaseDefense));
        OnProp(nameof(BaseSpAttack)); OnProp(nameof(BaseSpDefense)); OnProp(nameof(BaseSpeed));
        OnProp(nameof(BaseAbilityHp)); OnProp(nameof(BaseAbilityAttack)); OnProp(nameof(BaseAbilityDefense));
        OnProp(nameof(BaseAbilitySpAttack)); OnProp(nameof(BaseAbilitySpDefense)); OnProp(nameof(BaseAbilitySpeed));

        // 特性下拉
        AvailableAbilities.Clear();
        if (!string.IsNullOrEmpty(ab1)) AvailableAbilities.Add(ab1);
        if (!string.IsNullOrEmpty(ab2)) AvailableAbilities.Add(ab2);
        if (!string.IsNullOrEmpty(abH)) AvailableAbilities.Add(abH);
        SelectedAbility = AvailableAbilities.FirstOrDefault() ?? string.Empty;

        // 重置所有配置（重选宝可梦时清空旧数据）
        // 直接赋私有字段，避免每个 setter 触发 RecalcStats()，最后统一算一次
        _ivHp = 31; _ivAtk = 31; _ivDef = 31;
        _ivSpAtk = 31; _ivSpDef = 31; _ivSpd = 31;
        _evHp = 0; _evAtk = 0; _evDef = 0;
        _evSpAtk = 0; _evSpDef = 0; _evSpd = 0;
        OnProp(nameof(IvHp)); OnProp(nameof(IvAttack)); OnProp(nameof(IvDefense));
        OnProp(nameof(IvSpAttack)); OnProp(nameof(IvSpDefense)); OnProp(nameof(IvSpeed));
        OnProp(nameof(EvHp)); OnProp(nameof(EvAttack)); OnProp(nameof(EvDefense));
        OnProp(nameof(EvSpAttack)); OnProp(nameof(EvSpDefense)); OnProp(nameof(EvSpeed));
        OnProp(nameof(EvTotal)); OnProp(nameof(EvTotalText)); OnProp(nameof(EvTotalColor));
        _selectedNature = AllNatures.FirstOrDefault(n => NatureName(n) == "勤奋") ?? "勤奋";
        OnProp(nameof(SelectedNature));
        // 清空模型字段
        _pokemon.Nature = "勤奋";
        _pokemon.Item = string.Empty;
        _pokemon.Move1 = string.Empty; _pokemon.Move2 = string.Empty;
        _pokemon.Move3 = string.Empty; _pokemon.Move4 = string.Empty;
        // 清空 UI 搜索框（每次设置前都重新抑制，防止 TextChanged 消耗 flag）
        _suppressItemSearch = true;
        ItemSearchKeyword = string.Empty;
        _suppressMoveSearch = true;
        MoveSearch1 = string.Empty;
        _suppressMoveSearch = true;
        MoveSearch2 = string.Empty;
        _suppressMoveSearch = true;
        MoveSearch3 = string.Empty;
        _suppressMoveSearch = true;
        MoveSearch4 = string.Empty;

        HasPokemon = true;
        RecalcStats();
    }

    // --- 努力值变化 ---
    private void OnEvChanged(object sender, Microsoft.Maui.Controls.TextChangedEventArgs e)
    {
        OnProp(nameof(EvTotal));
        OnProp(nameof(EvTotalText));
        OnProp(nameof(EvTotalColor));
    }

    // --- 能力值计算（基础能力值 + 能力点数）---
    private void RecalcStats()
    {
        StatHp = BaseHp + 31 + EvHp;
        StatAttack = BaseAttack + 31 + EvAttack;
        StatDefense = BaseDefense + 31 + EvDefense;
        StatSpAttack = BaseSpAttack + 31 + EvSpAttack;
        StatSpDefense = BaseSpDefense + 31 + EvSpDefense;
        StatSpeed = BaseSpeed + 31 + EvSpeed;

        var natMod = GetNatureModifier();
        StatAttackColor = NatColor(natMod[0]);
        StatDefenseColor = NatColor(natMod[1]);
        StatSpAttackColor = NatColor(natMod[2]);
        StatSpDefenseColor = NatColor(natMod[3]);
        StatSpeedColor = NatColor(natMod[4]);
    }

    // 返回 [atk, def, spAtk, spDef, spd] 的性格倍率
    private double[] GetNatureModifier()
    {
        var mods = new double[] { 1, 1, 1, 1, 1 };
        var name = NatureName(SelectedNature);
        var boostMap = new Dictionary<string, int>
        {
            {"怕寂寞",0},{"固执",0},{"顽皮",0},{"勇敢",0},
            {"大胆",1},{"淘气",1},{"乐天",1},{"悠闲",1},
            {"内敛",2},{"慢吞吞",2},{"马虎",2},{"冷静",2},
            {"温和",3},{"温顺",3},{"慎重",3},{"自大",3},
            {"胆小",4},{"急躁",4},{"爽朗",4},{"天真",4}
        };
        // 减少的能力
        var dropMap = new Dictionary<string, int>
        {
            {"大胆",0},{"内敛",0},{"温和",0},{"胆小",0},
            {"怕寂寞",1},{"慢吞吞",1},{"温顺",1},{"急躁",1},
            {"固执",2},{"淘气",2},{"慎重",2},{"爽朗",2},
            {"顽皮",3},{"乐天",3},{"马虎",3},{"天真",3},
            {"勇敢",4},{"悠闲",4},{"冷静",4},{"自大",4}
        };
        if (boostMap.TryGetValue(name, out var b)) mods[b] = 1.1;
        if (dropMap.TryGetValue(name, out var d)) mods[d] = 0.9;
        return mods;
    }

    // 从 "固执（+攻击，-特攻）" 提取纯名字 "固执"
    private static string NatureName(string display)
    {
        if (string.IsNullOrEmpty(display)) return display;
        var idx = display.IndexOf('（');
        return idx > 0 ? display[..idx] : display;
    }

    // 性格倍率 → 颜色：1.1=红(增加)，0.9=蓝(减少)，无修正=跟随系统主题
    private static Color NatColor(double mod) =>
        mod > 1.0 ? Color.FromArgb("#E74C3C") :
        mod < 1.0 ? Color.FromArgb("#3498DB") :
        DefaultStatColor;

    // --- 道具搜索 ---
    private async void OnItemSearchChanged(object sender, Microsoft.Maui.Controls.TextChangedEventArgs e)
    {
        if (_suppressItemSearch) { _suppressItemSearch = false; return; }

        var kw = e.NewTextValue?.Trim() ?? string.Empty;
        _itemSearchCts?.Cancel();
        if (kw.Length < 1) { ShowItemDropdown = false; return; }

        var cts = new CancellationTokenSource();
        _itemSearchCts = cts;
        var token = cts.Token;

        try { await Task.Delay(150, token); }
        catch (TaskCanceledException) { return; }

        // delay 结束后再次检查是否仍是最新的请求
        if (_itemSearchCts != cts) return;

        try
        {
            var results = await _db.SearchItemsAsync(kw);
            if (token.IsCancellationRequested || _itemSearchCts != cts) return;
            ItemResults.Clear();
            foreach (var r in results) ItemResults.Add(r);
            ShowItemDropdown = ItemResults.Count > 0;
        }
        catch { }
    }

    private void OnItemSelected(object sender, SelectionChangedEventArgs e)
    {
        if (e.CurrentSelection.FirstOrDefault() is not ItemSearchResult item) return;
        _suppressItemSearch = true;
        ItemSearchKeyword = item.DisplayName;
        _pokemon.Item = item.DisplayName;
        ShowItemDropdown = false;
        if (sender is CollectionView cv) cv.SelectedItem = null;
    }

    // --- 招式搜索（通用）---
    private async Task SearchMoveAsync(string kw, ObservableCollection<MoveSearchResult> results,
        Action<bool> setVisible, CancellationTokenSource? cts, bool skipSuppress = false)
    {
        if (!skipSuppress && _suppressMoveSearch) { _suppressMoveSearch = false; return; }

        // 记录 MAUI 路径已处理的关键词，供 Android 原生 TextWatcher 去重
        if (!skipSuppress) _lastMauiSearchKw = kw;

        if (kw.Length < 1) { setVisible(false); return; }
        cts?.Cancel();
        var newCts = new CancellationTokenSource();
        _moveSearchCts = newCts;
        var token = newCts.Token;

        try { await Task.Delay(300, token); }
        catch (TaskCanceledException) { return; }

        try
        {
            var res = await _db.SearchMovesAsync(kw, _pokemon.PokedexId);
            if (token.IsCancellationRequested) return;
            results.Clear();
            foreach (var r in res) results.Add(r);
            setVisible(results.Count > 0);
        }
        catch { }
    }

    private async void OnMove1SearchChanged(object s, Microsoft.Maui.Controls.TextChangedEventArgs e) =>
        await SearchMoveAsync(e.NewTextValue?.Trim() ?? "", MoveResults1, v => ShowMoveDropdown1 = v, _moveSearchCts);
    private async void OnMove2SearchChanged(object s, Microsoft.Maui.Controls.TextChangedEventArgs e) =>
        await SearchMoveAsync(e.NewTextValue?.Trim() ?? "", MoveResults2, v => ShowMoveDropdown2 = v, _moveSearchCts);
    private async void OnMove3SearchChanged(object s, Microsoft.Maui.Controls.TextChangedEventArgs e) =>
        await SearchMoveAsync(e.NewTextValue?.Trim() ?? "", MoveResults3, v => ShowMoveDropdown3 = v, _moveSearchCts);
    private async void OnMove4SearchChanged(object s, Microsoft.Maui.Controls.TextChangedEventArgs e) =>
        await SearchMoveAsync(e.NewTextValue?.Trim() ?? "", MoveResults4, v => ShowMoveDropdown4 = v, _moveSearchCts);

    private void SelectMove(SelectionChangedEventArgs e, Action<string> setSearch,
        ObservableCollection<MoveSearchResult> results, Action<bool> setVisible, Action<string> setMove)
    {
        if (e.CurrentSelection.FirstOrDefault() is not MoveSearchResult m) return;
        setSearch(m.DisplayName);
        setMove(m.DisplayName);
        setVisible(false);
        if (e.CurrentSelection.Count > 0 && results is not null)
            MainThread.BeginInvokeOnMainThread(() => { /* clear selection */ });
    }

    private void OnMove1Selected(object s, SelectionChangedEventArgs e)
    {
        if (e.CurrentSelection.FirstOrDefault() is not MoveSearchResult m) return;
        _suppressMoveSearch = true;
        MoveSearch1 = m.DisplayName; _pokemon.Move1 = m.DisplayName; ShowMoveDropdown1 = false;
        if (s is CollectionView cv) cv.SelectedItem = null;
    }
    private void OnMove2Selected(object s, SelectionChangedEventArgs e)
    {
        if (e.CurrentSelection.FirstOrDefault() is not MoveSearchResult m) return;
        _suppressMoveSearch = true;
        MoveSearch2 = m.DisplayName; _pokemon.Move2 = m.DisplayName; ShowMoveDropdown2 = false;
        if (s is CollectionView cv) cv.SelectedItem = null;
    }
    private void OnMove3Selected(object s, SelectionChangedEventArgs e)
    {
        if (e.CurrentSelection.FirstOrDefault() is not MoveSearchResult m) return;
        _suppressMoveSearch = true;
        MoveSearch3 = m.DisplayName; _pokemon.Move3 = m.DisplayName; ShowMoveDropdown3 = false;
        if (s is CollectionView cv) cv.SelectedItem = null;
    }
    private void OnMove4Selected(object s, SelectionChangedEventArgs e)
    {
        if (e.CurrentSelection.FirstOrDefault() is not MoveSearchResult m) return;
        _suppressMoveSearch = true;
        MoveSearch4 = m.DisplayName; _pokemon.Move4 = m.DisplayName; ShowMoveDropdown4 = false;
        if (s is CollectionView cv) cv.SelectedItem = null;
    }

    // --- 保存 ---
    private async void OnSaveClicked(object sender, EventArgs e)
    {
        if (!HasPokemon) return;
        _pokemon.IvHp = IvHp; _pokemon.IvAttack = IvAttack; _pokemon.IvDefense = IvDefense;
        _pokemon.IvSpAttack = IvSpAttack; _pokemon.IvSpDefense = IvSpDefense; _pokemon.IvSpeed = IvSpeed;
        _pokemon.EvHp = EvHp; _pokemon.EvAttack = EvAttack; _pokemon.EvDefense = EvDefense;
        _pokemon.EvSpAttack = EvSpAttack; _pokemon.EvSpDefense = EvSpDefense; _pokemon.EvSpeed = EvSpeed;
        _pokemon.Nature = NatureName(SelectedNature);
        _pokemon.Ability = SelectedAbility;
        _pokemon.Item = ItemSearchKeyword;
        _pokemon.Move1 = MoveSearch1; _pokemon.Move2 = MoveSearch2;
        _pokemon.Move3 = MoveSearch3; _pokemon.Move4 = MoveSearch4;
        await _storage.SavePokemonAsync(_pokemon);
        await Shell.Current.GoToAsync("..");
    }

    // --- 工具 ---
    // 输入框获取焦点时，自动滚动让下拉框可见（留出约3个选项的空间）
    private async void OnSearchEntryFocused(object sender, FocusEventArgs e)
    {
        if (sender is not VisualElement entry) return;
        // 等待键盘弹出和布局完成
        await Task.Delay(350);
        // 额外向下滚动 160dp，为下拉框留出空间（约3个选项高度）
        var scrollY = MainScrollView.ScrollY + 160;
        await MainScrollView.ScrollToAsync(MainScrollView.ScrollX, scrollY, true);
    }

    private static string BuildImageUrl(string path)
    {
        if (string.IsNullOrEmpty(path)) return string.Empty;
        if (path.StartsWith("http")) return path;
        return $"{ApiConfig.BaseUrl}/static/{path}";
    }

    private static int Clamp(int v, int min, int max) => Math.Max(min, Math.Min(max, v));

    public new event PropertyChangedEventHandler? PropertyChanged;
    private void OnProp([System.Runtime.CompilerServices.CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}

// 搜索结果展示用的轻量模型
public class PokemonSearchItem
{
    public int PokemonId { get; set; }
    public int PokedexId { get; set; }
    public string NameZh { get; set; } = string.Empty;
    public string NameEn { get; set; } = string.Empty;
    public string NameJa { get; set; } = string.Empty;
    public string ImageUrl { get; set; } = string.Empty;
    public string Type1 { get; set; } = string.Empty;
    public string Type2 { get; set; } = string.Empty;
    public string Type1Color { get; set; } = string.Empty;
    public string Type2Color { get; set; } = string.Empty;
    public int BaseHp { get; set; }
    public int BaseAttack { get; set; }
    public int BaseDefense { get; set; }
    public int BaseSpAttack { get; set; }
    public int BaseSpDefense { get; set; }
    public int BaseSpeed { get; set; }
    public string Ability1 { get; set; } = string.Empty;
    public string Ability2 { get; set; } = string.Empty;
    public string HiddenAbility { get; set; } = string.Empty;
}
