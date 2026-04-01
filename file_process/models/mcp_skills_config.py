"""
配置管理器
- SkillsConfigManager: LLM System Prompt 模板 CRUD
- SQLDBConfigManager: SQL 数据库连接配置 CRUD

遵循 LLMConfigManager 模式：参数化SQL、软删除、dml_sql/query_sql/fetch_one
"""
import re
import json
from datetime import datetime
from config.db_config import dml_sql, query_sql, fetch_one, fetch_all, dml_sql_with_insert_id
from config.logging_config import logger


# ==================== Skills 配置管理器（LLM Prompt模板） ====================

class SkillsConfigManager:
    """LLM System Prompt 模板管理器"""

    # 支持的场景类型
    SCENE_TYPES = {
        'sql_extraction_mysql': 'SQL提取(MySQL)',
        'sql_extraction_pg': 'SQL提取(PostgreSQL)',
        'sql_extraction_oracle': 'SQL提取(Oracle)',
        'web_search_summary': '搜索结果归纳',
        'general': '通用',
    }

    @classmethod
    def create_config(cls, name, scene_type, system_prompt,
                      variables_json=None, is_default=False):
        """
        创建 Prompt 模板

        Args:
            name: 模板名称
            scene_type: 场景类型
            system_prompt: 模板内容（支持 {{变量名}} 占位符）
            variables_json: 变量定义（dict）
            is_default: 是否设为该场景的默认模板
        """
        if scene_type not in cls.SCENE_TYPES:
            raise ValueError(f"不支持的场景类型: {scene_type}")

        # 如果设为默认，先取消该场景的其他默认
        if is_default:
            cls._clear_scene_default(scene_type)

        sql = """
            INSERT INTO skills_configs
            (name, scene_type, system_prompt, variables_json, is_default,
             is_enabled, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 1, 1, %s, %s)
        """
        now = datetime.now()
        vars_str = json.dumps(variables_json, ensure_ascii=False) if variables_json else None

        config_id, _ = dml_sql_with_insert_id(sql, (
            name, scene_type, system_prompt, vars_str,
            1 if is_default else 0, now, now
        ))
        return config_id

    @classmethod
    def get_config(cls, config_id):
        """获取指定模板"""
        sql = "SELECT * FROM skills_configs WHERE id = %s AND is_active = 1"
        result = fetch_one(sql, (config_id,))
        if result:
            cls._parse_json_fields(result)
        return result

    @classmethod
    def list_configs(cls, scene_type=None):
        """
        列出模板列表

        Args:
            scene_type: 可选，筛选指定场景类型
        """
        if scene_type:
            sql = """SELECT * FROM skills_configs
                     WHERE is_active = 1 AND scene_type = %s
                     ORDER BY is_default DESC, created_at DESC"""
            results = query_sql(sql, (scene_type,))
        else:
            sql = """SELECT * FROM skills_configs
                     WHERE is_active = 1
                     ORDER BY scene_type, is_default DESC, created_at DESC"""
            results = query_sql(sql)

        for r in results:
            cls._parse_json_fields(r)
        return results

    @classmethod
    def update_config(cls, config_id, **kwargs):
        """更新模板"""
        allowed_fields = ['name', 'scene_type', 'system_prompt', 'variables_json',
                          'is_default', 'is_enabled', 'is_active']
        updates = []
        params = []

        for field, value in kwargs.items():
            if field in allowed_fields:
                if field == 'variables_json' and value is not None:
                    value = json.dumps(value, ensure_ascii=False)
                if field == 'is_default' and value:
                    # 获取当前配置的 scene_type
                    current = cls.get_config(config_id)
                    if current:
                        scene = kwargs.get('scene_type', current['scene_type'])
                        cls._clear_scene_default(scene)
                updates.append(f"{field} = %s")
                params.append(value)

        if not updates:
            return False

        updates.append("updated_at = %s")
        params.append(datetime.now())
        params.append(config_id)

        sql = f"UPDATE skills_configs SET {', '.join(updates)} WHERE id = %s AND is_active = 1"
        affected = dml_sql(sql, params)
        return affected > 0

    @classmethod
    def delete_config(cls, config_id):
        """软删除模板"""
        sql = "UPDATE skills_configs SET is_active = 0, updated_at = %s WHERE id = %s"
        affected = dml_sql(sql, (datetime.now(), config_id))
        return affected > 0

    @classmethod
    def get_prompt_for_scene(cls, scene_type):
        """
        获取指定场景的默认启用模板

        Args:
            scene_type: 场景类型

        Returns:
            模板记录 dict 或 None
        """
        sql = """SELECT * FROM skills_configs
                 WHERE scene_type = %s AND is_default = 1
                 AND is_enabled = 1 AND is_active = 1
                 LIMIT 1"""
        result = fetch_one(sql, (scene_type,))
        if result:
            cls._parse_json_fields(result)
        return result

    @classmethod
    def render_prompt(cls, template_id_or_record, variables=None):
        """
        渲染模板：替换 {{变量名}} 占位符

        Args:
            template_id_or_record: 模板ID (int) 或 模板记录 (dict)
            variables: 变量字典，覆盖默认变量值

        Returns:
            渲染后的 system prompt 字符串
        """
        if isinstance(template_id_or_record, dict):
            record = template_id_or_record
        else:
            record = cls.get_config(template_id_or_record)

        if not record:
            return None

        template = record.get('system_prompt', '')
        # 合并默认变量和传入变量
        default_vars = record.get('variables_json') or {}
        if isinstance(default_vars, str):
            try:
                default_vars = json.loads(default_vars)
            except (json.JSONDecodeError, TypeError):
                default_vars = {}

        merged_vars = {**default_vars, **(variables or {})}

        # 替换 {{变量名}} 占位符
        def replace_var(match):
            var_name = match.group(1).strip()
            return str(merged_vars.get(var_name, match.group(0)))

        rendered = re.sub(r'\{\{(\w+)\}\}', replace_var, template)
        return rendered

    @classmethod
    def get_scene_types(cls):
        """获取支持的场景类型列表"""
        return cls.SCENE_TYPES

    @classmethod
    def _clear_scene_default(cls, scene_type):
        """清除指定场景的默认模板标记"""
        sql = """UPDATE skills_configs SET is_default = 0, updated_at = %s
                 WHERE scene_type = %s AND is_default = 1 AND is_active = 1"""
        dml_sql(sql, (datetime.now(), scene_type))

    @classmethod
    def _parse_json_fields(cls, record):
        """解析 JSON 字段"""
        if record.get('variables_json'):
            try:
                record['variables_json'] = json.loads(record['variables_json'])
            except (json.JSONDecodeError, TypeError):
                record['variables_json'] = {}


