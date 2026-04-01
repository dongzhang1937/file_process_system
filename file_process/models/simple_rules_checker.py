"""
静态拦截规则检查器
在 LLM 调用之前，先用特征词匹配快速判断是否命中预置规则。
命中后直接返回标准 JSON 格式的测试用例，跳过 LLM 调用。

支持按数据库类型分别匹配不同规则集。
"""
from config.logging_config import logger
from .simple_rules_mysql import SIMPLE_MYSQL_RULES
from .simple_rules_pg import SIMPLE_PG_RULES
from .simple_rules_oracle import SIMPLE_ORACLE_RULES


# 数据库类型 → 规则集映射
DB_TYPE_RULES = {
    'mysql': SIMPLE_MYSQL_RULES,
    'pg': SIMPLE_PG_RULES,
    'oracle': SIMPLE_ORACLE_RULES,
}

# db_type 标识 → 数据库大类映射
DB_TYPE_CATEGORY = {
    'mysql_centralized': 'mysql',
    'mysql_distributed': 'mysql',
    'pg_centralized': 'pg',
    'pg_distributed': 'pg',
    'oracle_centralized': 'oracle',
    'oracle_distributed': 'oracle',
}


def _match_rules(requirement_text, rules):
    """
    扫描规则列表，返回命中的规则（标准格式）或 None
    
    匹配逻辑：计算特征词命中率，超过 70% 或全部命中时判定拦截成功
    """
    req_lower = requirement_text.lower()
    
    for rule in rules:
        keywords = rule["特征词"]
        if not keywords:
            continue
        hit_count = sum(1 for kw in keywords if kw.lower() in req_lower)
        hit_rate = hit_count / len(keywords)
        
        if hit_rate >= 0.7 or hit_count == len(keywords):
            logger.info(f"[拦截规则] 命中: {rule['测试名']} "
                       f"(命中率={hit_rate:.0%}, {hit_count}/{len(keywords)})")
            return {
                "intent": "SQL_TEST",
                "extracted_points": [rule["测试名"]],
                "test_cases": [
                    {
                        "test_point": rule["测试名"],
                        "setup_sql": rule["前置SQL"],
                        "verify_sql": rule["验证SQL"],
                        "expected_behavior": "执行成功，满足招标要求"
                    }
                ]
            }
    
    return None


def check_simple_rules(requirement_text, db_category):
    """
    检查指定数据库大类的拦截规则
    
    Args:
        requirement_text: 需求文本
        db_category: 数据库大类 ('mysql' / 'pg' / 'oracle')
        
    Returns:
        dict: 标准 JSON 格式的测试用例，或 None（未命中）
    """
    rules = DB_TYPE_RULES.get(db_category)
    if not rules:
        return None
    return _match_rules(requirement_text, rules)


def check_simple_rules_for_db_types(requirement_text, sql_db_types):
    """
    为一组数据库类型分别检查拦截规则
    
    Args:
        requirement_text: 需求文本
        sql_db_types: 数据库类型列表，如 ['mysql_centralized', 'pg_centralized']
        
    Returns:
        dict: {db_category: matched_result} — 命中的大类及其测试用例
              未命中的大类不在返回字典中
    """
    if not sql_db_types:
        return {}
    
    # 按大类去重（同大类的多个子类型只需匹配一次）
    checked_categories = set()
    results = {}
    
    for db_type in sql_db_types:
        category = DB_TYPE_CATEGORY.get(db_type)
        if not category or category in checked_categories:
            continue
        checked_categories.add(category)
        
        matched = check_simple_rules(requirement_text, category)
        if matched:
            results[category] = matched
    
    return results


def get_db_category(db_type):
    """获取数据库类型的大类"""
    return DB_TYPE_CATEGORY.get(db_type, 'mysql')
