/**
 * NCP VGC Damage Calculator — Node.js 入口
 * 从 web/cale/ 提取的计算引擎，无需浏览器/DOM
 */

var path = require('path');
var fs = require('fs');
var vm = require('vm');
var caleDir = __dirname;

function getDamageRange(damage) {
    if (Array.isArray(damage[0])) {
        var minTotal = 0, maxTotal = 0;
        for (var h = 0; h < damage.length; h++) {
            minTotal += damage[h][0];
            maxTotal += damage[h][damage[h].length - 1];
        }
        return [minTotal, maxTotal];
    }
    return [damage[0], damage[damage.length - 1]];
}

// ========== jQuery polyfill ($.extend + DOM stubs) ==========
function deepExtend(deep, target) {
    var args, i, src, copy, clone;
    if (typeof deep !== 'boolean') {
        target = deep;
        deep = false;
        args = Array.prototype.slice.call(arguments, 1);
    } else {
        args = Array.prototype.slice.call(arguments, 2);
    }
    if (!target) target = {};
    for (i = 0; i < args.length; i++) {
        var options = args[i];
        if (options == null) continue;
        for (var name in options) {
            src = target[name];
            copy = options[name];
            if (target === copy) continue;
            if (deep && copy && (typeof copy === 'object' || Array.isArray(copy))) {
                if (src && (typeof src === 'object' || Array.isArray(src))) {
                    target[name] = deepExtend(deep, Array.isArray(src) ? src.slice() : Object.assign({}, src), copy);
                } else {
                    clone = Array.isArray(copy) ? [] : {};
                    target[name] = deepExtend(deep, clone, copy);
                }
            } else if (copy !== undefined) {
                target[name] = copy;
            }
        }
    }
    return target;
}

var _noop = { val: function(){}, is: function(){return false;}, prop: function(){return false;}, find: function(){return _noop;}, text: function(){return _noop;} };
global.$ = function () { return _noop; };
$.extend = deepExtend;

// ========== Load files into global scope ==========
// NCP data files use `var` at top level, which in require() would be module-scoped.
// We use vm.runInThisContext to execute them in the global scope.
function loadGlobal(filename) {
    var code = fs.readFileSync(path.join(caleDir, filename), 'utf-8');
    vm.runInThisContext(code, { filename: filename });
}

// Load data files
loadGlobal('stat_data.js');
loadGlobal('nature_data.js');
loadGlobal('type_data.js');
loadGlobal('item_data.js');
loadGlobal('ability_data.js');
loadGlobal('pokedex.js');
loadGlobal('move_data.js');
loadGlobal('cooldown_za.js');

// Load calc engine
loadGlobal('damage_MASTER.js');
loadGlobal('damage_SV.js');
loadGlobal('ko_chance.js');

// ========== Globals expected by the calc engine ==========
global.gen = 10; // Champions
global.pokedex = {};
global.typeChart = {};
global.moves = {};
global.abilities = [];
global.items = [];
global.STATS = [];
global.calculateAllMoves = null;
global.calcHP = null;
global.calcStat = null;
global.transformSpecies = { p1: '', p2: '' };
global.lastHighestStat = [0, 0];
global.resultDisplayMode = 'SPs';
global._calcConfig = {};
global.attacker_name = '';
global.defender_name = '';
global.autoLevel = 50;
global.isCustomMods = false;

// ========== Normalize: 只保留英文字母，小写 ==========
function normalize(s) { return s.replace(/[^a-zA-Z]/g, '').toLowerCase(); }

var normalizedMoves = {};
var normalizedPokedex = {};
var normalizedNatures = {};
var normalizedAbilities = {};
var normalizedItems = {};
var normalizedWeather = {};
var normalizedTerrain = {};
var normalizedStatus = {};