# ==================== SQL 数据库连接配置管理器 ====================

class SQLDBConfigManager:
    """SQL 数据库连接配置管理器"""

    # 6种数据库类型定义（只用两种驱动）
    DB_TYPES = {
        'mysql_centralized': {
            'name': '兼容MySQL集中式',
            'driver': 'pymysql',
            'reuse_from': None,
            'default_port': 3306
        },
        'mysql_distributed': {
            'name': '兼容MySQL分布式(TDSQL)',
            'driver': 'pymysql',
            'reuse_from': None,
            'default_port': 3306
        },
        'pg_centralized': {
            'name': '兼容PG集中式',
            'driver': 'psycopg2',
            'reuse_from': None,
            'default_port': 5432
        },
        'pg_distributed': {
            'name': '兼容PG分布式(TDSQL-PG)',
            'driver': 'psycopg2',
            'reuse_from': None,
            'default_port': 5432
        },
        'oracle_centralized': {
            'name': '兼容Oracle集中式',
            'driver': 'psycopg2',
            'reuse_from': 'pg_centralized',
            'default_port': 5432
        },
        'oracle_distributed': {
            'name': '兼容Oracle分布式',
            'driver': 'psycopg2',
            'reuse_from': 'pg_distributed',
            'default_port': 5432
        },
    }

    @classmethod
    def create_config(cls, db_type, host='', port=0, username='', password='',
                      database_name='', name='', use_independent=False):
        """
        创建 SQL 数据库连接配置

        Args:
            db_type: 数据库类型标识
            host, port, username, password, database_name: 连接参数
            name: 配置别名
            use_independent: Oracle类型是否使用独立连接
        """
        if db_type not in cls.DB_TYPES:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        type_info = cls.DB_TYPES[db_type]
        driver_type = type_info['driver']
        reuse_from = type_info['reuse_from']

        if not port:
            port = type_info['default_port']

        if not name:
            name = type_info['name']

        sql = """
            INSERT INTO sql_db_configs
            (db_type, name, host, port, username, password, database_name,
             driver_type, reuse_from, use_independent,
             is_enabled, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1, %s, %s)
        """
        now = datetime.now()
        config_id, _ = dml_sql_with_insert_id(sql, (
            db_type, name, host, port, username, password, database_name,
            driver_type, reuse_from, 1 if use_independent else 0, now, now
        ))
        return config_id

    @classmethod
    def get_config(cls, config_id):
        """获取指定配置"""
        sql = "SELECT * FROM sql_db_configs WHERE id = %s AND is_active = 1"
        return fetch_one(sql, (config_id,))

    @classmethod
    def get_config_by_type(cls, db_type):
        """根据数据库类型获取配置"""
        sql = "SELECT * FROM sql_db_configs WHERE db_type = %s AND is_active = 1 LIMIT 1"
        return fetch_one(sql, (db_type,))

    @classmethod
    def list_configs(cls):
        """列出所有有效配置"""
        sql = """SELECT * FROM sql_db_configs WHERE is_active = 1
                 ORDER BY FIELD(db_type, 'mysql_centralized','mysql_distributed',
                 'pg_centralized','pg_distributed','oracle_centralized','oracle_distributed')"""
        results = query_sql(sql)
        return results

    @classmethod
    def update_config(cls, config_id, **kwargs):
        """更新配置"""
        allowed_fields = ['name', 'host', 'port', 'username', 'password',
                          'database_name', 'use_independent', 'is_enabled', 'is_active']
        updates = []
        params = []

        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = %s")
                params.append(value)

        if not updates:
            return False

        updates.append("updated_at = %s")
        params.append(datetime.now())
        params.append(config_id)

        sql = f"UPDATE sql_db_configs SET {', '.join(updates)} WHERE id = %s AND is_active = 1"
        affected = dml_sql(sql, params)
        return affected > 0

    @classmethod
    def upsert_config(cls, db_type, **kwargs):
        """
        按 db_type 创建或更新配置（前端保存时使用）

        如果该 db_type 已存在记录则更新，否则创建新记录
        """
        existing = cls.get_config_by_type(db_type)
        if existing:
            return cls.update_config(existing['id'], **kwargs)
        else:
            return cls.create_config(db_type, **kwargs)

    @classmethod
    def delete_config(cls, config_id):
        """软删除配置"""
        sql = "UPDATE sql_db_configs SET is_active = 0, updated_at = %s WHERE id = %s"
        affected = dml_sql(sql, (datetime.now(), config_id))
        return affected > 0

    @classmethod
    def get_connection_params(cls, db_type):
        """
        获取完整的数据库连接参数

        Oracle 类型如果 use_independent=False，则从对应 PG 配置取 host/port/user/password，
        仅使用自身的 database_name

        Returns:
            dict: {host, port, username, password, database_name, driver_type} 或 None
        """
        config = cls.get_config_by_type(db_type)
        if not config:
            return None

        if not config.get('is_enabled'):
            return None

        type_info = cls.DB_TYPES.get(db_type, {})
        reuse_from = type_info.get('reuse_from')

        # Oracle 类型且 use_independent=False -> 复用 PG 连接参数
        if reuse_from and not config.get('use_independent'):
            pg_config = cls.get_config_by_type(reuse_from)
            if not pg_config:
                logger.warning(f"Oracle类型 {db_type} 需要复用 {reuse_from} 配置，但未找到")
                return None

            return {
                'host': pg_config['host'],
                'port': pg_config['port'],
                'username': pg_config['username'],
                'password': pg_config['password'],
                'database_name': config['database_name'],  # 使用自身的Oracle兼容库名
                'driver_type': type_info['driver'],
                'db_type': db_type,
                'reused_from': reuse_from
            }

        # 独立连接
        return {
            'host': config['host'],
            'port': config['port'],
            'username': config['username'],
            'password': config['password'],
            'database_name': config['database_name'],
            'driver_type': config['driver_type'],
            'db_type': db_type,
            'reused_from': None
        }

    @classmethod
    def test_connection(cls, db_type=None, host=None, port=None,
                        username=None, password=None, database_name=None,
                        config_id=None):
        """
        测试数据库连接

        可以传入直接参数测试，也可以传 config_id 使用已保存的配置测试

        Returns:
            dict: {success: bool, message: str, version: str}
        """
        # 获取连接参数
        if config_id:
            params = cls.get_connection_params_by_id(config_id)
            if not params:
                return {'success': False, 'message': '配置不存在或已禁用'}
        elif db_type:
            # 如果是 Oracle 类型且需要复用，先获取 PG 参数
            type_info = cls.DB_TYPES.get(db_type, {})
            reuse_from = type_info.get('reuse_from')

            if reuse_from and not host:
                # 需要从 PG 配置复用
                pg_config = cls.get_config_by_type(reuse_from)
                if not pg_config:
                    return {'success': False, 'message': f'未找到 {reuse_from} 配置，无法复用连接'}
                host = pg_config['host']
                port = pg_config['port']
                username = pg_config['username']
                password = pg_config['password']

            params = {
                'host': host,
                'port': port,
                'username': username,
                'password': password,
                'database_name': database_name,
                'driver_type': type_info.get('driver', 'pymysql'),
                'db_type': db_type
            }
        else:
            return {'success': False, 'message': '请提供数据库类型或配置ID'}

        # 尝试连接
        driver = params.get('driver_type', 'pymysql')
        try:
            if driver == 'pymysql':
                import pymysql
                conn = pymysql.connect(
                    host=params['host'],
                    port=int(params['port']),
                    user=params['username'],
                    password=params['password'],
                    database=params['database_name'],
                    connect_timeout=5
                )
                cursor = conn.cursor()
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()[0]
                cursor.close()
                conn.close()
                return {
                    'success': True,
                    'message': '连接成功',
                    'version': version
                }
            elif driver == 'psycopg2':
                try:
                    import psycopg2
                except ImportError:
                    return {'success': False, 'message': 'psycopg2 驱动未安装，请执行: pip install psycopg2-binary'}

                conn = psycopg2.connect(
                    host=params['host'],
                    port=int(params['port']),
                    user=params['username'],
                    password=params['password'],
                    dbname=params['database_name'],
                    connect_timeout=5
                )
                cursor = conn.cursor()
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                cursor.close()
                conn.close()
                return {
                    'success': True,
                    'message': '连接成功',
                    'version': version
                }
            else:
                return {'success': False, 'message': f'不支持的驱动类型: {driver}'}

        except Exception as e:
            logger.error(f"数据库连接测试失败 ({db_type}): {e}")
            return {'success': False, 'message': f'连接失败: {str(e)}'}

    @classmethod
    def get_connection_params_by_id(cls, config_id):
        """通过配置ID获取完整连接参数"""
        config = cls.get_config(config_id)
        if not config:
            return None
        return cls.get_connection_params(config['db_type'])

    @classmethod
    def get_enabled_db_types(cls):
        """获取所有已启用的数据库类型列表"""
        sql = "SELECT db_type FROM sql_db_configs WHERE is_enabled = 1 AND is_active = 1"
        results = query_sql(sql)
        return [r['db_type'] for r in results]

    @classmethod
    def get_db_types(cls):
        """获取支持的数据库类型信息"""
        return cls.DB_TYPES

    @classmethod
    def mask_password(cls, password):
        """密码脱敏"""
        if not password:
            return ''
        if len(password) <= 4:
            return '****'
        return password[:4] + '****'
