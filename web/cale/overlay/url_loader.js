/**
 * URL Parameter Loader for NCP VGC Damage Calculator
 *
 * 从 URL query params 读取参数，自动填入计算器表单并触发计算。
 * 加载顺序：必须在 ap_calc.js 之后，确保 select2、calcHP 等已初始化。
 *
 * 支持的参数：
 *   gen        - 世代 (1-10，默认 Champions)
 *   p1 / p2    - 攻守方宝可梦英文名 (如 Koraidon)
 *   move1-move4      - 攻击方招式1-4
 *   move2_1-move2_4  - 防守方招式1-4
 *   item1/item2      - 道具
 *   ability1/ability2 - 特性
 *   nature1/nature2   - 性格
 *   evs1/evs2  - 努力值 (hp,atk,def,spa,spd,spe 逗号分隔)
 *   sps1/sps2  - 能力点 Gen 10 (hp,atk,def,spa,spd,spe 逗号分隔, 0-32)
 *   ivs1/ivs2  - 个体值 (同上)
 *   tera1/tera2 - 太晶属性
 *   weather    - 天气 (Sun/Rain/Sand/Snow/Hail/Harsh Sun/Heavy Rain/Strong Winds)
 *   terrain    - 场地 (Electric/Grassy/Misty/Psychic)
 *   status1/status2 - 状态
 *   boosts1/boosts2 - 能力等级变化 (atk,def,spa,spd,spe 逗号分隔, -6到+6)
 *   reflect1/reflect2 - 反射壁 (true)
 *   lightscreen1/lightscreen2 - 光墙 (true)
 *   auroraveil1/auroraveil2 - 极光幕 (true)
 *   mode       - 单打/双打 (Singles/Doubles)，默认 Singles
 *   level1/level2 - 等级
 *
 * 用法示例：
 *   index_zh.html?gen=9&p1=Koraidon&p2=Miraidon&move1=Flare+Blitz&evs1=252,252,0,0,4,0
 */