function buildNormalizeMaps() {
    normalizedMoves = {};
    for (var key in moves) normalizedMoves[normalize(key)] = key;

    normalizedPokedex = {};
    for (var key in pokedex) normalizedPokedex[normalize(key)] = key;

    normalizedNatures = {};
    for (var key in NATURES) normalizedNatures[normalize(key)] = key;

    normalizedAbilities = {};
    for (var i = 0; i < abilities.length; i++) normalizedAbilities[normalize(abilities[i])] = abilities[i];

    normalizedItems = {};
    for (var i = 0; i < items.length; i++) normalizedItems[normalize(items[i])] = items[i];

    normalizedWeather = {};
    ['Sun','Rain','Sand','Snow','Harsh Sun','Heavy Rain','Strong Winds'].forEach(function(w) {
        normalizedWeather[normalize(w)] = w;
    });

    normalizedTerrain = {};
    ['Electric','Grassy','Misty','Psychic'].forEach(function(t) {
        normalizedTerrain[normalize(t)] = t;
    });

    normalizedStatus = {};
    ['Burned','Paralyzed','Asleep','Poisoned','Badly Poisoned','Drowsy','Frozen'].forEach(function(s) {
        normalizedStatus[normalize(s)] = s;
    });
}

// setHasTypeFunc: creates .hasType() on Pokemon objects
global.setHasTypeFunc = function () {
    for (var t of arguments) {
        if ([this.type1, this.type2].includes(t)) {
            return true;
        }
    }
    return false;
};

// ========== Set generation and data ==========
function setGeneration(g) {
    global.gen = g;
    switch (g) {
        case 1:
            pokedex = typeof POKEDEX_RBY !== 'undefined' ? POKEDEX_RBY : {};
            typeChart = typeof TYPE_CHART_RBY !== 'undefined' ? TYPE_CHART_RBY : {};
            moves = typeof MOVES_RBY !== 'undefined' ? MOVES_RBY : {};
            abilities = typeof ABILITIES_ADV !== 'undefined' ? ABILITIES_ADV : [];
            items = typeof ITEMS_GSC !== 'undefined' ? ITEMS_GSC : [];
            STATS = STATS_RBY;
            calcHP = CALC_HP_RBY;
            calcStat = CALC_STAT_RBY;
            break;
        case 2:
            pokedex = typeof POKEDEX_GSC !== 'undefined' ? POKEDEX_GSC : {};
            typeChart = typeof TYPE_CHART_GSC !== 'undefined' ? TYPE_CHART_GSC : {};
            moves = typeof MOVES_GSC !== 'undefined' ? MOVES_GSC : {};
            abilities = typeof ABILITIES_ADV !== 'undefined' ? ABILITIES_ADV : [];
            items = typeof ITEMS_GSC !== 'undefined' ? ITEMS_GSC : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 3:
            pokedex = typeof POKEDEX_ADV !== 'undefined' ? POKEDEX_ADV : {};
            typeChart = typeof TYPE_CHART_BW !== 'undefined' ? TYPE_CHART_BW : {};
            moves = typeof MOVES_ADV !== 'undefined' ? MOVES_ADV : {};
            abilities = typeof ABILITIES_ADV !== 'undefined' ? ABILITIES_ADV : [];
            items = typeof ITEMS_ADV !== 'undefined' ? ITEMS_ADV : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 4:
            pokedex = typeof POKEDEX_DPP !== 'undefined' ? POKEDEX_DPP : {};
            typeChart = typeof TYPE_CHART_BW !== 'undefined' ? TYPE_CHART_BW : {};
            moves = typeof MOVES_DPP !== 'undefined' ? MOVES_DPP : {};
            abilities = typeof ABILITIES_DPP !== 'undefined' ? ABILITIES_DPP : [];
            items = typeof ITEMS_DPP !== 'undefined' ? ITEMS_DPP : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 5:
            pokedex = typeof POKEDEX_BW !== 'undefined' ? POKEDEX_BW : {};
            typeChart = typeof TYPE_CHART_BW !== 'undefined' ? TYPE_CHART_BW : {};
            moves = typeof MOVES_BW !== 'undefined' ? MOVES_BW : {};
            abilities = typeof ABILITIES_XY !== 'undefined' ? ABILITIES_XY : [];
            items = typeof ITEMS_XY !== 'undefined' ? ITEMS_XY : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 6:
            pokedex = typeof POKEDEX_XY !== 'undefined' ? POKEDEX_XY : {};
            typeChart = typeof TYPE_CHART_XY !== 'undefined' ? TYPE_CHART_XY : {};
            moves = typeof MOVES_XY !== 'undefined' ? MOVES_XY : {};
            abilities = typeof ABILITIES_XY !== 'undefined' ? ABILITIES_XY : [];
            items = typeof ITEMS_XY !== 'undefined' ? ITEMS_XY : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 7:
            pokedex = typeof POKEDEX_SM !== 'undefined' ? POKEDEX_SM : {};
            typeChart = typeof TYPE_CHART_SV !== 'undefined' ? TYPE_CHART_SV : {};
            moves = typeof MOVES_SM !== 'undefined' ? MOVES_SM : {};
            abilities = typeof ABILITIES_SV !== 'undefined' ? ABILITIES_SV : [];
            items = typeof ITEMS_SM !== 'undefined' ? ITEMS_SM : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 8:
            pokedex = typeof POKEDEX_SS_NATDEX !== 'undefined' ? POKEDEX_SS_NATDEX : {};
            typeChart = typeof TYPE_CHART_SV !== 'undefined' ? TYPE_CHART_SV : {};
            moves = typeof MOVES_SS !== 'undefined' ? MOVES_SS : {};
            abilities = typeof ABILITIES_SV !== 'undefined' ? ABILITIES_SV : [];
            items = typeof ITEMS_SS !== 'undefined' ? ITEMS_SS : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 9:
        case 9.5:
            pokedex = typeof POKEDEX_SV_NATDEX !== 'undefined' ? POKEDEX_SV_NATDEX : {};
            typeChart = typeof TYPE_CHART_SV !== 'undefined' ? TYPE_CHART_SV : {};
            moves = typeof MOVES_SV !== 'undefined' ? MOVES_SV : {};
            abilities = typeof ABILITIES_SV !== 'undefined' ? ABILITIES_SV : [];
            items = typeof ITEMS_SV !== 'undefined' ? ITEMS_SV : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
            break;
        case 10:
            pokedex = typeof POKEDEX_CHAMPIONS !== 'undefined' ? POKEDEX_CHAMPIONS : {};
            typeChart = typeof TYPE_CHART_SV !== 'undefined' ? TYPE_CHART_SV : {};
            moves = typeof MOVES_ZA_NATDEX !== 'undefined' ? MOVES_ZA_NATDEX : {};
            abilities = typeof ABILITIES_CHAMPIONS !== 'undefined' ? ABILITIES_CHAMPIONS : [];
            items = typeof ITEMS_CHAMPIONS !== 'undefined' ? ITEMS_CHAMPIONS : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_CHAMP;
            calcStat = CALC_STAT_CHAMP;
            break;
        default:
            pokedex = typeof POKEDEX_SV_NATDEX !== 'undefined' ? POKEDEX_SV_NATDEX : {};
            typeChart = typeof TYPE_CHART_SV !== 'undefined' ? TYPE_CHART_SV : {};
            moves = typeof MOVES_SV !== 'undefined' ? MOVES_SV : {};
            abilities = typeof ABILITIES_SV !== 'undefined' ? ABILITIES_SV : [];
            items = typeof ITEMS_SV !== 'undefined' ? ITEMS_SV : [];
            STATS = STATS_GSC;
            calcHP = CALC_HP_ADV;
            calcStat = CALC_STAT_ADV;
    }
    buildNormalizeMaps();
}

