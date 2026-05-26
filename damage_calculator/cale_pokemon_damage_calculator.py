"""
基于 NCP VGC Damage Calculator 的 Python 桥接
替代 pokemon_damage_calculator.py，使用 web/cale/ 的计算引擎（支持 Gen 1-9 + Champions）
接口与 PokemonDamageCalculator 完全一致
"""

import os
from pokemon_damage_calculator import PokemonDamageCalculator


class CalePokemonDamageCalculator(PokemonDamageCalculator):
    """基于 NCP 计算引擎的伤害计算器（支持 Gen 1-9 + Champions）"""

    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        calculator_js = os.path.join(current_dir, 'cale', 'calculator.js')
        super().__init__(node_script_path=calculator_js, persistent=True)
