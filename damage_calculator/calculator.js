/**
 * 宝可梦伤害计算器封装
 * 可以通过命令行或作为模块使用
 */

const { calculate, Pokemon, Move, Field, Generations } = require('@smogon/calc');

/**
 * 主计算函数
 */
function calculateDamage(params) {
  try {
    const gen = Generations.get(params.generation || 9);

    // 创建攻击方
    const attacker = new Pokemon(gen, params.attacker.name, {
      level: params.attacker.level || 50,
      evs: params.attacker.evs || {},
      ivs: params.attacker.ivs || {},
      nature: params.attacker.nature || 'Serious',
      ability: params.attacker.ability,
      item: params.attacker.item,
      boosts: params.attacker.boosts || {},
      status: params.attacker.status,  // 状态: 'brn', 'par', 'psn', 'tox', 'slp', 'frz'
      curHP: params.attacker.curHP,  // 当前HP百分比（0-100）
      teraType: params.attacker.teraType,  // 太晶属性
    });

    // 创建防御方
    const defender = new Pokemon(gen, params.defender.name, {
      level: params.defender.level || 50,
      evs: params.defender.evs || {},
      ivs: params.defender.ivs || {},
      nature: params.defender.nature || 'Serious',
      ability: params.defender.ability,
      item: params.defender.item,
      boosts: params.defender.boosts || {},
      status: params.defender.status,  // 状态: 'brn', 'par', 'psn', 'tox', 'slp', 'frz'
      curHP: params.defender.curHP,  // 当前HP百分比（0-100）
      teraType: params.defender.teraType,  // 太晶属性
    });

    // 创建招式
    const move = new Move(gen, params.move, {
      isCrit: params.isCriticalHit || false,
    });

    // 创建场地
    const field = new Field(params.field || {});

    // 计算
    const result = calculate(gen, attacker, defender, move, field);

    const damageRange = result.range();
    const isImmune = damageRange[damageRange.length - 1] === 0;
    return {
      success: true,
      damage: result.damage,
      damageRange: damageRange,
      description: isImmune ? 'Immune' : result.fullDesc(),
      kochance: isImmune ? { text: 'Immune (0 damage)', chance: 0 } : result.kochance(),
      attacker: {
        name: attacker.name,
        stats: attacker.stats,
      },
      defender: {
        name: defender.name,
        stats: defender.stats,
        hp: defender.originalCurHP,
      },
    };
  } catch (error) {
    return {
      success: false,
      error: error.message,
    };
  }
}

// 命令行接口
if (require.main === module) {
  const input = process.argv[2];
  if (!input) {
    console.error('Usage: node calculator.js \'<JSON_PARAMS>\'');
    process.exit(1);
  }

  try {
    const params = JSON.parse(input);
    const result = calculateDamage(params);
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(JSON.stringify({ success: false, error: error.message }));
    process.exit(1);
  }
}

module.exports = { calculateDamage };