// ========== Build Pokemon object from params ==========
var LONG_TO_SHORT = { hp: 'hp', atk: 'at', def: 'df', spa: 'sa', spd: 'sd', spe: 'sp' };

function normalizeStatsDict(dict) {
    if (!dict) return {};
    var out = {};
    for (var k in dict) {
        out[LONG_TO_SHORT[k] || k] = dict[k];
    }
    return out;
}

function buildPokemon(params) {
    var nameNorm = normalize(params.name);
    var formNorm = params.form ? normalize(params.form) : '';
    var name;

    if (formNorm) {
        // 尝试 name+form（后缀式：Aegislash-Shield, Basculegion-F）
        name = normalizedPokedex[nameNorm + formNorm]
            // 尝试 form+name（前缀式：Mega Absol）
            || normalizedPokedex[formNorm + nameNorm]
            // 兜底：默认形态，用 base name
            || normalizedPokedex[nameNorm]
            || params.name;
    } else {
        name = normalizedPokedex[nameNorm] || params.name;
    }
    var level = params.level || 50;
    var pokeData = pokedex[name] || {};
    var isDynamax = params.isDynamax || false;
    var isGen10 = gen === 10;

    var nature = normalizedNatures[normalize(params.nature || 'Serious')] || params.nature || 'Serious';
    var natureMods = NATURES[nature] || ['', ''];

    // Normalize evs/ivs/boosts from long keys (atk, spa, etc.) to short keys (at, sa, etc.)
    var evs = normalizeStatsDict(params.evs);
    var ivs = normalizeStatsDict(params.ivs);
    var boosts = normalizeStatsDict(params.boosts);
    var sps = normalizeStatsDict(params.sps);

    // Determine stat keys based on generation
    var statKeys = STATS;
    var pokemon = {
        name: name,
        type1: pokeData.t1 || 'Normal',
        type2: pokeData.t2 || '',
        tera_type: params.teraType || '',
        level: isGen10 ? 50 : level,
        maxHP: 0,
        curHP: 0,
        HPSPs: 0,
        HPEVs: evs.hp || 0,
        HPIVs: ivs.hp !== undefined ? ivs.hp : 31,
        HPraw: 0,
        isDynamax: isDynamax,
        gmax_factor: params.gmax_factor || false,
        isTerastalize: params.isTerastalize || false,
        rawStats: {},
        stats: {},
        boosts: {},
        sps: {},
        evs: {},
        ivs: {},
        nature: nature,
        ability: params.ability ? (normalizedAbilities[normalize(params.ability)] || params.ability) : (pokeData.ab ? pokeData.ab : ''),
        abilityOn: params.abilityOn !== undefined ? params.abilityOn : true,
        supremeOverlord: params.supremeOverlord || 0,
        rivalryGender: params.rivalryGender || '',
        highestStat: params.highestStat !== undefined ? params.highestStat : -1,
        item: params.item ? (normalizedItems[normalize(params.item)] || params.item) : '',
        status: params.status ? (normalizedStatus[normalize(params.status)] || params.status) : '',
        toxicCounter: params.toxicCounter || 0,
        moves: [],
        glaiveRushMod: params.glaiveRushMod || false,
        weight: params.weight || (pokeData.w || 0),
        canEvolve: pokeData.canEvolve || false,
        isTransformed: params.isTransformed || false,
        customModifiers: null,
        hasCustomModifiers: false,
        hasType: setHasTypeFunc,
    };

    // Calculate HP first (not in STATS array)
    if (isGen10) {
        pokemon.maxHP = CALC_HP_CHAMP(pokeData.bs ? (pokeData.bs.hp || 0) : 0, sps.hp || 0, isDynamax);
    } else {
        pokemon.maxHP = CALC_HP_ADV(pokeData.bs ? (pokeData.bs.hp || 0) : 0, evs.hp || 0, ivs.hp !== undefined ? ivs.hp : 31, pokemon.level, isDynamax);
    }
    pokemon.HPraw = pokemon.maxHP;
    pokemon.HPSPs = sps.hp || 0;
    pokemon.HPEVs = evs.hp || 0;
    pokemon.HPIVs = ivs.hp !== undefined ? ivs.hp : 31;

    // Calculate other stats
    for (var i = 0; i < statKeys.length; i++) {
        var sk = statKeys[i];
        var baseStat = pokeData.bs ? (pokeData.bs[sk] || 0) : 0;
        var ev = evs[sk] || 0;
        var iv = ivs[sk] !== undefined ? ivs[sk] : 31;
        var natureBoost = natureMods[0] === sk ? 1.1 : natureMods[1] === sk ? 0.9 : 1;
        var statPoints = sps[sk] || 0;

        if (isGen10) {
            pokemon.rawStats[sk] = CALC_STAT_CHAMP(baseStat, statPoints, natureBoost);
        } else {
            pokemon.rawStats[sk] = CALC_STAT_ADV(baseStat, ev, iv, pokemon.level, natureBoost);
        }
        pokemon.stats[sk] = pokemon.rawStats[sk]; // will be overwritten after boosts
        pokemon.boosts[sk] = boosts[sk] || 0;
        pokemon.sps[sk] = statPoints;
        pokemon.evs[sk] = ev;
        pokemon.ivs[sk] = iv;
    }

    pokemon.curHP = params.curHP ? Math.floor(params.curHP / 100 * pokemon.maxHP) : pokemon.maxHP;
    if (!pokemon.curHP) pokemon.curHP = pokemon.maxHP;

    return pokemon;
}

