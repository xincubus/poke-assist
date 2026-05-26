# VGC 2026 Damage Calculator
Originally the official Nuggetbridge damage calculator 2015-2016, later adapted for Trainer Tower 2017-2020, now adapted for Nimbasa City Post from 2021-present. Maintained and developed by nerd-of-now.

If there are inaccuracies please submit an issue or pull request!

Credits and license
-------------------

MIT License.

Written by Honko. VGC 2015 Update by Tapin and Firestorm. VGC 2016, 2017, 2018, 2019, and 2020 done by squirrelboyVGC. VGC 2021 onwards done by nerd-of-now.

---

## 中文翻译覆盖层（overlay/）

在不修改任何英文原版文件的前提下，通过覆盖层脚本实现中文翻译和 URL 参数支持。

### 文件结构

```
overlay/
├── translate.js      # 宝可梦/招式/特性/道具/属性等中英翻译映射
├── search_input.js   # 宝可梦/招式拼音搜索数据 + 匹配函数（POKEMON_NAMES_INPUTS/MOVE_NAMES_INPUTS）
├── translate_ui.js   # UI 翻译引擎（getSelectOptions patch + Select2 matcher patch + calculate() patch + MutationObserver）
├── url_loader.js     # URL 参数加载器（自动填充计算器表单并触发计算）
├── zh.css            # 中文界面样式调整
└── mobile.css        # 手机端样式（tab切换布局、隐藏桌面元素、输入框适配、Gen 10 能力点切换下拉框 .mob-toggle-result-row）
```

### 入口页面

- `index.html` — 英文原版（不动）
- `index_zh.html` — 中文翻译版 + URL 参数支持（引入 overlay/ 下的脚本）
- `mobile.html` — 手机端中文版（tab切换布局：计算器/场地/宝可梦1/宝可梦2，引入同套 overlay 脚本）

### url_loader.js

从 URL query params 读取参数，自动填入计算器表单并触发计算。支持的参数包括：gen、p1/p2、move1-4、item/ability/nature、evs/ivs、sps（Gen 10 能力点）、tera、weather/terrain/status、mode、level 等。

### 修改记录

- **2026-04-21**：`url_loader.js` 新增 `findOptionValue()` 函数，实现招式/特性/道具下拉选项的大小写不敏感匹配。修复 `.title()` 产生的 `Light Of Ruin` 无法匹配 move_data.js 中 `Light of Ruin`（小写介词），导致 URL 参数 move1 无法选中招式的问题

- **2026-04-15**：`url_loader.js` 新增 `findPokedexKey()` 函数，实现大小写不敏感 + 连字符/空格不敏感的 pokedex key 查找。修复 URL 参数如 `p2=sneasler`（小写）或 `p2=iron-valiant`（连字符）无法匹配 pokedex 中的 `Sneasler` / `Iron Valiant`，导致回退到默认 Abomasnow 的问题

- **2026-04-15**：`translate_ui.js` 修复手机端性格下拉闪烁问题：
  - 根因：Android WebView 的原生 `<select>` 弹窗在 DOM 发生任何变更时会重新渲染，而 MutationObserver + translateSimpleSelects() + calculate() monkey-patch 在弹窗打开期间持续修改 DOM，导致弹窗每 200ms 重绘一次
  - 新增全局标志 `_nativeSelectOpen`：原生 select focus 时置 true，blur/change 后 300ms 置 false
  - MutationObserver 回调检查标志，弹窗打开期间完全暂停；翻译前 disconnect、翻译后 reconnect 防循环
  - `calculate()` 和 `.result-move change` 的 monkey-patch 也检查标志，弹窗期间跳过 `translateDynamicResults()`
  - 所有 select 翻译增加"已翻译则跳过"判断（`$(this).text() !== translated`），避免无意义 DOM 写入
  - blur/change 恢复后主动调用一次 `translateSimpleSelects()` + `translateDynamicResults()` 补翻译

- **2026-04-14**：`index_zh.html` 新增手机端自动跳转——检测 UA（Android/iPhone/iPod）时，`location.replace` 跳转 `mobile.html`（保留所有 URL 参数，不留浏览器历史；不含 iPad，iPad 用桌面版体验更好）

- **2026-04-14**：`mobile.css` panel-heading 黑色背景顶到面板边界（`margin-left/right: -8px` 抵消 poke-info/field-info 的 padding），文字保留 16px 左缩进；`.panel` 添加 `margin: 0 !important` 修复面板右侧溢出被裁；场地面板按钮组居中修复（`.panel-body { text-align: center }` + 覆盖 inline 固定 em 宽度为 `auto`）

- **2026-04-14**：`translate.js` 修复宝可梦形态名 undefined 问题：
  - 根因：`formes` 字典只存缩写 key（如 `'W'`），但 pokedex 用全称（如 `'Wash'`），`forme.types[type]` 查不到返回 `undefined`
  - 安全回退：翻译查不到时保留英文原文（`translated != null ? translated : type`），不再显示 undefined
  - 补全 9 个宝可梦共 15 个缺失的全称 key：Deoxys（Attack/Defense/Speed）、Kyurem（Black/White）、Wormadam（Sandy/Trash）、Shaymin（Sky）、Rotom（Wash/Heat/Frost/Fan/Mow）、Floette（Eternal）、Necrozma（Dusk-Mane/Dawn-Wings）、Lycanroc（Dusk）、Dudunsparce（Three-Segment）、Gimmighoul（Roaming）、Tauros（Paldea-Combat/Paldea-Blaze/Paldea-Aqua）

