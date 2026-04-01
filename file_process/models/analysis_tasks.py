"""
批量需求分析 - 后台任务管理器

核心设计：
- 任务状态存储在 MySQL analysis_tasks 表，刷新/关闭页面不影响任务执行
- 使用 Python threading 在后台线程中逐条执行分析
- 前端通过轮询 /api/chat/task/{id}/status 获取进度
- 支持取消：设置 cancelled 标志，分析循环中检查并中断

数据流：
  前端提交 → 写入 DB (pending) → 启动后台线程 → 逐条分析 (running)
  → 每完成一条更新 DB (current++, results_json) → 全部完成 (completed)
  前端轮询 → 读 DB 中的 status/current/results_json → 渲染进度/结果
"""

import json
import uuid
import threading
from datetime import datetime
from config.db_config import dml_sql, fetch_one, query_sql
from config.logging_config import logger


# 用于在内存中跟踪运行中的任务线程及取消标志
_running_tasks = {}  # task_id -> {'thread': Thread, 'cancel_flag': threading.Event}


class AnalysisTaskManager:
    """批量分析后台任务管理器"""

    # ==================== 任务 CRUD ====================

    @classmethod
    def create_task(cls, username, requirements, params):
        """
        创建新任务

        Args:
            username: 用户名
            requirements: 需求列表 (list of dict)
            params: 分析参数 dict {document_ids, enable_web_search, enable_sql_validation, 
                                   sql_db_types, llm_config_id, temp_file}
        Returns:
            task_id (str)
        """
        task_id = str(uuid.uuid4())
        sql = """
            INSERT INTO analysis_tasks 
            (id, username, status, total, current, requirements_json, params_json, 
             results_json, created_at, updated_at)
            VALUES (%s, %s, 'pending', %s, 0, %s, %s, '[]', %s, %s)
        """
        now = datetime.now()
        dml_sql(sql, (
            task_id, username, len(requirements),
            json.dumps(requirements, ensure_ascii=False),
            json.dumps(params, ensure_ascii=False),
            now, now
        ))
        logger.info(f"[Task] 创建任务: id={task_id}, user={username}, total={len(requirements)}")
        return task_id

    @classmethod
    def get_task(cls, task_id):
        """获取任务完整信息"""
        sql = "SELECT * FROM analysis_tasks WHERE id = %s"
        row = fetch_one(sql, (task_id,))
        if row:
            cls._parse_json_fields(row)
        return row

    @classmethod
    def get_task_status(cls, task_id):
        """
        获取任务进度（轻量查询，不含完整 results_json）
        
        Returns:
            dict: {id, status, total, current, current_title, error, 
                   created_at, started_at, completed_at}
        """
        sql = """
            SELECT id, status, total, current, current_title, error,
                   created_at, started_at, completed_at, updated_at
            FROM analysis_tasks WHERE id = %s
        """
        row = fetch_one(sql, (task_id,))
        if row:
            # 日期字段转字符串
            for field in ('created_at', 'started_at', 'completed_at', 'updated_at'):
                if row.get(field) and isinstance(row[field], datetime):
                    row[field] = row[field].strftime('%Y-%m-%d %H:%M:%S')
        return row

    @classmethod
    def get_task_results(cls, task_id):
        """获取任务的完整结果"""
        sql = "SELECT status, total, current, results_json, summary_json, error FROM analysis_tasks WHERE id = %s"
        row = fetch_one(sql, (task_id,))
        if row:
            cls._parse_json_fields(row)
        return row

    @classmethod
    def get_active_task(cls, username):
        """
        获取用户当前活跃的任务（pending 或 running）
        
        Returns:
            task dict 或 None
        """
        sql = """
            SELECT id, status, total, current, current_title, error,
                   created_at, started_at, updated_at
            FROM analysis_tasks 
            WHERE username = %s AND status IN ('pending', 'running')
            ORDER BY created_at DESC LIMIT 1
        """
        row = fetch_one(sql, (username,))
        if row:
            for field in ('created_at', 'started_at', 'updated_at'):
                if row.get(field) and isinstance(row[field], datetime):
                    row[field] = row[field].strftime('%Y-%m-%d %H:%M:%S')
        return row

    @classmethod
    def list_tasks(cls, username, limit=20):
        """获取用户最近的任务列表"""
        sql = """
            SELECT id, status, total, current, current_title, error,
                   created_at, started_at, completed_at
            FROM analysis_tasks 
            WHERE username = %s 
            ORDER BY created_at DESC LIMIT %s
        """
        rows = query_sql(sql, (username, limit))
        for row in rows:
            for field in ('created_at', 'started_at', 'completed_at'):
                if row.get(field) and isinstance(row[field], datetime):
                    row[field] = row[field].strftime('%Y-%m-%d %H:%M:%S')
        return rows

    # ==================== 任务状态更新 ====================

    @classmethod
    def _update_status(cls, task_id, status, **kwargs):
        """更新任务状态"""
        updates = ["status = %s", "updated_at = %s"]
        params = [status, datetime.now()]

        for field, value in kwargs.items():
            if field in ('current', 'current_title', 'error', 'started_at', 'completed_at'):
                updates.append(f"{field} = %s")
                params.append(value)
            elif field in ('results_json', 'summary_json'):
                updates.append(f"{field} = %s")
                params.append(json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)

        params.append(task_id)
        sql = f"UPDATE analysis_tasks SET {', '.join(updates)} WHERE id = %s"
        dml_sql(sql, params)

    @classmethod
    def _append_result(cls, task_id, result, current_index, current_title=''):
        """
        追加一条分析结果到 results_json，同时更新 current 进度
        
        使用 JSON_ARRAY_APPEND 高效追加，避免读取-解析-写回整个 JSON
        """
        result_str = json.dumps(result, ensure_ascii=False)
        sql = """
            UPDATE analysis_tasks 
            SET results_json = JSON_ARRAY_APPEND(results_json, '$', CAST(%s AS JSON)),
                current = %s,
                current_title = %s,
                updated_at = %s
            WHERE id = %s
        """
        dml_sql(sql, (result_str, current_index, current_title, datetime.now(), task_id))

    # ==================== 任务执行 ====================

    @classmethod
    def start_task(cls, task_id, flask_app):
        """
        启动后台任务线程
        
        Args:
            task_id: 任务ID
            flask_app: Flask app 实例（线程中需要 app context）
        """
        cancel_event = threading.Event()
        thread = threading.Thread(
            target=cls._run_task,
            args=(task_id, flask_app, cancel_event),
            daemon=True,
            name=f"analysis-task-{task_id[:8]}"
        )
        _running_tasks[task_id] = {
            'thread': thread,
            'cancel_flag': cancel_event
        }
        thread.start()
        logger.info(f"[Task] 后台线程已启动: task_id={task_id[:8]}...")

    @classmethod
    def cancel_task(cls, task_id):
        """
        取消任务
        
        如果线程正在运行，设置取消标志；
        不管线程是否在跑，都更新 DB 状态为 cancelled
        """
        # 设置内存取消标志
        task_info = _running_tasks.get(task_id)
        if task_info:
            task_info['cancel_flag'].set()
            logger.info(f"[Task] 已设置取消标志: task_id={task_id[:8]}...")

        # 更新 DB 状态
        cls._update_status(task_id, 'cancelled', completed_at=datetime.now())
        logger.info(f"[Task] 任务已取消: task_id={task_id[:8]}...")
        return True

    @classmethod
    def _run_task(cls, task_id, flask_app, cancel_event):
        """
        后台线程执行函数
        
        在 Flask app context 内逐条分析需求，每条完成后更新 DB
        """
        with flask_app.app_context():
            try:
                # 1. 读取任务数据
                task = cls.get_task(task_id)
                if not task:
                    logger.error(f"[Task] 任务不存在: {task_id}")
                    return

                requirements = task.get('requirements_json', [])
                params = task.get('params_json', {})
                username = task.get('username', 'anonymous')

                # 2. 更新状态为 running
                cls._update_status(task_id, 'running', started_at=datetime.now())

                # 3. 初始化分析器
                from .requirement_analyzer import get_requirement_analyzer
                llm_config_id = params.get('llm_config_id')
                analyzer = get_requirement_analyzer(llm_config_id)

                document_ids = params.get('document_ids') or []
                enable_web_search = params.get('enable_web_search', True)
                enable_sql_validation = params.get('enable_sql_validation', True)
                sql_db_types = params.get('sql_db_types')

                total = len(requirements)
                results = []

                logger.info(f"[Task] 开始执行: task_id={task_id[:8]}, total={total}")

                # 4. 逐条分析
                for i, req in enumerate(requirements):
                    # ==== 检查取消标志 ====
                    if cancel_event.is_set():
                        logger.info(f"[Task] 检测到取消标志，停止执行: task_id={task_id[:8]}, "
                                   f"已完成 {i}/{total}")
                        # DB 状态已在 cancel_task() 中更新
                        break

                    # 也检查 DB 状态（防止内存标志丢失，如进程重启后）
                    if i > 0 and i % 5 == 0:
                        db_status = cls.get_task_status(task_id)
                        if db_status and db_status.get('status') == 'cancelled':
                            logger.info(f"[Task] DB状态为cancelled，停止执行: task_id={task_id[:8]}")
                            break

                    index = i + 1
                    req_title = ''
                    if isinstance(req, dict):
                        req_title = req.get('title', req.get('content', ''))[:60]
                    else:
                        req_title = str(req)[:60]

                    logger.info(f"[Task] 处理 {index}/{total}: {req_title}")

                    try:
                        result = analyzer.analyze_requirement(
                            req, username,
                            document_ids if document_ids else None,
                            enable_web_search=enable_web_search,
                            enable_sql_validation=enable_sql_validation,
                            sql_db_types=sql_db_types
                        )
                        result['index'] = index
                        results.append(result)
                    except Exception as e:
                        logger.error(f"[Task] 分析需求 {index} 失败: {e}")
                        result = {
                            'index': index,
                            'requirement': req_title,
                            'answer': f'分析失败: {str(e)}',
                            'match_type': 'error',
                            'confidence': 0
                        }
                        results.append(result)

                    # 更新 DB 进度（逐条追加结果）
                    next_title = ''
                    if i + 1 < total:
                        next_req = requirements[i + 1]
                        if isinstance(next_req, dict):
                            next_title = next_req.get('title', next_req.get('content', ''))[:60]
                        else:
                            next_title = str(next_req)[:60]

                    cls._append_result(task_id, result, index, next_title)

                # 5. 完成：生成摘要
                if not cancel_event.is_set():
                    summary = {
                        'exact': sum(1 for r in results if r.get('match_type') == 'exact'),
                        'sql_validation': sum(1 for r in results if r.get('match_type') == 'sql_validation'),
                        'web_search': sum(1 for r in results if r.get('match_type') == 'web_search'),
                        'combined': sum(1 for r in results if r.get('match_type') == 'combined'),
                        'llm_generated': sum(1 for r in results if r.get('match_type') == 'llm_generated'),
                        'none': sum(1 for r in results if r.get('match_type') in ['none', 'error'])
                    }
                    cls._update_status(
                        task_id, 'completed',
                        summary_json=summary,
                        completed_at=datetime.now()
                    )
                    logger.info(f"[Task] 任务完成: task_id={task_id[:8]}, total={total}, "
                               f"summary={summary}")

                # 清理临时文件
                temp_file = params.get('temp_file')
                if temp_file:
                    import os
                    if os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except Exception:
                            pass

            except Exception as e:
                logger.error(f"[Task] 任务执行异常: task_id={task_id[:8]}, error={e}", exc_info=True)
                cls._update_status(task_id, 'failed', error=str(e), completed_at=datetime.now())
            finally:
                # 清理内存中的任务引用
                _running_tasks.pop(task_id, None)

    # ==================== 工具方法 ====================

    @classmethod
    def _parse_json_fields(cls, row):
        """解析 JSON 字段"""
        for field in ('requirements_json', 'results_json', 'summary_json', 'params_json'):
            if row.get(field) and isinstance(row[field], str):
                try:
                    row[field] = json.loads(row[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # 日期字段转字符串
        for field in ('created_at', 'started_at', 'completed_at', 'updated_at'):
            if row.get(field) and isinstance(row[field], datetime):
                row[field] = row[field].strftime('%Y-%m-%d %H:%M:%S')

    @classmethod
    def cleanup_stale_tasks(cls):
        """
        清理卡住的任务（应用启动时调用）：
        1. 将所有 pending/running 的任务标记为 failed（服务重启后线程已丢失）
        2. 额外清理超过 2 小时仍为 running 的老任务（兜底）
        """
        now = datetime.now()
        
        # 服务重启时，所有 running/pending 的任务线程都不在了，标记为 failed
        sql_restart = """
            UPDATE analysis_tasks 
            SET status = 'failed', error = '服务重启，任务中断，请重新提交', 
                completed_at = %s, updated_at = %s
            WHERE status IN ('running', 'pending')
        """
        affected = dml_sql(sql_restart, (now, now))
        if affected:
            logger.info(f"[Task] 启动清理: 标记了 {affected} 个残留任务为 failed")
        return affected