// ========== Build Move object from params ==========
function buildMove(moveParams) {
    var moveName;
    if (typeof moveParams === 'string') {
        moveName = moveParams;
        moveParams = {};
    } else {
        moveName = moveParams.name;
    }

    moveName = normalizedMoves[normalize(moveName)] || moveName;

    var defaultDetails = moves[moveName] || { bp: 0, type: 'Normal', category: 'Status' };

    return Object.assign({}, defaultDetails, {
        name: moveName,
        bp: moveParams.bp !== undefined ? moveParams.bp : defaultDetails.bp,
        type: moveParams.type || defaultDetails.type,
        category: moveParams.category || defaultDetails.category,
        isCrit: moveParams.isCrit || false,
        isZ: moveParams.isZ || false,
        isSignatureZ: moveParams.isSignatureZ || false,
        hits: moveParams.hits !== undefined ? moveParams.hits : (defaultDetails.hitRange ? defaultDetails.hitRange.length == 2 ? defaultDetails.hitRange[1] : defaultDetails.hitRange : 1),
        isDouble: moveParams.isDouble || 0,
        combinePledge: moveParams.combinePledge || 0,
        timesAffected: moveParams.timesAffected || 0,
        usedOppMoveIndex: moveParams.usedOppMoveIndex || 0,
        getsStellarBoost: moveParams.getsStellarBoost || false,
        isPlusMove: moveParams.isPlusMove || false,
    });
}

