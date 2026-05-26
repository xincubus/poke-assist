/**
 * translate_ui.js — 英文 NCP 伤害计算器的运行时中文翻译覆盖层
 *
 * 加载顺序：在所有原版 JS 之后（sidebars.js 之后），与 url_loader.js 一起最后加载。
 *
 * 工作原理：
 *   1. Monkey-patch getSelectOptions — 生成翻译后的 option 文本（但 value 保持英文）
 *   2. Override select2 的 formatResult — 使下拉显示中文名
 *   3. Override select2 的 matcher — 支持中文/英文搜索
 *   4. Monkey-patch calculate() — 拦截结果输出翻译成中文
 *   5. 替换静态 UI 标签
 *   6. MutationObserver — 处理动态 DOM 变化
 */
(function () {
    'use strict';

    // ========== 1. 翻译函数包装 ==========

    function tp(name) { return typeof translate_pokemon === 'function' ? translate_pokemon(name) : name; }
    function tm(name) { return typeof translate_move === 'function' ? translate_move(name) : name; }
    function ta(name) { return typeof translate_ability === 'function' ? translate_ability(name) : name; }
    function ti(name) { return typeof translate_item === 'function' ? translate_item(name) : name; }
    function tty(name) { return typeof translate_type === 'function' ? translate_type(name) : name; }
    function tn(name) { return typeof translate_nature === 'function' ? translate_nature(name) : name; }
    function ts(name) { return typeof translate_set === 'function' ? translate_set(name) : name; }
    function tk(text) { return typeof translate_ko_text === 'function' ? translate_ko_text(text) : text; }

    // ========== 2. 翻译分发器 ==========

    /**
     * 根据 select 的 CSS class 翻译 option 的显示文本
     */
    function translateOptionText($sel, val) {
        if ($sel.hasClass('ability')) return ta(val);
        if ($sel.hasClass('item')) return ti(val);
        if ($sel.hasClass('move-selector')) return tm(val);
        if ($sel.hasClass('type1') || $sel.hasClass('type2') ||
            $sel.hasClass('tera-type') || $sel.hasClass('move-type') ||
            $sel.hasClass('type')) return tty(val);
        return val;
    }

    // ========== 3. UI 静态文本映射 ==========

    var UI_LABELS = {
        'VGC 2026: Champions Damage Calculator': 'VGC 2026：宝可梦冠军伤害计算器',
        'Pokémon Damage Calculator': '宝可梦伤害计算器',
        'RBY': '红绿蓝黄', 'GSC': '金银水晶', 'ADV': '宝石',
        'DPP': '珍钻白金', 'B/W': '黑/白', 'ORAS': 'XY/宝石复刻',
        'USUM': '(究极)日/月', 'SWSH': '剑/盾', 'S/V': '朱/紫',
        'CHAMP': '冠军',
        'Dark theme': '夜晚模式', 'Night theme': '夜晚模式', 'Day theme': '日间模式',
        'National Dex': '全国图鉴',
        'Singles': '单打', 'Doubles': '双打',
        'Sun': '晴天', 'Rain': '雨天', 'Sand': '沙暴', 'Hail': '冰雹', 'Snow': '雪天',
        'Harsh Sun': '大日照', 'Heavy Rain': '大雨', 'Strong Winds': '乱流',
        'None': '无',
        'Electric': '电气', 'Grassy': '青草', 'Misty': '薄雾', 'Psychic': '精神',
        'Physical': '物理', 'Special': '特殊', 'Status': '变化',
        'Helping Hand': '帮助', 'Flower Gift': '花之礼',
        'Aurora Veil': '极光幕', 'Reflect': '反射壁', 'Light Screen': '光之壁',
        'Lucky Chant': '幸运咒语', 'Stealth Rock': '隐形岩', 'Spikes': '撒菱',
        'Tailwind': '顺风', 'Protect': '守住', 'Gravity': '重力',
        'Aura Break': '气场破坏', 'Fairy Aura': '妖精气场', 'Dark Aura': '暗黑气场',
        'Tablets of Ruin': '灾祸之简', 'Vessel of Ruin': '灾祸之鼎',
        'Sword of Ruin': '灾祸之剑', 'Beads of Ruin': '灾祸之玉',
        'Neutralizing Gas': '化学变化气体',
        'Sea of Fire': '烈火', 'Friend Guard': '友情防守',
        'Battery': '蓄电', 'Power Spot': '能量点', 'Steely Spirit': '钢之心',
    };

    // ========== 4. Monkey-patch getSelectOptions ==========
    // 必须在脚本加载时立即 patch（不在 $(document).ready 中），
    // 因为 ap_calc.js 的 $(document).ready 先于此脚本的 ready 执行，
    // 而它会调用 getSelectOptions 生成 option HTML。

    (function patchGetSelectOptionsImmediate() {
        if (typeof getSelectOptions !== 'function') return;

        var _origGetSelectOptions = getSelectOptions;

        // 合并所有翻译字典为一个查找函数，避免串行 6 次函数调用
        var _allDicts = [];
        if (typeof MOVENAMES === 'object') _allDicts.push(MOVENAMES);
        if (typeof ABILITYNAMES === 'object') _allDicts.push(ABILITYNAMES);
        if (typeof ITEMNAMES === 'object') _allDicts.push(ITEMNAMES);
        if (typeof POKENAMES === 'object') _allDicts.push(POKENAMES);
        if (typeof TYPENAMES === 'object') _allDicts.push(TYPENAMES);
        if (typeof NATURENAMES === 'object') _allDicts.push(NATURENAMES);

        // 翻译缓存：避免重复查找
        var _translateCache = {};

        function quickTranslate(val) {
            if (_translateCache.hasOwnProperty(val)) return _translateCache[val];
            for (var i = 0; i < _allDicts.length; i++) {
                var t = _allDicts[i][val];
                if (t) {
                    _translateCache[val] = t;
                    return t;
                }
            }
            _translateCache[val] = val;
            return val;
        }

        // 无条件翻译 option text：将 value 的英文名翻译为中文显示
        // value 保持不变，只改显示文本
        window.getSelectOptions = function (arr, sort, defaultIdx) {
            var result = _origGetSelectOptions(arr, sort, defaultIdx);
            result = result.replace(/<option value="([^"]+)">([^<]*)<\/option>/g, function (match, val, text) {
                var translated = quickTranslate(val);
                return '<option value="' + val + '">' + translated + '</option>';
            });
            return result;
        };
    })();

    // ========== 5. Override select2 的 formatResult/formatSelection ==========

    function patchSelect2Instances() {
        // set-selector 的 select2（宝可梦下拉）
        // 宝可梦选择器不重新初始化（使用自定义 query），只 patch formatResult
        ['#p1', '#p2'].forEach(function (panelId) {
            var $sel = $(panelId + ' .set-selector');
            try {
                var s2 = $sel.data('select2');
                if (!s2 || !s2.opts) return;

                s2.opts.formatResult = function (object) {
                    if (object.set === 'Blank Set') {
                        return '&nbsp;&nbsp;&nbsp;空白配置';
                    }
                    if (object.set) {
                        return '&nbsp;&nbsp;&nbsp;' + ts(object.set);
                    }
                    var name = object.text;
                    if (name.indexOf('(Blank Set)') !== -1) {
                        name = tp(name.replace(' (Blank Set)', '')) + ' (空白配置)';
                    } else if (name.indexOf('(') !== -1) {
                        var m = name.match(/^(.+?)\s*\((.+)\)$/);
                        if (m) name = tp(m[1]) + ' (' + ts(m[2]) + ')';
                    } else {
                        name = tp(name);
                    }
                    return '<b>' + name + '</b>';
                };
            } catch (e) { }
        });

        // move-selector, ability, item 不再需要 patch formatResult/formatSelection
        // 因为 patchSearch() 会重新初始化这些 Select2，option text 已经是中文
    }

    // ========== 6. 翻译招式类别等非 select2 的 select ==========

    function translateSimpleSelects() {
        // 翻译 special option（空值选项不在 getSelectOptions 中生成）
        // 辅助：仅在文本不同时才写入，避免无意义 DOM 变更
        function _setTextIfDiff(el, text) {
            if (el.text() !== text) el.text(text);
        }
        _setTextIfDiff($('select.item option[value=""]'), '(无)');
        _setTextIfDiff($('select.ability option[value=""]'), '(其他)');
        _setTextIfDiff($('select.tera-type option[value=""]'), '(无)');

        // 翻译招式类别
        var moveCatMap = { 'Physical': '物理', 'Special': '特殊', 'Status': '变化' };
        $('select.move-cat option').each(function () {
            var v = $(this).attr('value');
            var zh = moveCatMap[v];
            if (zh && $(this).text() !== zh) $(this).text(zh);
        });

        // 翻译 nature select（原生 select，不是 select2）
        $('select.nature option').each(function () {
            var val = $(this).val();
            var translated = tn(val);
            if (translated !== val && translated !== $(this).text()) $(this).text(translated);
        });

        // 翻译状态下拉
        var statusMap = {
            'Healthy': '健康', 'Poisoned': '中毒', 'Badly Poisoned': '剧毒',
            'Burned': '烧伤', 'Paralyzed': '麻痹', 'Asleep': '睡眠', 'Frozen': '冰冻'
        };
        $('select.status option').each(function () {
            var v = $(this).attr('value');
            if (statusMap[v] && $(this).text() !== statusMap[v]) $(this).text(statusMap[v]);
        });

        // 翻译连续攻击次数
        $('select.move-hits option').each(function () {
            var t = $(this).text();
            var m = t.match(/^(\d+) hits?$/);
            if (m) $(this).text(m[1] + '次');
        });

        // 翻译誓约招式
        var pledgeMap = { 'Grass Pledge': '草之誓约', 'Fire Pledge': '火之誓约', 'Water Pledge': '水之誓约' };
        $('select.move-pledge option').each(function () {
            var v = $(this).attr('value');
            if (pledgeMap[v] && $(this).text() !== pledgeMap[v]) $(this).text(pledgeMap[v]);
        });

        // 翻译效果叠加次数
        $('select.move-linearAddedBP option').each(function () {
            var t = $(this).text();
            var m = t.match(/^(\d+)x effect$/);
            if (m) $(this).text(m[1] + '次效果');
        });

        // 翻译对手招式选择
        $('select.move-opponent option').each(function () {
            var t = $(this).text();
            var m = t.match(/^Move (\d+)$/);
            if (m) $(this).text('招式' + m[1]);
        });

        // 翻译霸主（Supreme Overlord）倒下数
        $('select.ability-supreme option').each(function () {
            var t = $(this).text();
            var m = t.match(/^(\d+) down$/);
            if (m) $(this).text('倒下' + m[1] + '只');
        });

        // 翻译竞争心（Rivalry）
        var rivalryMap = { 'Off': '关闭', 'Same Gender': '同性', 'Opposite Genders': '异性' };
        $('select.ability-rivalry option').each(function () {
            var t = $(this).text();
            if (rivalryMap[t]) $(this).text(rivalryMap[t]);
        });

        // 翻译古代活性/夸克充能 能力选择
        var protoMap = { 'Attack': '攻击', 'Defense': '防御', 'Sp. Atk': '特攻', 'Sp. Def': '特防', 'Speed': '速度' };
        $('select.ability-proto-quark option').each(function () {
            var t = $(this).text();
            if (protoMap[t]) $(this).text(protoMap[t]);
        });

        // 翻译结果显示模式下拉
        var toggleMap = { 'SPs': '能力点', 'raw': '实际能力值', 'EVs': '努力值' };
        $('#toggleResult option').each(function () {
            var v = $(this).attr('value');
            if (toggleMap[v] && $(this).text() !== toggleMap[v]) $(this).text(toggleMap[v]);
        });

        // 翻译 Hidden Power optgroup
        $('optgroup[label="min Atk"]').attr('label', '最小攻击');
        $('optgroup[label="min Atk+Spe"]').attr('label', '最小攻击+速度');
        $('optgroup[label="max IVs"]').attr('label', '最大个体值');
        $('optgroup[label="min Spe"]').attr('label', '最小速度');
    }

    // ========== 6.5 原生 select 打开期间暂停翻译 ==========
    // Android WebView 的原生 select 弹窗会因 DOM 变更而反复重绘/闪烁
    var _nativeSelectOpen = false;

    // ========== 7. Monkey-patch calculate() ==========

    function patchCalculate() {
        if (typeof calculate !== 'function') return;

        var _origCalc = calculate;
        window.calculate = function () {
            _origCalc.apply(this, arguments);
            if (_nativeSelectOpen) return; // 弹窗打开时不翻译结果
            try { translateDynamicResults(); } catch (e) { }
        };

        // 额外拦截 .result-move change 事件——用户点击招式结果时，
        // 原版 ap_calc.js 直接写 #mainResult，不经过 calculate()
        $(document).on('change', '.result-move', function () {
            setTimeout(function () {
                if (_nativeSelectOpen) return;
                try { translateDynamicResults(); } catch (e) { }
            }, 50);
        });
    }

    // ========== 8. 翻译动态计算结果 ==========

    function translateDynamicResults() {
        // resultHeaderL/R
        ['#resultHeaderL', '#resultHeaderR'].forEach(function (sel) {
            $(sel).each(function () {
                var t = $(this).text();
                var m = t.match(/^(.+?)'s Moves/);
                if (m) $(this).text(tp(m[1]) + '的招式 (选择以查看详细结果)');
            });
        });

        // Move labels in result group
        ['#p1', '#p2'].forEach(function (panel) {
            var prefix = panel === '#p1' ? 'L' : 'R';
            for (var i = 1; i <= 4; i++) {
                $('label[for="resultMove' + prefix + i + '"]').each(function () {
                    var t = $(this).text();
                    if (t && t !== 'Loading...' && t !== '加载中...') $(this).text(tm(t));
                });
            }
        });

        // mainResult
        var $main = $('#mainResult');
        if ($main.length) {
            var html = $main.html();
            if (html && html.indexOf('Loading') === -1 && html.indexOf('加载') === -1 &&
                html.indexOf('how</a>') === -1 && html.indexOf('is it a one-hit KO') === -1) {
                try {
                    var translated = translateResultText(html);
                    if (translated !== html) $main.html(translated);
                } catch (e) { }
            }
        }
    }

    function translateResultText(html) {
        var parts = html.split(' -- ');
        var desc = translateResultDescription(parts[0]);
        if (parts.length >= 2) {
            var ko = tk(parts.slice(1).join(' -- '));
            return desc + ' -- ' + ko;
        }
        return desc;
    }

    // ---------- 结果描述翻译辅助函数 ----------

    /** 尝试翻译单个 token，依次尝试宝可梦/招式/特性/道具/属性 */
    function tryTranslateToken(word) {
        var t;
        t = tp(word); if (t !== word) return { text: t, type: 'pokemon' };
        t = tm(word); if (t !== word) return { text: t, type: 'move' };
        t = ta(word); if (t !== word) return { text: t, type: 'ability' };
        t = ti(word); if (t !== word) return { text: t, type: 'item' };
        t = tty(word); if (t !== word) return { text: t, type: 'type' };
        return null;
    }

    /** 对 token 数组做多词组合翻译，返回翻译后的 token 数组 */
    function translateTokens(tokens) {
        var result = [];
        var i = 0;
        while (i < tokens.length) {
            var tok = tokens[i];
            // 跳过纯数字/标点/已翻译的中文/HP/Lv./空白/斜杠
            if (/^[\d+()/:,.%\u2013\u2014-]+$/.test(tok) || /[\u4e00-\u9fff]/.test(tok)
                || tok === 'HP' || tok === '/' || /^Lv\.$/.test(tok) || tok === '') {
                result.push(tok);
                i++;
                continue;
            }
            // 尝试多词匹配（最多5词）
            var maxLen = Math.min(5, tokens.length - i);
            var found = false;
            for (var len = maxLen; len >= 1; len--) {
                // 拼接原始词组，然后剥离首尾括号做查找
                var rawPhrase = tokens.slice(i, i + len).join(' ');
                var stripped = rawPhrase.replace(/^\(+/, '').replace(/\)+$/, '');
                if (!stripped) continue;
                var tr = tryTranslateToken(stripped);
                if (tr) {
                    // 保留原始括号
                    var prefix = rawPhrase.match(/^\(+/);
                    var suffix = rawPhrase.match(/\)+$/);
                    result.push((prefix ? prefix[0] : '') + tr.text + (suffix ? suffix[0] : ''));
                    i += len;
                    found = true;
                    break;
                }
            }
            if (!found) {
                result.push(tok);
                i++;
            }
        }
        return result;
    }

    /** 翻译结果描述的一侧（攻击侧或防御侧），就地替换可识别的名称 */
    function translateSide(text) {
        if (!text) return text;

        // 静态关键词映射（不依赖字典）——多词优先替换
        var kwMap = {
            'burned': '灼伤', 'Helping Hand': '帮助', 'Power Spot': '能量点',
            'Battery': '蓄电', 'Ally Steely Spirit': '队友钢之心',
            'Flower Gift': '花之礼', 'Me First': '抢先一步', 'Charged': '充电',
            'Red Item-boosted': '红道具加成', 'Blue Item-boosted': '蓝道具加成',
            'revealed': '识破', 'Dynamax': '极巨化',
            'Super Effective': '效果拔群',
            'Tera 60 BP Boost': '太晶60威力加成',
            '1.2x Mask Boost': '1.2倍面具加成',
            '1st Use': '首次使用',
            'on a critical hit': '暴击时', 'under Gravity': '重力下',
            'after using Glaive Rush': '使用巨剑突击后',
            'with Friend Guard': '友情防守下',
            'through Protect': '穿透守住',
            'through Aurora Veil': '穿透极光幕',
            'through Reflect': '穿透反射壁',
            'through Light Screen': '穿透光之壁',
            'with custom modifiers': '自定义修正',
        };
        var sortedKw = Object.keys(kwMap).sort(function (a, b) { return b.length - a.length; });
        for (var k = 0; k < sortedKw.length; k++) {
            text = text.split(sortedKw[k]).join(kwMap[sortedKw[k]]);
        }

        // 翻译 "Tera-TypeName"
        text = text.replace(/Tera-(\S+)/g, function (m, t) {
            return '太晶' + tty(t);
        });

        // 翻译能力值缩写 "252+ Atk" / "0 SpD" 等
        var statMap = { 'Atk': '攻击', 'Def': '防御', 'SpA': '特攻', 'SpD': '特防', 'Spe': '速度' };
        text = text.replace(/(\d+[+-]?)\s+(Atk|Def|SpA|SpD|Spe)\b/g, function (m, num, stat) {
            return num + ' ' + (statMap[stat] || stat);
        });

        // 翻译 "X IV" / "X IVs"
        text = text.replace(/(\d+)\s+IVs?\b/g, '$1 个体值');

        // 翻译 "N BP"
        text = text.replace(/(\d+)\s+BP\b/g, '$1 威力');

        // 翻译 "(N hits)"
        text = text.replace(/\((\d+) hits?\)/g, '($1次)');

        // 翻译 "in Weather and Terrain Terrain" / "in Terrain Terrain" / "in Weather"
        text = text.replace(/\bin\s+(.+?)\s+and\s+(.+?)\s+Terrain\b/, function (m, w, t) {
            return '在 ' + (UI_LABELS[w] || w) + ' 和 ' + (UI_LABELS[t] || tty(t) || t) + '场地';
        });
        text = text.replace(/\bin\s+(.+?)\s+Terrain\b/, function (m, t) {
            return '在 ' + (UI_LABELS[t] || tty(t) || t) + '场地';
        });
        text = text.replace(/\bin\s+(Sun|Rain|Sand|Hail|Snow|Harsh Sun|Heavy Rain|Strong Winds)\b/, function (m, w) {
            return '在 ' + (UI_LABELS[w] || w);
        });

        // 翻译 "X of Ruin"
        text = text.replace(/(Sword|Beads|Tablets|Vessel)\s+of\s+Ruin/g, function (m, name) {
            var ruinMap = { 'Sword': '灾祸之剑', 'Beads': '灾祸之玉', 'Tablets': '灾祸之简', 'Vessel': '灾祸之鼎' };
            return ruinMap[name] || m;
        });

        // 翻译括号内的属性名 "(120 威力 Fire)" → "(120 威力 火)"  和  "(Fire)" → "(火)"
        text = text.replace(/\((\d+ 威力)\s+([A-Z][a-z]+)\)/g, function (m, bp, t) {
            var tt = tty(t);
            return '(' + bp + ' ' + (tt !== t ? tt : t) + ')';
        });
        text = text.replace(/\(([A-Z][a-z]+)\)/g, function (m, t) {
            var tt = tty(t);
            return tt !== t ? '(' + tt + ')' : m;
        });

        // 用多词组合翻译宝可梦名、招式名、特性名、道具名
        var tokens = text.split(/\s+/);
        tokens = translateTokens(tokens);
        return tokens.join(' ');
    }

    function translateResultDescription(desc) {
        if (!desc) return desc;

        try {
            // "2x MoveName (...)" 前缀
            desc = desc.replace(/^(\d+x)\s+(\S+)\s*\(/, function (m, mult, move) {
                return mult + ' ' + tm(move) + ' (';
            });

            // 以 " vs. " 分割攻防两侧
            var vsIdx = desc.indexOf(' vs. ');
            if (vsIdx === -1) return desc;

            var atkSide = desc.substring(0, vsIdx);
            var defSideRaw = desc.substring(vsIdx + 5); // skip " vs. "

            // 防御侧可能含 ": damageText"（来自 #mainResult 格式）
            // 格式示例："0 HP / 0 SpD Abomasnow: 39–46 (23.6 – 27.8%)"
            // 需要把 ": " 后面的伤害数值部分分离出来
            var defSide = defSideRaw;
            var dmgSuffix = '';
            // 匹配 "PokemonName: digits" — 冒号后紧跟数字/空格/百分号/括号/破折号
            var colonMatch = defSideRaw.match(/^(.*\S):\s*(\d[\d\u2013\u2014\s(),.%-]*)$/);
            if (colonMatch) {
                defSide = colonMatch[1];
                dmgSuffix = ': ' + colonMatch[2];
            }

            // 翻译两侧
            atkSide = translateSide(atkSide);
            defSide = translateSide(defSide);

            return atkSide + ' vs. ' + defSide + dmgSuffix;
        } catch (e) {
            return desc;
        }
    }

    // ========== 9. 静态 UI 标签替换 ==========

    function translateStaticLabels() {
        // 天气
        $('label[for="sun"]').text('晴天');
        $('label[for="rain"]').text('雨天');
        $('label[for="sand"]').text('沙暴');
        $('label[for="hail"]').text('冰雹');
        $('label[for="snow"]').text('雪天');
        $('label[for="clear"]').text('无');
        $('label[for="harsh-sun"]').text('大日照');
        $('label[for="heavy-rain"]').text('大雨');
        $('label[for="strong-winds"]').text('乱流');
        $('label[for="gscClear"]').text('无');
        $('label[for="gscSun"]').text('晴天');
        $('label[for="gscRain"]').text('雨天');
        $('label[for="gscSand"]').text('沙暴');

        // 场地
        $('label[for="electric"]').text('电气');
        $('label[for="grassy"]').text('青草');
        $('label[for="misty"]').text('薄雾');
        $('label[for="psychic"]').text('精神');
        $('label[for="noterrain"]').text('无');

        // 格式
        $('label[for="singles"]').text('单打');
        $('label[for="doubles"]').text('双打');

        // 面板标题
        $('#p1 .panel-title').text('宝可梦 1');
        $('#p2 .panel-title').text('宝可梦 2');
        // field-info panel-title 内含 #autolevel 子元素，不能用 .text() 覆盖
        $('.field-info .panel-title').contents().filter(function () {
            return this.nodeType === 3 && this.textContent.trim() === 'Field';
        }).each(function () { this.textContent = '场地 '; });
        $('.damage-calc .panel-title').text('保存配置');

        // Stat row
        $('tr.hp > td:first-child').text('HP');
        $('tr.at > td:first-child').text('攻击');
        $('tr.df > td:first-child').text('防御');
        $('tr.sa > td:first-child').text('特攻');
        $('tr.sd > td:first-child').text('特防');
        $('tr.sp > td:first-child').text('速度');

        // 各种 label
        var labelMap = {
            'Level': '等级', 'Nature': '性格', 'Ability': '特性',
            'Item': '道具', 'Status': '状态', 'Weight': '体重',
            'Type': '属性', 'Tera Type': '太晶属性', 'Forme': '形态',
            'Current HP': '当前HP',
            'EV total:': '努力值总和：', 'DVs total: ': 'DVs总和：',
            'Helping Hand': '帮助', 'Protect': '守住',
            'Reflect': '反射壁', 'Light Screen': '光之壁',
            'Aurora Veil': '极光幕', 'Stealth Rock': '隐形岩',
            'Spikes': '撒菱', 'Tailwind': '顺风', 'Lucky Chant': '幸运咒语',
            'Gravity': '重力', 'Battery': '蓄电', 'Power Spot': '能量点',
            'Steely Spirit': '钢之心', 'Neutralizing Gas': '化学变化气体',
            'Flower Gift': '花之礼', 'Friend Guard': '友情防守',
            'Aura Break': '气场破坏', 'Fairy Aura': '妖精气场', 'Dark Aura': '暗黑气场',
            'Tablets of Ruin ': '灾祸之简 ', 'Vessel of Ruin ': '灾祸之鼎 ',
            'Sword of Ruin ': '灾祸之剑 ', 'Beads of Ruin ': '灾祸之玉 ',
            'Sea of Fire': '烈火', 'Swamp': '沼泽', 'Custom': '自定义',
            'Terastallize?': '太晶化？', 'Z-Move': 'Z招式',
            'Max Move': '极巨招式',
            'Is it a Critical Hit?': '是否暴击？',
            'Was it a Critical Hit?': '是否暴击？',
            'Crit': '暴击', 'G-Max': '超极巨化',
            'Dynamax': '极巨化', 'Terastalize': '太晶化',
            'Transform': '变身',
            '2x BP': '2倍威力', '1st Use': '首次使用',
            'Salt Cure': '盐腌',
        };

        $('#p1 label, #p2 label, .field-info label').each(function () {
            var t = $(this).text().trim();
            if (labelMap[t]) $(this).text(labelMap[t]);
        });

        // 翻译灾祸特性中内嵌的能力值缩写
        $('label[for="tablets-of-ruin"]').html(function (_, h) { return h.replace('(-Atk)', '(-攻击)'); });
        $('label[for="vessel-of-ruin"]').html(function (_, h) { return h.replace('(-SpA)', '(-特攻)'); });
        $('label[for="sword-of-ruin"]').html(function (_, h) { return h.replace('(-Def)', '(-防御)'); });
        $('label[for="beads-of-ruin"]').html(function (_, h) { return h.replace('(-SpD)', '(-特防)'); });

        // Stat Points / DVs 表头
        $('th').each(function () {
            var t = $(this).text().trim();
            if (t === 'Base') $(this).text('种族值');
            else if (t === 'IVs') $(this).text('个体值');
            else if (t === 'EVs') $(this).text('努力值');
            else if (t === 'Stat Points') $(this).text('能力点');
            else if (t === 'DVs') $(this).text('DVs');
        });

        // 保存/导出按钮
        $('button').each(function () {
            var t = $(this).text().trim();
            if (t === 'Save Calc Set') $(this).text('保存配置');
            else if (t === 'Export Set') $(this).text('导出配置');
            else if (t === 'Delete Set') $(this).text('删除配置');
            else if (t === 'Export Team') $(this).text('导出队伍');
        });

        // 自定义配置名称输入框
        $('input.setCalc').each(function () {
            if ($(this).val() === 'My Calc Set') $(this).val('我的配置');
        });

        // Custom sets only 复选框文本
        $('.set-checkbox').each(function () {
            var html = $(this).html();
            if (html.indexOf('Custom sets only') !== -1) {
                $(this).html(html.replace('Custom sets only', '仅自定义配置'));
            }
        });

        // Weight (kg) label
        $('label').each(function () {
            var t = $(this).text().trim();
            if (t === 'Weight (kg)') $(this).text('体重 (kg)');
        });

        // 顶部标题
        $('.title-text').text('VGC 2026：宝可梦冠军伤害计算器');

        // 导航栏按钮
        var $themeBtn = $('#switchTheme');
        if ($themeBtn.length) {
            var tt = $themeBtn.text().trim();
            if (tt === 'Dark theme') $themeBtn.text('深色模式');
            else if (tt === 'Night theme') $themeBtn.text('夜间模式');
            else if (tt === 'Day theme') $themeBtn.text('日间模式');
        }
        $('label[for="switchDex"]').text('全国图鉴');
        $('label[for="toggleCustMods"]').text('自定义修改');

        // Field 面板内 Auto-Level
        $('#autolevel').contents().filter(function () {
            return this.nodeType === 3;
        }).each(function () {
            if (this.textContent.indexOf('Auto-Level to:') !== -1) {
                this.textContent = this.textContent.replace('Auto-Level to:', '自动等级：');
            }
        });

        // 顶部介绍段落
        $('p').each(function () {
            var t = $(this).text();
            if (t.indexOf('Legends Z-A Damage Calculator') !== -1) {
                $(this).html('全新的 <a href="za-calc.html"><b>传说 Z-A 伤害计算器</b></a> 现已上线！我们还有 <a href="lgpe-calc.html"><b>Let\'s Go 皮卡丘/伊布伤害计算器</b></a>。');
            } else if (t.indexOf('VGC 2026 calculator maintainenance') !== -1) {
                $(this).html('VGC 2026 计算器由 Alex Collins (<a href="https://twitter.com/nerd_of_now">@nerd_of_now</a>) 维护。计算器基础由 Jake White (<a href="https://twitter.com/squirrelboydev" target="_blank" rel="noopener noreferrer">@squirrelboydev</a>) 开发。');
            } else if (t.indexOf('Pokémon Champions is here') !== -1) {
                $(this).text('宝可梦冠军已到来！我们正在整理游戏中所有可用的宝可梦、招式、道具和特性，以及从朱/紫版以来的变更。');
            } else if (t.indexOf('For any issues with or other suggestions') !== -1) {
                $(this).html('如对本计算器有任何问题或建议，请通过 <a href="https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator/issues" target="_blank" rel="noopener noreferrer">Github</a>、<a href="https://bsky.app/profile/nerdofnow.bsky.social" target="_blank" rel="noopener noreferrer">Bluesky</a> 或 <a href="https://twitter.com/nerd_of_now" target="_blank" rel="noopener noreferrer">X (原 Twitter)</a> 联系 Alex。');
                // 在"联系Alex"段落后插入汉化版信息
                $(this).after(
                    '<p>本汉化版计算器来源：<a href="https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator/" target="_blank" rel="noopener noreferrer">https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator/</a></p>' +
                    '<p>汉化版由徐果虫进行开发，如汉化有疑问或建议，欢迎加入QQ群交流，群号：2151054295。</p>'
                );
            }
        });

        // Gen 6/7 旧配置提示
        $('p.gen-specific').each(function () {
            var t = $(this).text();
            if (t.indexOf("This generation's set updates") !== -1) {
                $(this).html('<br />本世代的配置更新仍在施工中。如果你想使用旧版 Trainer Tower 配置，请勾选此框：<input type="checkbox" id="WIPsets" />');
            }
        });

        // Loading 提示文本
        var $mainResult = $('#mainResult');
        if ($mainResult.length && $mainResult.text() === 'Loading...') {
            $mainResult.text('加载中...');
        }
        var $damageValues = $('#damageValues');
        if ($damageValues.length && $damageValues.text().indexOf('If you see this message') !== -1) {
            $damageValues.text('（如果此消息显示超过几秒，请尝试启用 JavaScript。如已启用，请尝试清除 Cookie。）');
        }

        // page title
        document.title = '宝可梦伤害计算器';
    }

    // ========== 10. 中文/拼音搜索增强 ==========

    function patchSearch() {
        // --- 10a. 宝可梦选择器：monkey-patch query 函数，增加拼音匹配 ---
        ['#p1', '#p2'].forEach(function (panel) {
            var $sel = $(panel + ' .set-selector');
            try {
                var s2 = $sel.data('select2');
                if (!s2 || !s2.opts || !s2.opts.query) return;

                var origQuery = s2.opts.query;
                s2.opts.query = function (query) {
                    if (typeof match_pokemon_name_inputs === 'function' && typeof getSetOptions === 'function' && query.term) {
                        var setOptions = getSetOptions(panel);
                        var pageSize = 30;
                        var results = [];
                        var termUpper = query.term.toUpperCase();
                        for (var i = 0; i < setOptions.length; i++) {
                            var pokeName = setOptions[i].pokemon.toUpperCase();
                            var baseName = typeof pokemonname_noforme === 'function'
                                ? pokemonname_noforme(setOptions[i].pokemon)
                                : setOptions[i].pokemon;
                            if (match_pokemon_name_inputs(baseName, termUpper)
                                || termUpper.split(" ").every(function (term) {
                                    return pokeName.indexOf(term) === 0 || pokeName.indexOf("-" + term) >= 0 || pokeName.indexOf(" " + term) >= 0;
                                })) {
                                results.push(setOptions[i]);
                            }
                        }
                        query.callback({
                            results: results.slice((query.page - 1) * pageSize, query.page * pageSize),
                            more: results.length >= query.page * pageSize
                        });
                    } else {
                        origQuery.apply(this, arguments);
                    }
                };
            } catch (e) { }
        });

        // --- 10b. 招式选择器：monkey-patch matcher，增加拼音匹配 ---
        $('.move-selector').each(function () {
            try {
                var s2 = $(this).data('select2');
                if (!s2 || !s2.opts) return;
                s2.opts.matcher = function (term, text, option) {
                    var val = option.val();
                    return (text.toUpperCase().indexOf(term.toUpperCase()) >= 0
                        || text.toUpperCase().indexOf(" " + term.toUpperCase()) >= 0
                        || val.toUpperCase().indexOf(term.toUpperCase()) === 0
                        || val.toUpperCase().indexOf(" " + term.toUpperCase()) >= 0
                        || (typeof match_move_name_inputs === 'function' && match_move_name_inputs(val, term.toUpperCase())));
                };
            } catch (e) { }
        });

        // --- 10c. 特性选择器：monkey-patch matcher，增加英文名匹配 ---
        $('select.ability').each(function () {
            try {
                var s2 = $(this).data('select2');
                if (!s2 || !s2.opts) return;
                s2.opts.matcher = function (term, text, option) {
                    var val = option.val();
                    return (text.toUpperCase().indexOf(term.toUpperCase()) === 0
                        || text.toUpperCase().indexOf(" " + term.toUpperCase()) >= 0
                        || val.toUpperCase().indexOf(term.toUpperCase()) === 0
                        || val.toUpperCase().indexOf(" " + term.toUpperCase()) >= 0);
                };
            } catch (e) { }
        });

        // --- 10d. 道具选择器：monkey-patch matcher，增加英文名匹配 ---
        $('select.item').each(function () {
            try {
                var s2 = $(this).data('select2');
                if (!s2 || !s2.opts) return;
                s2.opts.matcher = function (term, text, option) {
                    var val = option.val();
                    return (text.toUpperCase().indexOf(term.toUpperCase()) === 0
                        || text.toUpperCase().indexOf(" " + term.toUpperCase()) >= 0
                        || val.toUpperCase().indexOf(term.toUpperCase()) === 0
                        || val.toUpperCase().indexOf(" " + term.toUpperCase()) >= 0);
                };
            } catch (e) { }
        });
    }

    // ========== 11. 初始化 ==========

    $(document).ready(function () {
        // 300ms: monkey-patches + 静态标签
        setTimeout(function () {
            patchCalculate();
            translateStaticLabels();
        }, 300);

        // 600ms: 宝可梦 select2 format patch + 简单 select 翻译
        setTimeout(function () {
            patchSelect2Instances();
            translateSimpleSelects();
        }, 600);

        // 900ms: 中文/拼音搜索增强 + 翻译初始结果
        setTimeout(function () {
            patchSearch();
            translateDynamicResults();
        }, 900);

        // 观察 DOM 变化（debounce 防抖，翻译期间断开避免循环）
        var _observerTimer = null;
        var _observerTarget = { childList: true, subtree: true };
        var observer = new MutationObserver(function (mutations) {
            if (_nativeSelectOpen) return;
            if (_observerTimer) clearTimeout(_observerTimer);
            _observerTimer = setTimeout(function () {
                if (_nativeSelectOpen) return;
                observer.disconnect();
                translateSimpleSelects();
                observer.observe(document.body, _observerTarget);
            }, 200);
        });
        observer.observe(document.body, _observerTarget);

        // 原生 select（非 select2）打开/关闭时设置标志，暂停所有翻译活动
        // 防止 Android WebView 的 select 弹窗因 DOM 变更而反复重绘闪烁
        $(document).on('focus', 'select.nature, select.status, select.move-cat, select.move-hits, select.move-pledge, select.move-linearAddedBP, select.move-opponent, select.ability-supreme, select.ability-rivalry, select.ability-proto-quark, #toggleResult', function () {
            _nativeSelectOpen = true;
        });
        $(document).on('blur change', 'select.nature, select.status, select.move-cat, select.move-hits, select.move-pledge, select.move-linearAddedBP, select.move-opponent, select.ability-supreme, select.ability-rivalry, select.ability-proto-quark, #toggleResult', function (e) {
            // 延迟恢复，确保 change 事件引发的 DOM 变更结束后再开启翻译
            setTimeout(function () {
                _nativeSelectOpen = false;
                translateSimpleSelects();
                translateDynamicResults();
            }, 300);
        });
    });

    window.__CALC_LANG = 'zh';

})();
