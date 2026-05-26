/**
 * 导出 NCP 计算器所有 Gen 10 (Champions) 的 canonical keys
 * 供 Python 测试脚本交叉验证 normalize 匹配
 */
var path = require('path');
var fs = require('fs');
var vm = require('vm');
var caleDir = __dirname;

global.$ = {
    extend: function deepExtend(deep, target) {
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
};

function loadGlobal(filename) {
    var code = fs.readFileSync(path.join(caleDir, filename), 'utf-8');
    vm.runInThisContext(code, { filename: filename });
}

loadGlobal('stat_data.js');
loadGlobal('nature_data.js');
loadGlobal('type_data.js');
loadGlobal('item_data.js');
loadGlobal('ability_data.js');
loadGlobal('pokedex.js');
loadGlobal('move_data.js');
loadGlobal('cooldown_za.js');

function normalize(s) { return s.replace(/[^a-zA-Z]/g, '').toLowerCase(); }

// Gen 10 Champions data
var pokemonKeys = Object.keys(typeof POKEDEX_CHAMPIONS !== 'undefined' ? POKEDEX_CHAMPIONS : {});
var moveKeys = Object.keys(typeof MOVES_ZA_NATDEX !== 'undefined' ? MOVES_ZA_NATDEX : {});
var natureKeys = Object.keys(typeof NATURES !== 'undefined' ? NATURES : {});
var abilityList = typeof ABILITIES_CHAMPIONS !== 'undefined' ? ABILITIES_CHAMPIONS : [];
var itemList = typeof ITEMS_CHAMPIONS !== 'undefined' ? ITEMS_CHAMPIONS : [];

var result = {
    pokemon: {},
    moves: {},
    natures: {},
    abilities: {},
    items: {},
};

pokemonKeys.forEach(function(k) { result.pokemon[normalize(k)] = k; });
moveKeys.forEach(function(k) { result.moves[normalize(k)] = k; });
natureKeys.forEach(function(k) { result.natures[normalize(k)] = k; });
abilityList.forEach(function(k) { result.abilities[normalize(k)] = k; });
itemList.forEach(function(k) { result.items[normalize(k)] = k; });

// hardcoded weather/terrain/status (same as calculator.js buildNormalizeMaps)
result.weather = {};
['Sun','Rain','Sand','Snow','Harsh Sun','Heavy Rain','Strong Winds'].forEach(function(w) {
    result.weather[normalize(w)] = w;
});
result.terrain = {};
['Electric','Grassy','Misty','Psychic'].forEach(function(t) {
    result.terrain[normalize(t)] = t;
});
result.status = {};
['Burned','Paralyzed','Asleep','Poisoned','Badly Poisoned','Drowsy','Frozen'].forEach(function(s) {
    result.status[normalize(s)] = s;
});

console.log(JSON.stringify(result));