// ========== Build Field object from params ==========
function buildField(fieldParams) {
    fieldParams = fieldParams || {};
    var format = fieldParams.format || 'Doubles';
    var weather = fieldParams.weather ? (normalizedWeather[normalize(fieldParams.weather)] || fieldParams.weather) : '';
    var terrain = fieldParams.terrain ? (normalizedTerrain[normalize(fieldParams.terrain)] || fieldParams.terrain) : '';
    var isGravity = fieldParams.isGravity || false;
    var isNeutralizingGas = fieldParams.isNeutralizingGas || false;
    var isSR = fieldParams.isSR || [false, false];
    var spikes = fieldParams.spikes || [0, 0];
    var isReflect = fieldParams.isReflect || [false, false];
    var isLightScreen = fieldParams.isLightScreen || [false, false];
    var isForesight = fieldParams.isForesight || [false, false];
    var isHelpingHand = fieldParams.isHelpingHand || [false, false];
    var isFriendGuard = fieldParams.isFriendGuard || [false, false];
    var isBattery = fieldParams.isBattery || [false, false];
    var isProtect = fieldParams.isProtect || [false, false];
    var isPowerSpot = fieldParams.isPowerSpot || [false, false];
    var isSteelySpirit = fieldParams.isSteelySpirit || [false, false];
    var isGMaxField = fieldParams.isGMaxField || [false, false];
    var isFlowerGiftSpD = fieldParams.isFlowerGiftSpD || [false, false];
    var isFlowerGiftAtk = fieldParams.isFlowerGiftAtk || [false, false];
    var isTailwind = fieldParams.isTailwind || [false, false];
    var isSaltCure = fieldParams.isSaltCure || [false, false];
    var isAuroraVeil = fieldParams.isAuroraVeil || [false, false];
    var isSwamp = fieldParams.isSwamp || [false, false];
    var isSeaFire = fieldParams.isSeaFire || [false, false];
    var isRedItem = fieldParams.isRedItem || [false, false];
    var isBlueItem = fieldParams.isBlueItem || [false, false];
    var isCharge = fieldParams.isCharge || [false, false];

    return {
        getNeutralGas: function () { return isNeutralizingGas; },
        getTailwind: function (i) { return isTailwind[i]; },
        getWeather: function () { return weather; },
        getTerrain: function () { return terrain; },
        getSwamp: function (i) { return isSwamp[i]; },
        clearWeather: function () { weather = ''; },
        clearTerrain: function () { terrain = ''; },
        getSide: function (i) {
            return new Side(format, terrain, weather, isGravity,
                isSR[i], spikes[i], isReflect[i], isLightScreen[i], isForesight[i],
                isHelpingHand[i], isFriendGuard[i], isBattery[i], isProtect[i],
                isPowerSpot[i], isSteelySpirit[i], isNeutralizingGas, isGMaxField[i],
                isFlowerGiftSpD[i], isFlowerGiftAtk[i], isTailwind[i], isSaltCure[i],
                isAuroraVeil[i], isSwamp[i], isSeaFire[i], isRedItem[i], isBlueItem[i],
                isCharge[i]);
        },
    };
}

