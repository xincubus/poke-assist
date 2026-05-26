/**
 * URL Parameter Loader for VGC Damage Calculator
 *
 * 从 URL query params 读取参数，自动填入计算器表单并触发计算。
 * 加载顺序：必须在 ap_calc.js 之后，确保 select2、calcHP 等已初始化。
 *
 * 支持的参数：
 *   gen        - 世代 (1-9)
 *   p1 / p2    - 攻守方宝可梦英文名 (如 Koraidon)
 *   move1      - 攻击方招式 (如 Flare Blitz)
 *   item1/item2      - 道具
 *   ability1/ability2 - 特性
 *   nature1/nature2   - 性格
 *   evs1/evs2  - 努力值 (hp,atk,def,spa,spd,spe 逗号分隔)
 *   tera1/tera2 - 太晶属性
 *   weather    - 天气 (Sun/Rain/Sand/Snow/Hail/Harsh Sun/Heavy Rain/Strong Winds)
 *   terrain    - 场地 (Electric/Grassy/Misty/Psychic)
 *   status1/status2 - 状态
 *   mode       - 单打/双打 (Singles/Doubles)，默认 Singles
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
     * 通过 select2 设置宝可梦（触发 .set-selector change handler）
     * 使用 "PokemonName (空白配置)" 格式，确保选中宝可梦但不加载预设配置
     */
    function toPokedexKey(name) {
        // URL 参数用连字符（flutter-mane），pokedex key 用空格（Flutter Mane）
        // 先将连字符转空格，再做 Title Case
        return name.replace(/-/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    }

    function setPokemon(panelId, name) {
        if (!name) return;
        name = decodeParam(name);
        // 将名字转成 Title Case 匹配 pokedex key（如 hitmonchan → Hitmonchan, flutter-mane → Flutter Mane）
        name = toPokedexKey(name);
        var blankId = name + ' (空白配置)';
        var displayText = translate_pokemon(name) + ' (空白配置)';
        var $sel = $(panelId + ' .set-selector');
        // select2 3.x query 模式：用 data 设置值
        $sel.select2('data', { id: blankId, text: displayText });
        $sel.trigger('change');
        // 强制更新 select2 显示框的文本
        $sel.closest('.poke-info').find('.select2-chosen').text(displayText);
    }

    /**
     * 用 select2 设置下拉框的值（ability / item / move-selector）
     */
    function setSelect2Val($el, value) {
        if (!value) return;
        value = decodeParam(value);
        // 检查 option 是否存在
        if ($el.find('option[value="' + value + '"]').length) {
            $el.select2('val', value);
        } else {
            // 尝试去掉连字符格式匹配 Title Case
            var titleCase = value.replace(/-/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
            if ($el.find('option[value="' + titleCase + '"]').length) {
                $el.select2('val', titleCase);
            } else {
                $el.val(value);
            }
        }
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

        // 特性 (select2)
        var ability = params.get('ability' + suffix);
        if (ability) {
            setSelect2Val($panel.find('select.ability'), ability);
        }

        // 道具 (select2)
        var item = params.get('item' + suffix);
        if (item) {
            setSelect2Val($panel.find('select.item'), item);
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

        // 招式: p1 用 move1-move4, p2 用 move2_1-move2_4
        var movePrefix = (suffix === '1') ? 'move' : 'move2_';
        var moveSlots = ['.move1', '.move2', '.move3', '.move4'];
        for (var m = 0; m < 4; m++) {
            var moveVal = params.get(movePrefix + (m + 1));
            if (moveVal) {
                var $moveSel = $panel.find(moveSlots[m] + ' select.move-selector');
                setSelect2Val($moveSel, moveVal);
                $moveSel.trigger('change');
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
            setPokemon('#p1', params.get('p1'));
            setPokemon('#p2', params.get('p2'));

            // Step 3: 等待宝可梦 change handler 填充完下拉选项后，覆盖自定义值
            setTimeout(function () {
                fillSide('#p1', '1');
                fillSide('#p2', '2');

                // Step 4: 场地条件放最后（覆盖特性自动设置的天气）
                setFieldConditions();

                // Step 5: 触发重新计算
                $('.calc-trigger').first().trigger('change');
            }, 100);
        }, 100);
    });
})();