- **2026-04-14**：`mobile.css` 修复手机端排版问题：
  - 宝可梦 tab 属性/形态等标签左对齐（`.poke-info label { width: 4em; text-align: left }`），与桌面端一致
  - 暴击/Z招式/1st Use 等按钮 `width: auto !important; flex: 0 0 auto`，不再溢出面板
  - 计算器 tab 招式伤害区取消 `min-width: 50em`，结果行用 flex 布局防止溢出
  - 两个宝可梦伤害结果改为上下排列（`.move-result-subgroup { float: none; width: 100% }`）
  - 场地面板覆盖 inline style 固定宽度（`div[style] { width: 100% !important }`）
  - 选择器宽度从固定 px 改为 `calc(100% - 5em)` 自适应

- **2026-04-14**：`mobile.html` 移除宝可梦1/宝可梦2 tab 中的「能力点数」切换下拉框（SPs/实际能力值/EVs），切换世代时已自动处理，手动切换无效且多余；同步删除 `syncToggleResult()` 及 P2→P1 同步逻辑

- **2026-04-14**：`mobile.html` 修复 select2/搜索功能完全失效的问题——根本原因是缺少 `switchTheme` 按钮元素，`ap_calc.js` 的 `.gen` change 事件在 `document.getElementById('switchTheme').value` 处崩溃（null 引用），导致 `pokedex`/`moves`/`items` 等全局变量未赋值，select2 初始化链中断；修复：添加隐藏的 `<button id="switchTheme">`

- **2026-04-14**：`mobile.html` 将 Gen 10 能力点切换下拉框（SPs/实际能力值/EVs）从计算器 tab 移至宝可梦1/宝可梦2 tab（能力值表前），两个下拉框通过 `syncToggleResult()` 双向同步；`mobile.css` 新增 `.mob-toggle-result-row` 样式类

- **2026-04-10**：`url_loader.js` 新增 `sps1/sps2` 参数支持（Gen 10 能力点，0-32，逗号分隔）；`chat_service.py` Gen 10 URL 构建改用 `sps` 参数

- **2026-04-09**：修复 `url_loader.js` 中 alternate forme 加载 bug（如 Mega Charizard Y）：
  - jQuery 选择器从 `$(panelId + ' .forme select')` 改为 `$(panelId + ' select.forme')`——forme `<select>` 元素的 class 直接是 `"forme calc-trigger"`，而非嵌套在 `.forme` 容器内
  - forme 切换延迟从 50ms 增至 150ms，确保 `showFormes()` DOM 更新完成
  - `setPokemon()` 现在返回 forme 延迟值，`fillSide()` 会等待 forme 切换完成后再执行，避免用基础形态的种族值覆盖 Mega/Primal 形态
- **2026-04-09**：`translate_ui.js` 中文/拼音搜索增强：
  - 宝可梦选择器：monkey-patch Select2 query 函数，接入 `match_pokemon_name_inputs()` 拼音匹配（支持拼音全拼、拼音缩写、中文名、英文名、日文罗马字）
  - 招式选择器：monkey-patch Select2 matcher，接入 `match_move_name_inputs()` 拼音匹配（支持拼音/类型/缩写等）
  - 特性/道具选择器：monkey-patch Select2 matcher，增加 `option.val()`（英文名）匹配
  - 新增 `getSelectOptions` monkey-patch：在脚本加载时立即替换，无条件将 option text 翻译为中文（带缓存），确保初始化和切换宝可梦后 option text 始终为中文
  - MutationObserver 加 200ms debounce 防抖，避免高频 DOM 变更时重复执行翻译
- **2026-04-09**：`index_zh.html` 移除国内超时的外部资源：
  - 移除 Google Fonts（`fonts.googleapis.com`），中文版通过 `zh.css` 指定字体栈
  - 移除 Google 广告脚本（`pagead2.googlesyndication.com`），原本就未启用
- **2026-04-09**：`translate_ui.js` 伤害结果翻译重写 + 汉化版信息：
  - 重写 `translateResultDescription()`：旧版正则只匹配 `PokemonName MoveName vs. ...` 简单格式，无法处理含 EV/性格/道具/特性等修饰词的完整结果（如 `252+ Atk Choice Band Koraidon Flare Blitz vs. 252 HP / 0 Def Miraidon`）
  - 新方案：以 ` vs. ` 分割攻防两侧，`translateSide()` 逐侧翻译——先替换静态关键词（burned/Helping Hand/through Reflect 等），再翻译 Tera-属性、能力值缩写（Atk→攻击）、IV/BP/hits、天气/场地/灾祸特性，最后用多词组合匹配翻译宝可梦名/招式名/特性名/道具名
  - `translateTokens()` 多词组合匹配时剥离首尾括号再查字典，匹配后还原括号（解决 `(No Move)` 等被括号粘连导致匹配失败的问题）
  - 防御侧用正则分离 `: damageText` 后缀，避免冒号粘在宝可梦名上导致翻译失败
  - 正则字符类中 Unicode 破折号（en-dash/em-dash）改用 `\u2013\u2014` 转义，避免字符范围解析错误导致整个 IIFE 崩溃
  - 额外监听 `.result-move` change 事件（50ms 延迟后重翻译），解决用户点击招式结果时 `ap_calc.js` 直接写 `#mainResult` 不经过 `calculate()` 的问题
  - `index_zh.html` 脚本引用加 `?v=2` 缓存破坏参数
  - 在"联系Alex"段落后插入汉化版来源链接和QQ群信息