// Side constructor (same as ap_calc.js)
function Side(format, terrain, weather, isGravity, isSR, spikes, isReflect, isLightScreen, isForesight, isHelpingHand, isFriendGuard, isBattery, isProtect, isPowerSpot, isSteelySpirit, isNeutralizingGas, isGmaxField, isFlowerGiftSpD, isFlowerGiftAtk, isTailwind, isSaltCure, isAuroraVeil, isSwamp, isSeaFire, isRedItem, isBlueItem, isCharge) {
    this.format = format;
    this.terrain = terrain;
    this.weather = weather;
    this.isGravity = isGravity;
    this.isSR = isSR;
    this.spikes = spikes;
    this.isReflect = isReflect;
    this.isLightScreen = isLightScreen;
    this.isForesight = isForesight;
    this.isHelpingHand = isHelpingHand;
    this.isFriendGuard = isFriendGuard;
    this.isBattery = isBattery;
    this.isProtect = isProtect;
    this.isPowerSpot = isPowerSpot;
    this.isSteelySpirit = isSteelySpirit;
    this.isNeutralizingGas = isNeutralizingGas;
    this.isGMaxField = isGmaxField;
    this.isFlowerGiftSpD = isFlowerGiftSpD;
    this.isFlowerGiftAtk = isFlowerGiftAtk;
    this.isTailwind = isTailwind;
    this.isSaltCure = isSaltCure;
    this.isAuroraVeil = isAuroraVeil;
    this.isSwamp = isSwamp;
    this.isSeaFire = isSeaFire;
    this.isRedItem = isRedItem;
    this.isBlueItem = isBlueItem;
    this.isCharge = isCharge;
}

// ========== Parse KO chance text into structured object ==========
function parseKOChanceText(text) {
    if (!text || text === 'unknown') return { text: text, n: 0, chance: 0 };

    // "guaranteed OHKO" / "guaranteed 2HKO" / "guaranteed 5HKO"
    var guaranteedMatch = text.match(/guaranteed\s+(\d*)O?HKO/);
    if (guaranteedMatch) {
        var n = guaranteedMatch[1] ? parseInt(guaranteedMatch[1]) : 1;
        return { text: text, n: n, chance: 1 };
    }

    // "XX.XX% chance to OHKO" / "XX.XX% chance to 2HKO"
    var chanceMatch = text.match(/([\d.<>]+)%\s+chance\s+to\s+(\d*)O?HKO/);
    if (chanceMatch) {
        var pct = parseFloat(chanceMatch[1].replace(/[<>]/g, ''));
        var n2 = chanceMatch[2] ? parseInt(chanceMatch[2]) : 1;
        return { text: text, n: n2, chance: pct / 100 };
    }

    // "possible XHKO"
    var possibleMatch = text.match(/possible\s+(\d*)O?HKO/);
    if (possibleMatch) {
        var n3 = possibleMatch[1] ? parseInt(possibleMatch[1]) : 1;
        return { text: text, n: n3, chance: 0.5 };
    }

    // No damage / immune / status
    return { text: text, n: 0, chance: 0 };
}

