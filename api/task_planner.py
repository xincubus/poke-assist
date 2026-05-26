"""
任务规划器 - 复杂问题拆分执行

当用户问题需要多步解决时，LLM 调用 create_plan 生成任务清单，
TaskPlanner 按拓扑排序逐个执行子任务，收集结果后返回汇总。

设计原则：
- 子任务直接调用 tool_executor（不经过 LLM），失败时 LLM 重试
- 依赖关系通过 from_task 标记，执行时解析为实际结果
- 最多 8 个子任务，防止滥用
"""
from typing import Dict, Any, List, Optional, Callable
from collections import defaultdict, deque


class TaskPlanner:
    """任务规划器：执行 create_plan 生成的多步任务"""

    MAX_TASKS = 8

    def __init__(self, tool_executor: Callable, llm_client=None, llm_model: str = None):
        """
        参数：
            tool_executor(tool_name, args) -> str  工具执行回调
            llm_client: OpenAI client，用于失败重试（可选）
            llm_model: 重试用的模型名
        """
        self.tool_executor = tool_executor
        self.llm_client = llm_client
        self.llm_model = llm_model

    def execute_plan(self, plan: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """
        执行任务计划

        参数：
            plan: {"goal": str, "tasks": [{"id": int, "action": str, "tool": str, "args": dict, "depends_on": [int]}]}
            progress_callback(step, label, detail, status)

        返回：
            {
                "goal": str,
                "results": {task_id: {"status": "success"|"failed", "data": str, "action": str}},
                "summary": str,  # 所有结果的格式化文本，供 LLM 总结
                "success_count": int,
                "fail_count": int,
            }
        """
        goal = plan.get("goal", "")
        tasks = plan.get("tasks", [])

        if not tasks:
            return {"goal": goal, "results": {}, "summary": "无任务", "success_count": 0, "fail_count": 0}

        # 限制任务数量
        if len(tasks) > self.MAX_TASKS:
            tasks = tasks[:self.MAX_TASKS]

        # 拓扑排序
        sorted_tasks = self._topological_sort(tasks)

        results = {}
        for i, task in enumerate(sorted_tasks):
            task_id = task["id"]
            action = task.get("action", f"任务{task_id}")

            # 进度回调
            if progress_callback:
                step = 50 + i  # step 50-57 用于规划器子任务
                progress_callback(step, f"任务{task_id}: {action}", "", "active")

            # 解析依赖：将 from_task 引用替换为实际结果
            resolved_args = self._resolve_args(task.get("args", {}), results)

            # 执行任务
            result = self._execute_task(task, resolved_args, results)

            results[task_id] = {
                "status": "success" if result["success"] else "failed",
                "data": result["data"],
                "action": action,
            }

            # 进度回调：完成
            if progress_callback:
                status = "done" if result["success"] else "done"
                detail = f"找到" if result["success"] else "未找到"
                progress_callback(step, f"任务{task_id}: {action}", detail, status)

        # 统计
        success_count = sum(1 for r in results.values() if r["status"] == "success")
        fail_count = len(results) - success_count

        # 生成汇总文本
        summary = self._format_results(goal, results)

        return {
            "goal": goal,
            "results": results,
            "summary": summary,
            "success_count": success_count,
            "fail_count": fail_count,
        }

    def _execute_task(self, task: Dict, resolved_args: Dict, all_results: Dict) -> Dict[str, Any]:
        """
        执行单个子任务

        策略：
        1. 有 tool + args → 直接调用 tool_executor
        2. 失败 → LLM 重试（最多 2 轮）
        3. 彻底失败 → 标记 failed
        """
        tool_name = task.get("tool")
        action = task.get("action", "")

        # 策略 1：直接调用工具
        if tool_name and resolved_args:
            try:
                result = self.tool_executor(tool_name, resolved_args)
                if result and not self._is_empty_result(result):
                    return {"success": True, "data": result}
            except Exception as e:
                print(f"TaskPlanner: 任务{task['id']} 工具调用失败: {e}")

        # 策略 2：LLM 重试（如果有 client）
        if self.llm_client:
            for retry in range(2):
                try:
                    result = self._llm_retry(task, all_results)
                    if result and not self._is_empty_result(result):
                        return {"success": True, "data": result}
                except Exception as e:
                    print(f"TaskPlanner: 任务{task['id']} LLM重试{retry+1}失败: {e}")

        # 策略 3：彻底失败
        return {"success": False, "data": f"未找到相关数据: {action}"}

    def _llm_retry(self, task: Dict, all_results: Dict) -> Optional[str]:
        """LLM 重试：让 LLM 换个方式执行任务"""
        if not self.llm_client:
            return None

        # 构建上下文：已有结果
        context_parts = []
        for tid, result in all_results.items():
            if result["status"] == "success":
                context_parts.append(f"任务{tid}结果: {result['data'][:200]}")
        context_text = "\n".join(context_parts) if context_parts else "无前置结果"

        prompt = f"""你正在执行一个多步任务计划中的一个子任务。

子任务：{task.get('action', '')}
建议工具：{task.get('tool', '无')}
建议参数：{task.get('args', {})}

前置任务结果：
{context_text}

请直接调用合适的工具完成这个子任务。如果建议的工具和参数不可用，换用其他工具或调整参数。"""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.llm_model,
                max_tokens=2048,
                temperature=0,
                messages=[
                    {"role": "system", "content": "你是宝可梦助手，正在执行多步任务。直接调用工具完成子任务。"},
                    {"role": "user", "content": prompt},
                ],
                tools=self._get_retry_tools(),
                tool_choice="required",
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                call = msg.tool_calls[0]
                name = call.function.name
                import json
                try:
                    args = json.loads(call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                return self.tool_executor(name, args)

        except Exception as e:
            print(f"TaskPlanner LLM 重试异常: {e}")

        return None

    def _get_retry_tools(self) -> list:
        """获取重试可用的工具列表（简化版，只包含常用查询工具）"""
        from .llm.helpers import load_tools
        try:
            tools_raw = load_tools("llm2b_query_tools.json")
            return [
                {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
                for t in tools_raw
            ]
        except Exception:
            return []

    @staticmethod
    def _resolve_args(args: Dict, results: Dict) -> Dict:
        """
        解析 args 中的 from_task 引用

        如 {"name": {"from_task": 1}} → {"name": "皮卡丘"}（假设任务1返回了"皮卡丘"）
        """
        if not args:
            return {}

        resolved = {}
        for key, value in args.items():
            if isinstance(value, dict) and "from_task" in value:
                ref_task_id = value["from_task"]
                if ref_task_id in results and results[ref_task_id]["status"] == "success":
                    # 用前置任务的结果替换
                    resolved[key] = results[ref_task_id]["data"]
                else:
                    # 依赖任务失败，保留空值
                    resolved[key] = ""
            elif isinstance(value, dict):
                resolved[key] = TaskPlanner._resolve_args(value, results)
            elif isinstance(value, list):
                resolved[key] = [
                    TaskPlanner._resolve_args(item, results) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                resolved[key] = value

        return resolved

    @staticmethod
    def _topological_sort(tasks: List[Dict]) -> List[Dict]:
        """拓扑排序：按依赖关系排列任务执行顺序"""
        task_map = {t["id"]: t for t in tasks}
        in_degree = defaultdict(int)
        graph = defaultdict(list)

        for task in tasks:
            tid = task["id"]
            deps = task.get("depends_on", [])
            in_degree[tid] = len(deps)
            for dep in deps:
                graph[dep].append(tid)

        # BFS 拓扑排序
        queue = deque([tid for tid in task_map if in_degree[tid] == 0])
        sorted_ids = []

        while queue:
            tid = queue.popleft()
            sorted_ids.append(tid)
            for next_tid in graph[tid]:
                in_degree[next_tid] -= 1
                if in_degree[next_tid] == 0:
                    queue.append(next_tid)

        # 处理循环依赖（不应发生，但安全起见）
        if len(sorted_ids) < len(tasks):
            remaining = [tid for tid in task_map if tid not in sorted_ids]
            sorted_ids.extend(remaining)

        return [task_map[tid] for tid in sorted_ids]

    @staticmethod
    def _is_empty_result(result: str) -> bool:
        """判断结果是否为空或无效"""
        if not result:
            return True
        stripped = result.strip()
        if not stripped:
            return True
        # 常见的空结果模式
        empty_patterns = [
            "未找到", "没有找到", "查不到", "不存在",
            "no results", "not found", "empty",
        ]
        lower = stripped.lower()
        return any(p in lower for p in empty_patterns) and len(stripped) < 50

    @staticmethod
    def _format_results(goal: str, results: Dict) -> str:
        """将所有子任务结果格式化为文本，供 LLM 总结"""
        parts = [f"目标: {goal}", ""]

        for task_id in sorted(results.keys()):
            r = results[task_id]
            status_icon = "✓" if r["status"] == "success" else "✗"
            parts.append(f"[{status_icon}] 任务{task_id}: {r['action']}")
            if r["status"] == "success":
                # 限制单个结果长度，防止 context 溢出
                data = r["data"]
                if len(data) > 1000:
                    data = data[:1000] + "...(已截断)"
                parts.append(data)
            else:
                parts.append(f"失败: {r['data']}")
            parts.append("")

        return "\n".join(parts)
