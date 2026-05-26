"""
Python 封装的宝可梦伤害计算器
通过调用 Node.js 的 @smogon/calc 库实现
"""

import json
import os
import subprocess
import threading
from typing import Dict, List, Optional, Union


_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'calc_debug.log')

def _calc_log(msg):
    import time as _t
    with open(_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f'{_t.strftime("%H:%M:%S")} {msg}\n')


class PersistentNodeProcess:
    """常驻 Node.js 进程管理器，通过 stdin/stdout JSON 行协议通信"""

    def __init__(self, script_path: str):
        self.script_path = script_path
        self._process = None
        self._lock = threading.Lock()

    def start(self):
        """启动 Node.js 进程，等待 ready 信号"""
        if self._process and self._process.poll() is None:
            return
        import time as _t
        t0 = _t.time()
        self._process = subprocess.Popen(
            ['node', self.script_path, '--persistent'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
        )
        ready_line = self._process.stdout.readline().strip()
        if not ready_line:
            err = self._process.stderr.read()
            raise RuntimeError(f'Node.js calculator failed to start: {err}')
        ready = json.loads(ready_line)
        if not ready.get('ready'):
            raise RuntimeError(f'Node.js calculator unexpected ready signal: {ready_line}')
        _calc_log(f'[PersistentNode] started pid={self._process.pid} in {(_t.time()-t0)*1000:.0f}ms')

    def _ensure_alive(self):
        """检查进程存活，崩了自动重启"""
        if self._process is None or self._process.poll() is not None:
            old_pid = self._process.pid if self._process else None
            status = 'None' if self._process is None else f'dead(rc={self._process.poll()})'
            _calc_log(f'[PersistentNode] _ensure_alive: process {status}, restarting... (old_pid={old_pid})')
            self.start()

    def send(self, params: Dict) -> Dict:
        """发送计算请求，返回结果（线程安全）"""
        import time as _t
        self._ensure_alive()
        with self._lock:
            try:
                t0 = _t.time()
                line = json.dumps(params, separators=(',', ':'))
                self._process.stdin.write(line + '\n')
                self._process.stdin.flush()
                result_line = self._process.stdout.readline().strip()
                elapsed = (_t.time() - t0) * 1000
                if not result_line:
                    _calc_log(f'[PersistentNode] send: empty response after {elapsed:.0f}ms')
                    return {'success': False, 'error': 'Calculator process returned empty response'}
                result = json.loads(result_line)
                if elapsed > 100:
                    _calc_log(f'[PersistentNode] send: SLOW {elapsed:.0f}ms success={result.get("success")}')
                return result
            except (BrokenPipeError, OSError) as e:
                _calc_log(f'[PersistentNode] send: DIED {e}')
                self._process = None
                return {'success': False, 'error': f'Calculator process died: {e}'}

    def shutdown(self):
        """关闭进程"""
        if self._process and self._process.poll() is None:
            try:
                self._process.stdin.close()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
            self._process = None


class PokemonDamageCalculator:
    """宝可梦伤害计算器"""

    def __init__(self, node_script_path: str = './calculator.js', persistent: bool = False):
        """
        初始化计算器

        Args:
            node_script_path: Node.js 计算脚本路径
            persistent: 是否使用常驻 Node.js 进程
        """
        self.node_script_path = node_script_path
        self._persistent = PersistentNodeProcess(node_script_path) if persistent else None

    def calculate(
        self,
        attacker_name: str,
        defender_name: str,
        move_name: str,
        attacker_evs: Optional[Dict[str, int]] = None,
        attacker_nature: str = 'Serious',
        attacker_ability: Optional[str] = None,
        attacker_item: Optional[str] = None,
        attacker_boosts: Optional[Dict[str, int]] = None,
        attacker_status: Optional[str] = None,
        attacker_cur_hp: Optional[int] = None,
        attacker_tera_type: Optional[str] = None,
        attacker_is_terastallized: bool = False,
        attacker_sps: Optional[Dict[str, int]] = None,
        attacker_form: Optional[str] = None,
        defender_evs: Optional[Dict[str, int]] = None,
        defender_nature: str = 'Serious',
        defender_ability: Optional[str] = None,
        defender_item: Optional[str] = None,
        defender_boosts: Optional[Dict[str, int]] = None,
        defender_status: Optional[str] = None,
        defender_cur_hp: Optional[int] = None,
        defender_tera_type: Optional[str] = None,
        defender_is_terastallized: bool = False,
        defender_sps: Optional[Dict[str, int]] = None,
        defender_form: Optional[str] = None,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        is_critical_hit: bool = False,
        is_reflect: bool = False,
        is_light_screen: bool = False,
        is_aurora_veil: bool = False,
        generation: int = 10,  # Champions
        mode: Optional[str] = None,
    ) -> Dict:
        """
        计算伤害

        Args:
            attacker_name: 攻击方宝可梦名称（英文）
            defender_name: 防御方宝可梦名称（英文）
            move_name: 招式名称（英文）
            attacker_evs: 攻击方努力值，如 {'spa': 252, 'spe': 252}
            attacker_nature: 攻击方性格
            attacker_ability: 攻击方特性
            attacker_item: 攻击方道具
            attacker_boosts: 攻击方能力等级，如 {'spa': 2}
            attacker_status: 攻击方状态（'brn', 'par', 'psn', 'tox', 'slp', 'frz'）
            attacker_cur_hp: 攻击方当前HP百分比（0-100）
            attacker_tera_type: 攻击方太晶属性（如 'Water', 'Fire'）
            defender_evs: 防御方努力值
            defender_nature: 防御方性格
            defender_ability: 防御方特性
            defender_item: 防御方道具
            defender_boosts: 防御方能力等级
            defender_status: 防御方状态（'brn', 'par', 'psn', 'tox', 'slp', 'frz'）
            defender_cur_hp: 防御方当前HP百分比（0-100，满血触发多重鳞片等特性）
            defender_tera_type: 防御方太晶属性
            weather: 天气（'Sun', 'Rain', 'Sand', 'Snow', 'Harsh Sunshine', 'Heavy Rain'）
            terrain: 场地（'Electric', 'Grassy', 'Psychic', 'Misty'）
            is_critical_hit: 是否会心一击
            is_reflect: 是否有反射壁
            is_light_screen: 是否有光墙
            generation: 世代（默认9）

        Returns:
            计算结果字典
        """
        params = {
            'generation': generation,
            'attacker': {
                'name': attacker_name,
                'form': attacker_form or '',
                'level': 50,
                'evs': attacker_evs or {},
                'sps': attacker_sps or {},
                'nature': attacker_nature,
                'ability': attacker_ability,
                'item': attacker_item,
                'boosts': attacker_boosts or {},
                'status': attacker_status,
                'curHP': attacker_cur_hp,
                'teraType': attacker_tera_type,
                'isTerastalize': attacker_is_terastallized,
            },
            'defender': {
                'name': defender_name,
                'form': defender_form or '',
                'level': 50,
                'evs': defender_evs or {},
                'sps': defender_sps or {},
                'nature': defender_nature,
                'ability': defender_ability,
                'item': defender_item,
                'boosts': defender_boosts or {},
                'status': defender_status,
                'curHP': defender_cur_hp,
                'teraType': defender_tera_type,
                'isTerastalize': defender_is_terastallized,
            },
            'move': move_name,
            'isCriticalHit': is_critical_hit,
            'field': {
                'weather': weather,
                'terrain': terrain,
                'isReflect': [False, is_reflect],
                'isLightScreen': [False, is_light_screen],
                'isAuroraVeil': [False, is_aurora_veil],
                'format': mode or 'Doubles',
            }
        }

        return self._call_node_calculator(params)

    def shutdown(self):
        """关闭常驻 Node.js 进程"""
        if self._persistent:
            self._persistent.shutdown()

    def _call_node_calculator(self, params: Dict) -> Dict:
        """调用 Node.js 计算器"""
        if self._persistent:
            return self._persistent.send(params)
        try:
            result = subprocess.run(
                ['node', self.node_script_path, json.dumps(params)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'error': f'Calculator error: {e.stderr}'
            }
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'error': f'JSON decode error: {str(e)}'
            }


# 使用示例
if __name__ == '__main__':
    calc = PokemonDamageCalculator()

    # 示例1: 原始盖欧卡对故勒顿使用喷水
    print('=== 示例1: 原始盖欧卡 vs 故勒顿 ===')
    result = calc.calculate(
        attacker_name='Kyogre-Primal',
        attacker_evs={'spa': 252, 'spe': 252, 'hp': 4},
        attacker_nature='Timid',
        attacker_ability='Primordial Sea',
        attacker_item='Choice Specs',
        defender_name='Koraidon',
        defender_evs={'hp': 252, 'atk': 252, 'spe': 4},
        defender_nature='Adamant',
        defender_ability='Orichalcum Pulse',
        move_name='Water Spout',
        weather='Heavy Rain',
    )

    if result['success']:
        print(f"描述: {result['description']}")
        print(f"伤害范围: {result['damageRange']}")
        print(f"击杀概率: {result['kochance']}")
    else:
        print(f"错误: {result['error']}")

    # 示例2: 带能力等级的计算
    print('\n=== 示例2: +2 特攻的盖欧卡 ===')
    result2 = calc.calculate(
        attacker_name='Kyogre',
        attacker_evs={'spa': 252},
        attacker_nature='Modest',
        attacker_ability='Drizzle',
        attacker_boosts={'spa': 2},  # +2 特攻
        defender_name='Groudon',
        defender_evs={'hp': 252, 'spd': 252},
        defender_nature='Careful',
        move_name='Water Spout',
        weather='Rain',
    )

    if result2['success']:
        print(f"描述: {result2['description']}")
        print(f"伤害范围: {result2['damageRange']}")
