var AT = "at", DF = "df", SA = "sa", SD = "sd", SP = "sp", SL = "sl";
var STATS_RBY = [AT, DF, SL, SP];
var STATS_GSC = [AT, DF, SA, SD, SP];

// Gen 1 HP (no EVs/IVs, use DVs)
function CALC_HP_RBY(base, dv, level) {
    return Math.floor(((base + dv) * 2 + 63) * level / 100) + level + 10;
}

// Gen 1 stat
function CALC_STAT_RBY(base, dv, level) {
    return Math.floor(((base + dv) * 2 + 63) * level / 100) + 5;
}

// Gen 3-9 HP
function CALC_HP_ADV(base, evs, ivs, level, isDynamax) {
    if (base === 1) return 1;
    var total = Math.floor((base * 2 + ivs + Math.floor(evs / 4)) * level / 100) + level + 10;
    if (isDynamax) total *= 2;
    return total;
}

// Gen 3-9 stat
function CALC_STAT_ADV(base, evs, ivs, level, nature) {
    return Math.floor((Math.floor((base * 2 + ivs + Math.floor(evs / 4)) * level / 100) + 5) * nature);
}

// Gen 7 Let's Go HP
function CALC_HP_LGPE(base, ivs, level, avs) {
    if (base === 1) return 1;
    return Math.floor((base * 2 + ivs) * level / 100) + level + 10 + avs;
}

// Gen 7 Let's Go stat
function CALC_STAT_LGPE(base, ivs, level, nature, friendshipMod, avs) {
    var friendship = 1 + (Math.floor(10 * friendshipMod / 255) / 100);
    return Math.floor((Math.floor((base * 2 + ivs) * level / 100) + 5) * nature * friendship) + avs;
}

// Champions HP (level 50, IV 31 hardcoded)
function CALC_HP_CHAMP(base, statPoints, isDynamax) {
    if (base === 1) return 1;
    var total = Math.floor((base * 2 + 31) * 50 / 100) + 60 + statPoints;
    if (isDynamax) total *= 2;
    return total;
}

// Champions stat (level 50, IV 31 hardcoded)
function CALC_STAT_CHAMP(base, statPoints, nature) {
    return Math.floor(((Math.floor((base * 2 + 31) * 50 / 100) + 5) + statPoints) * nature);
}
