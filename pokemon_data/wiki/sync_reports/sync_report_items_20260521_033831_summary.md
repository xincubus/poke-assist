# Items 同步报告摘要
生成时间: 2026-05-21T03:38:31.037932
since: 2025-10-01  until: 2026-04-01
模型: mimo-v2.5
过期条目: 417  有变更: 14
新条目: 0  重命名: 0

## fling_power (6 条)

- 焦点镜 (scope-lens): '30' -> 10  (根据道具信息框的throw字段，值为10，与数据库值30不一致)
- 冰冷岩石 (icy-rock): '40' -> 60  (信息框中throw字段为60，表示投掷威力为60。)
- 紧绑束带 (binding-band): '30' -> 10  (从wiki道具信息框throw字段提取)
- 超极粉 (gigantamix): '50' -> 10  (从道具信息框 throw 字段提取数字为 10)
- 模仿香草 (mirror-herb): '' -> 30  (从道具信息框throw字段提取数字30)
- 机变骰子 (loaded-dice): '' -> 30  (从道具信息框的throw字段提取，数字为30)

## category (8 条)

- 公园球 (park-ball): 'standard-balls' -> special-balls  (公园球是特殊精灵球，用于伙伴公园或捕虫大赛，不属于标准球，根据wiki中bag字段为'精灵球'且道具用途推断，应映射为special-balls)
- 全息影像通讯器 (holo-caster--green): 'gameplay' -> plot-advancement  (wiki中bag字段为'重要物品'，对应剧情进展道具，应映射到plot-advancement分类)
- 究极奈克洛Ｚ (ultranecrozium-z--held): 'unused' -> z-crystals  (bag字段为'Ｚ纯晶'，映射到英文分类列表中的'z-crystals')
- 究极奈克洛Ｚ (ultranecrozium-z--bag): 'unused' -> z-crystals  (从bag字段'Ｚ纯晶'映射到英文分类'z-crystals')
- 奈克洛露奈合体器 (n-lunarizer--merge): 'unused' -> plot-advancement  (道具信息框中bag字段为'重要物品'，在PokeAPI分类中对应'plot-advancement')
- 敏捷糖果 (quick-candy): 'vitamins' -> species-candies  (从 wiki 页面的 bag2 字段'糖果罐'和描述'敏捷糖果是一种糖果'，推断分类应为 species-candies)
- 大金刚宝玉 (adamant-crystal): 'gameplay' -> held-items  (从wiki的bag字段'道具'映射到英文分类'held-items'，且道具为携带物品)
- 大白宝玉 (lustrous-globe): 'gameplay' -> held-items  (根据 wiki bag 字段和道具描述，大白宝玉是携带物品，应分类为 held-items)