(function () {
    'use strict';

    var params = new URLSearchParams(window.location.search);
    // 无参数则不执行
    if (!params.has('p1') && !params.has('p2') && !params.has('gen')) return;

    // EV 字段 CSS class 与参数顺序的映射
    var STAT_CLASSES = ['hp', 'at', 'df', 'sa', 'sd', 'sp'];

    /**
     * 解码 URL 参数值（+ → 空格）
     */
    function decodeParam(val) {
        if (!val) return '';
        return decodeURIComponent(val.replace(/\+/g, ' '));
    }

    /**
     * 获取中文翻译（如果 translate.js 已加载），否则返回原文
     */
    function tryTranslatePokemon(name) {
        if (typeof translate_pokemon === 'function') {
            return translate_pokemon(name);
        }
        return name;
    }

    /**
     * 从 alternate forme 名反查 base Pokemon 名。
     * 例如 "Mega Charizard Y" → "Charizard", "Primal Kyogre" → "Kyogre"
     */
    function findBasePokemon(formeName) {
        if (typeof pokedex === 'undefined') return null;
        for (var key in pokedex) {
            var entry = pokedex[key];
            if (entry.formes && entry.formes.indexOf(formeName) !== -1) {
                return key;
            }
        }
        return null;
    }

    /**
     * 大小写 & 连字符/空格 不敏感地查找 pokedex key。
     * "sneasler" → "Sneasler"
     * "iron-valiant" → "Iron Valiant"
     * "ho-oh" → "Ho-Oh"
     */
    function findPokedexKey(name) {
        if (typeof pokedex === 'undefined') return name;
        // 精确匹配优先
        if (pokedex[name]) return name;
        // 大小写不敏感查找
        var nameLower = name.toLowerCase();
        for (var key in pokedex) {
            if (key.toLowerCase() === nameLower) {
                return key;
            }
        }
        // 连字符 ↔ 空格互换后再试（iron-valiant ↔ Iron Valiant）
        var nameNorm = nameLower.replace(/[-\s]/g, ' ');
        for (var key in pokedex) {
            if (key.toLowerCase().replace(/[-\s]/g, ' ') === nameNorm) {
                return key;
            }
        }
        return name; // 找不到则原样返回
    }

    /**
     * 大小写不敏感地在 <select> 的 option 中查找 value。
     * "Light Of Ruin" → "Light of Ruin"
     */
    function findOptionValue($select, name) {
        if (!name) return name;
        // 精确匹配优先
        if ($select.find('option[value="' + name + '"]').length) return name;
        // 大小写不敏感
        var nameLower = name.toLowerCase();
        var match = null;
        $select.find('option').each(function () {
            if (this.value.toLowerCase() === nameLower) {
                match = this.value;
                return false;
            }
        });
        return match || name;
    }

    /**
     * 通过 select2 设置宝可梦（触发 .set-selector change handler）
     * 注意：id 必须用英文 "Blank Set"，因为 ap_calc.js 的 showFormes/getSetOptions
     * 内部检查的是 'Blank Set'，不是 '空白配置'。
     * 显示文本可以用中文。
     *
     * 如果 name 是 alternate forme（Mega/Primal 等），先设 base Pokemon，
     * 等 showFormes() 塌好 forme 下拉后再选具体形态，模拟手动选择流程。
     *
     * 返回需要等待 forme 切换的延迟（ms），0 表示无需等待。
     */
    function setPokemon(panelId, name) {
        if (!name) return 0;
        name = decodeParam(name);
        // 大小写不敏感匹配 pokedex key
        name = findPokedexKey(name);

        var formeToSelect = null;
        var baseName = name;

        // 检查是否是 alternate forme（需要先选 base 再切 forme）
        if (typeof pokedex !== 'undefined' && pokedex[name] && pokedex[name].isAlternateForme) {
            var found = findBasePokemon(name);
            if (found) {
                formeToSelect = name;
                baseName = found;
            }
        }

        var blankId = baseName + ' (Blank Set)';
        var displayText = tryTranslatePokemon(baseName) + ' (空白配置)';
        var $sel = $(panelId + ' .set-selector');
        // select2 3.x query 模式：用 data 设置值
        $sel.select2('data', { id: blankId, text: displayText });
        $sel.trigger('change');
        // 强制更新 select2 显示框的文本
        $sel.closest('.poke-info').find('.select2-chosen').text(displayText);

        // 如果需要选 forme，等 showFormes() 完成 DOM 更新后再切
        if (formeToSelect) {
            var FORME_DELAY = 150;
            var $formeSelect = $(panelId + ' select.forme');
            setTimeout(function () {
                $formeSelect.val(formeToSelect).trigger('change');
                // 更新显示文本为 forme 名（但 selector 内部 id 保持 baseName）
                var formeDisplay = tryTranslatePokemon(formeToSelect) + ' (空白配置)';
                $sel.select2('data', { id: blankId, text: formeDisplay });
                $sel.closest('.poke-info').find('.select2-chosen').text(formeDisplay);
            }, FORME_DELAY);
            return FORME_DELAY;
        }
        return 0;
    }

    /**
     * 用 select2 设置下拉框的值（ability / item / move-selector）
     */
    function setSelect2Val($el, value) {
        if (!value) return;
        value = decodeParam(value);
        // 先设置底层 select 的值，再触发 select2 刷新
        $el.val(value);
        try { $el.select2('val', value); } catch(e) {}
    }

    /**
     * 设置一侧的 EVs/IVs/性格/特性/道具/招式/太晶/状态
     */
    function fillSide(panelId, suffix) {
        var $panel = $(panelId);

        // EVs: "hp,atk,def,spa,spd,spe"
        var evStr = params.get('evs' + suffix);
        if (evStr) {
            var evs = evStr.split(',');
            for (var i = 0; i < STAT_CLASSES.length && i < evs.length; i++) {
                $panel.find('.' + STAT_CLASSES[i] + ' .evs').val(parseInt(evs[i]) || 0);
            }
        }

        // SPs (Gen 10 Stat Points): "hp,atk,def,spa,spd,spe"
        var spsStr = params.get('sps' + suffix);
        if (spsStr) {
            var sps = spsStr.split(',');
            for (var i = 0; i < STAT_CLASSES.length && i < sps.length; i++) {
                $panel.find('.' + STAT_CLASSES[i] + ' .sps').val(parseInt(sps[i]) || 0);
            }
        }

        // IVs (可选)
        var ivStr = params.get('ivs' + suffix);
        if (ivStr) {
            var ivs = ivStr.split(',');
            for (var i = 0; i < STAT_CLASSES.length && i < ivs.length; i++) {
                $panel.find('.' + STAT_CLASSES[i] + ' .ivs').val(parseInt(ivs[i]));
            }
        }

        // 性格
        var nature = params.get('nature' + suffix);
        if (nature) {
            $panel.find('select.nature').val(decodeParam(nature));
        }

        // 特性 (select2, 大小写不敏感)
        var ability = params.get('ability' + suffix);
        if (ability) {
            var $abilitySel = $panel.find('select.ability');
            var resolvedAbility = findOptionValue($abilitySel, decodeParam(ability));
            setSelect2Val($abilitySel, resolvedAbility);
        }

        // 道具 (select2, 大小写不敏感)
        var item = params.get('item' + suffix);
        if (item) {
            var $itemSel = $panel.find('select.item');
            var resolvedItem = findOptionValue($itemSel, decodeParam(item));
            setSelect2Val($itemSel, resolvedItem);
        }

        // 等级
        var level = params.get('level' + suffix);
        if (level) {
            $panel.find('.level').val(parseInt(level));
        }

        // 太晶属性 (Gen 9)
        var tera = params.get('tera' + suffix);
        if (tera) {
            $panel.find('.tera-type').val(decodeParam(tera));
            var teraCheckId = suffix === '1' ? '#teraL' : '#teraR';
            $(teraCheckId).prop('checked', true).trigger('change');
        }

        // 状态
        var status = params.get('status' + suffix);
        if (status) {
            $panel.find('.status').val(decodeParam(status)).trigger('change');
        }

        // Boosts: "atk,def,spa,spd,spe" (逗号分隔, 对应 at/df/sa/sd/sp)
        var boostStr = params.get('boosts' + suffix);
        if (boostStr) {
            var boostVals = boostStr.split(',');
            var boostClasses = ['at', 'df', 'sa', 'sd', 'sp'];
            for (var b = 0; b < boostClasses.length && b < boostVals.length; b++) {
                var bv = parseInt(boostVals[b]) || 0;
                if (bv !== 0) {
                    $panel.find('.' + boostClasses[b] + ' .boost').val(String(bv));
                }
            }
        }

        // 壁: reflect/lightscreen/auroraveil (L=攻击方, R=防守方)
        var side = (suffix === '1') ? 'L' : 'R';
        if (params.get('reflect' + suffix) === 'true') {
            $('#reflect' + side).prop('checked', true);
        }
        if (params.get('lightscreen' + suffix) === 'true') {
            $('#lightScreen' + side).prop('checked', true);
        }
        if (params.get('auroraveil' + suffix) === 'true') {
            $('#auroraVeil' + side).prop('checked', true);
        }

        // 招式: p1 用 move1-move4, p2 用 move2_1-move2_4
        var movePrefix = (suffix === '1') ? 'move' : 'move2_';
        var moveSlots = ['.move1', '.move2', '.move3', '.move4'];
        for (var m = 0; m < 4; m++) {
            var moveVal = params.get(movePrefix + (m + 1));
            if (moveVal) {
                var $moveSel = $panel.find(moveSlots[m] + ' select.move-selector');
                if (!$moveSel.length) {
                    console.warn('[url_loader] move selector not found:', moveSlots[m] + ' select.move-selector', 'in panel', panelId);
                } else {
                    var resolved = findOptionValue($moveSel, decodeParam(moveVal));
                    if (!$moveSel.find('option[value="' + resolved + '"]').length) {
                        console.warn('[url_loader] move option not found:', decodeParam(moveVal), 'options count:', $moveSel.find('option').length);
                    } else {
                        $moveSel.val(resolved);
                        try { $moveSel.select2('val', resolved); } catch(e) {}
                        $moveSel.trigger('change');
                    }
                }
            }
        }

        // 重算能力值
        calcHP($panel);
        calcStats($panel);
        calcEvTotal($panel);
    }

    /**
     * 设置场地条件（天气、地形）
     */
    function setFieldConditions() {
        // 单打/双打：默认单打，支持 mode=Singles/Doubles
        var mode = decodeParam(params.get('mode')) || 'Singles';
        if (mode === 'Doubles') {
            $('#doubles').prop('checked', true);
            $('#douswitch').prop('checked', true);
        } else {
            $('#singles').prop('checked', true);
            $('#douswitch').prop('checked', false);
        }

        var weather = params.get('weather');
        if (weather) {
            weather = decodeParam(weather);
            $("input:radio[name='weather']").each(function () {
                if ($(this).val() === weather) {
                    $(this).prop('checked', true).trigger('change');
                }
            });
        }

        var terrain = params.get('terrain');
        if (terrain) {
            terrain = decodeParam(terrain);
            $("input:radio[name='terrain']").each(function () {
                if ($(this).val() === terrain) {
                    $(this).prop('checked', true).trigger('change');
                }
            });
        }
    }

    /**
     * 主入口：在 document ready 之后执行（ap_calc.js 的 ready 先跑完）
     */
    $(document).ready(function () {
        // Step 1: 设置世代（会重建所有下拉列表）
        var genVal = params.get('gen') || '9';
        var $genRadio = $('#gen' + genVal);
        if ($genRadio.length) {
            $genRadio.prop('checked', true).trigger('change');
        }

        // Step 2: 等待世代切换完成（下拉列表重建），然后设置宝可梦
        setTimeout(function () {
            var formeDelay1 = setPokemon('#p1', params.get('p1'));
            var formeDelay2 = setPokemon('#p2', params.get('p2'));
            // 如果有 forme 需要切换，等 forme change 完成后再填值
            var extraDelay = Math.max(formeDelay1, formeDelay2);

            // Step 3: 等待宝可梦 change handler + forme 切换完成后，覆盖自定义值
            setTimeout(function () {
                fillSide('#p1', '1');
                fillSide('#p2', '2');

                // Step 4: 场地条件放最后（覆盖特性自动设置的天气）
                setFieldConditions();

                // Step 5: 触发重新计算
                $('.calc-trigger').first().trigger('change');
            }, 200 + extraDelay);
        }, 100);
    });
})();
