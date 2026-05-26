# 宝可梦伤害计算器（中文版，VGC2024）

Fork 自 Nimbasa City Post VGC Damage Calculator，由 professorSidon 等人翻译为中文。

## 文件结构

```
calc/
├── index.html           # 桌面版计算器（三栏布局：宝可梦1 | 场地+结果 | 宝可梦2）
├── mobile.html          # 手机端计算器（tab 切换布局：计算器/场地/宝可梦1/宝可梦2）
└── script_res/          # JS 计算引擎、CSS 样式、翻译数据
    ├── mobile.css        # 手机端样式覆盖（取消 min-width:100em，全宽布局，移动端适配）
    ├── damage_MASTER.js  # 核心伤害计算引擎
    ├── pokemon_data.js   # 宝可梦数据
    ├── url_loader.js     # URL 参数解析（自动填充计算器表单）
    ├── translate/        # 中文翻译数据
    └── ...               # 其他 JS/CSS 资源
```

### 桌面版（index.html）
三栏布局，左右分别为宝可梦1/2的配置面板，中间为场地设定和计算结果。

### 手机端（mobile.html）
复用 index.html 的全部 JS 引擎和 DOM 结构（保持所有 id/class 不变），用 4 个 tab 重新组织 UI：
- **计算器**：世代选择器 + 计算结果显示
- **场地**：等级、单打/双打、场地/天气/灾厄等条件设定
- **宝可梦1**：攻击方配置（种族、性格、努力值、招式等）
- **宝可梦2**：防御方配置

世代选择器分两行显示（一代~四代 / 五代~九代），标签简化。通过 `script_res/mobile.css` 覆盖桌面端样式实现移动端适配。

URL 参数机制与桌面版一致，`url_loader.js` 可自动填充表单。MAUI 安卓客户端通过 WebView 加载此页面。

网址：https://professorsidon.github.io/VGC-Damage-Calculator-Chinese/

## 修改记录

- **2026-04-08**：修复 `url_loader.js` 中 `setPokemon()` 的 bug——URL 参数中的宝可梦名（如 `hitmonchan`、`flutter-mane`）为小写，但 pokedex key 为 Title Case（如 `Hitmonchan`、`Flutter Mane`），大小写/分隔符不匹配导致 `pokedex[name]` 返回 undefined，属性和种族值不更新。新增 `toPokedexKey()` 函数，将 URL 参数中的宝可梦名统一转为 Title Case 空格格式。
- **2026-04-07**：修复 `ap_calc.js` 中 `getSetOptions()` 的 bug——宝可梦名称标题项（粗体）缺少 `id` 字段，导致点击标题无法更新宝可梦的属性和种族值。为标题项补充 `id: pokeName + " (空白配置)"`，使其行为与选择空白配置一致。

## 中文翻译
由MEI进行中文翻译，hdongZ进行Gen8翻译，professorSidon进行Gen8DLC+Gen9翻译及改进。
输入法部分数据来源于 https://github.com/MarkussLugia/Pboard
英文上游为 https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator

## 开源协议
翻译数据（translate文件夹）为GPLv3协议，其余部分与英文源一致。

## Original README
Originally the official Nuggetbridge damage calculator 2015-2016, later adapted for Trainer Tower 2017-2020, now adapted for Nimbasa City Post from 2021-present. Maintained and developed by nerd-of-now.

If there are inaccuracies please submit an issue or pull request!

Credits and license
-------------------

MIT License.

Written by Honko. VGC 2015 Update by Tapin and Firestorm. VGC 2016, 2017, 2018, 2019, and 2020 done by squirrelboyVGC. VGC 2021 onwards done by nerd-of-now.