// ========== Main calculation function ==========
function calculateDamage(params) {
    try {
        var g = params.generation || 10; // default: Champions
        setGeneration(g);

        // Set _calcConfig for DOM-replaced values
        _calcConfig = {
            isDoubleBattle: (params.field && params.field.format) !== 'Singles',
            evoBoostL: false, tatsuL: false, evoBoostR: false, tatsuR: false,
            clangL: false, clangR: false, weakL: false, weakR: false,
            isTransformedL: false,
            auraChecked: params.field && params.field.auraChecked || null,
            auraBreakChecked: params.field && params.field.auraBreakChecked || false,
            tabletsOfRuin: params.field && params.field.tabletsOfRuin || false,
            vesselOfRuin: params.field && params.field.vesselOfRuin || false,
            swordOfRuin: params.field && params.field.swordOfRuin || false,
            beadsOfRuin: params.field && params.field.beadsOfRuin || false,
        };

        // Auto-detect aura/ruin abilities → set _calcConfig fields
        var allAbilities = [
            params.attacker && params.attacker.ability,
            params.defender && params.defender.ability
        ];
        for (var ai = 0; ai < allAbilities.length; ai++) {
            var ab = (allAbilities[ai] || '').toLowerCase().replace(/[\s-]/g, '');
            if (ab === 'fairyaura') {
                _calcConfig.auraChecked = _calcConfig.auraChecked || {};
                _calcConfig.auraChecked.fairy = true;
            } else if (ab === 'darkaura') {
                _calcConfig.auraChecked = _calcConfig.auraChecked || {};
                _calcConfig.auraChecked.dark = true;
            } else if (ab === 'aurabreak') {
                _calcConfig.auraBreakChecked = true;
            } else if (ab === 'tabletsofruin') {
                _calcConfig.tabletsOfRuin = true;
            } else if (ab === 'vesselofruin') {
                _calcConfig.vesselOfRuin = true;
            } else if (ab === 'swordofruin') {
                _calcConfig.swordOfRuin = true;
            } else if (ab === 'beadsofruin') {
                _calcConfig.beadsOfRuin = true;
            }
        }

        // Build attacker
        var attacker = buildPokemon(params.attacker);
        var defender = buildPokemon(params.defender);

        // Build moves for each Pokemon (4 slots)
        var attackerMoves = (params.attacker.moves || []).map(function(m) {
            return typeof m === 'string' ? buildMove({ name: m }) : buildMove(m);
        });
        // Fill remaining slots with empty moves
        while (attackerMoves.length < 4) attackerMoves.push(buildMove({ name: '(No Move)', bp: 0, type: 'Normal', category: 'Status' }));
        attacker.moves = attackerMoves;

        var defenderMoves = (params.defender.moves || []).map(function(m) {
            return typeof m === 'string' ? buildMove({ name: m }) : buildMove(m);
        });
        while (defenderMoves.length < 4) defenderMoves.push(buildMove({ name: '(No Move)', bp: 0, type: 'Normal', category: 'Status' }));
        defender.moves = defenderMoves;

        // If single-move mode (legacy format), put the move in slot 0
        if (params.move) {
            var singleMove;
            if (typeof params.move === 'string') {
                singleMove = buildMove({ name: params.move, isCrit: params.isCriticalHit || false });
            } else {
                singleMove = buildMove(Object.assign({}, params.move, { isCrit: params.move.isCrit || params.isCriticalHit || false }));
            }
            attacker.moves[0] = singleMove;
        }

        // Adjust default hits for 2-5 multi-hit moves (match web UI: 3 default, Skill Link→5, Loaded Dice→4)
        for (var hi = 0; hi < attacker.moves.length; hi++) {
            var mv = attacker.moves[hi];
            if (mv.hitRange && mv.hitRange.length === 2 && mv.hitRange[0] === 2 && mv.hitRange[1] === 5 && mv.hits === 5) {
                if (attacker.ability === 'Skill Link') {
                    mv.hits = 5;
                } else if (attacker.item === 'Loaded Dice') {
                    mv.hits = 4;
                } else {
                    mv.hits = 3;
                }
            }
        }

        // Build field
        var field = buildField(params.field);

        // Calculate all moves
        var damageResults;
        var defenderSide = field.getSide(1);
        try {
            damageResults = CALCULATE_ALL_MOVES_SV(attacker, defender, field);
        } catch (calcErr) {
            console.error('[NCP] CALCULATE_ALL_MOVES_SV error:', calcErr.message);
            console.error(calcErr.stack);
            return { success: false, error: 'Calculation error: ' + calcErr.message };
        }

        // Pick the first result from attacker's side (slot 0)
        var attackerResults = damageResults[0];
        var result0 = attackerResults[0];

        if (!result0) {
            return { success: false, error: 'No calculation result' };
        }

        // Find the first successful move result (skip Status moves for legacy output)
        var chosenResult = result0;
        for (var r = 0; r < attackerResults.length; r++) {
            if (attackerResults[r] && attackerResults[r].damage) {
                chosenResult = attackerResults[r];
                break;
            }
        }

        var damage = chosenResult.damage;
        if (!damage || damage.length === 0) {
            return { success: false, error: 'No damage result' };
        }

        var damageRange = getDamageRange(damage);
        var isImmune = damageRange[1] === 0;

        // Build description
        var desc = chosenResult.description || '';
        if (typeof desc === 'object') {
            desc = buildDescription(desc, attacker, defender, chosenResult);
        }

        // KO chance
        var kochanceText = 'unknown';
        if (isImmune) {
            kochanceText = 'No damage (immune)';
        } else {
            try {
                kochanceText = getKOChanceText(damage, attacker.moves[0], defender, defenderSide, attacker.ability === 'Bad Dreams');
            } catch (koErr) {
                kochanceText = 'unknown';
            }
        }
        var kochanceObj = parseKOChanceText(kochanceText);

        // Build attacker/defender stat summaries
        var attackerStats = {};
        var defenderStats = {};
        for (var si = 0; si < STATS.length; si++) {
            var sk = STATS[si];
            attackerStats[sk] = attacker.rawStats[sk];
            defenderStats[sk] = defender.rawStats[sk];
        }

        // If single-move mode, return single result
        if (params.move) {
            return {
                success: true,
                damage: damage,
                damageRange: damageRange,
                description: isImmune ? 'Immune' : desc,
                kochance: kochanceObj,
                attacker: {
                    name: attacker.name,
                    stats: attackerStats,
                },
                defender: {
                    name: defender.name,
                    stats: defenderStats,
                    hp: defender.maxHP,
                },
            };
        }

        // Multi-move mode: return all 4 results
        var allResults = [];
        for (var mi = 0; mi < 4; mi++) {
            var mr = attackerResults[mi];
            if (mr && mr.damage && mr.damage.length > 0) {
                var mDmg = mr.damage;
                var mKo = 'unknown';
                try {
                    mKo = getKOChanceText(mDmg, attacker.moves[mi], defender, defenderSide, attacker.ability === 'Bad Dreams');
                } catch (e) {}
                allResults.push({
                    moveName: attacker.moves[mi].name,
                    damage: mDmg,
                    damageRange: getDamageRange(mDmg),
                    description: buildDescription(mr.description, attacker, defender, mr),
                    kochance: parseKOChanceText(mKo),
                });
            }
        }

        return {
            success: true,
            results: allResults,
            attacker: {
                name: attacker.name,
                stats: attackerStats,
            },
            defender: {
                name: defender.name,
                stats: defenderStats,
                hp: defender.maxHP,
            },
        };

    } catch (error) {
        return {
            success: false,
            error: error.message,
            stack: error.stack,
        };
    }
}

// ========== Build description text ==========
function buildDescription(desc, attacker, defender, result) {
    if (typeof desc === 'string') return desc;
    // desc is an object like { attackerName, moveName, defenderName, ... }
    var parts = [];
    if (desc.attackerLevel) parts.push('Lvl ' + desc.attackerLevel);
    if (attacker.boosts && attacker.boosts[SA] > 0) {
        parts.push('+' + attacker.boosts[SA]);
    }
    if (desc.attackerName) parts.push(desc.attackerName);
    if (desc.attackerItem) parts.push('@ ' + desc.attackerItem);
    parts.push(desc.moveName || '???');
    parts.push('vs.');
    if (desc.defenderLevel) parts.push('Lvl ' + desc.defenderLevel);
    if (desc.defenderName) parts.push(desc.defenderName);
    if (result && result.damage) {
        var dr = [result.damage[0], result.damage[result.damage.length - 1]];
        var pct = defender.maxHP > 0 ? Math.round(dr[1] / defender.maxHP * 1000) / 10 : 0;
        parts.push('-- ' + dr[0] + '-' + dr[1] + ' (' + pct + '%)');
    }
    return parts.join(' ');
}

// ========== CLI ==========
if (require.main === module) {
    var input = process.argv[2];

    if (input === '--persistent') {
        // 持久模式：从 stdin 逐行读取 JSON，计算后输出结果
        var readline = require('readline');
        var rl = readline.createInterface({ input: process.stdin, terminal: false });
        console.log(JSON.stringify({ ready: true }));
        rl.on('line', function(line) {
            try {
                var params = JSON.parse(line);
                var result = calculateDamage(params);
                console.log(JSON.stringify(result));
            } catch (error) {
                console.log(JSON.stringify({ success: false, error: error.message }));
            }
        });
        rl.on('close', function() { process.exit(0); });
    } else {
        if (!input) {
            console.error('Usage: node calculator.js \'<JSON_PARAMS>\'');
            process.exit(1);
        }
        try {
            var params = JSON.parse(input);
            var result = calculateDamage(params);
            console.log(JSON.stringify(result, null, 2));
        } catch (error) {
            console.error(JSON.stringify({ success: false, error: error.message }));
            process.exit(1);
        }
    }
}

module.exports = { calculateDamage };
