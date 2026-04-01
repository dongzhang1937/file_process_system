#!/usr/bin/env python3
"""
网络搜索配置工具
用于检查和配置网络搜索服务
"""
import sys
sys.path.insert(0, '/mnt/e/codebuddy/data/tencentcode/data')

from config.db_config import query_sql, dml_sql_with_insert_id, dml_sql
from datetime import datetime
import json

def check_web_search_config():
    """检查网络搜索配置"""
    print("=== 网络搜索配置检查 ===\n")
    
    try:
        configs = query_sql('SELECT * FROM web_search_configs WHERE is_active = 1')
        if configs:
            print(f"找到 {len(configs)} 个搜索配置:\n")
            for c in configs:
                print(f"  ID: {c.get('id')}")
                print(f"  搜索引擎: {c.get('search_engine')}")
                print(f"  API URL: {c.get('api_url', 'N/A')}")
                print(f"  API Key: {'*' * 8 if c.get('api_key') else '未设置'}")
                print(f"  是否默认: {'是' if c.get('is_default') else '否'}")
                print(f"  额外参数: {c.get('extra_params', {})}")
                print("-" * 40)
            return True
        else:
            print("✗ 未配置任何网络搜索引擎\n")
            return False
    except Exception as e:
        print(f"查询失败: {e}\n")
        return False


def add_search_config(search_engine, api_key, api_url=None, extra_params=None, is_default=True):
    """添加搜索配置"""
    # 如果设为默认，先清除其他默认
    if is_default:
        dml_sql("UPDATE web_search_configs SET is_default = 0 WHERE is_default = 1")
    
    sql = """
        INSERT INTO web_search_configs 
        (search_engine, api_url, api_key, extra_params, is_default, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
    """
    now = datetime.now()
    extra_params_json = json.dumps(extra_params) if extra_params else None
    
    config_id, _ = dml_sql_with_insert_id(sql, (
        search_engine, api_url, api_key, extra_params_json, is_default, now, now
    ))
    print(f"✓ 搜索配置已添加，ID: {config_id}")
    return config_id


def print_usage():
    """打印使用说明"""
    print("""
=== 网络搜索配置说明 ===

支持的搜索引擎:
1. Google 自定义搜索
   - 需要: API Key + 自定义搜索引擎 ID (cx)
   - API URL: https://www.googleapis.com/customsearch/v1
   - 获取方式: https://developers.google.com/custom-search/v1/introduction

2. 百度搜索
   - 需要: API Key
   - 普通用户可能需要申请百度搜索 API

3. Bing 搜索
   - 需要: Bing API Key
   - 获取方式: https://www.microsoft.com/en-us/bing/apis/bing-web-search-api

4. 自定义搜索
   - 可以配置任意搜索 API

配置示例 (Google):
-----------------
from scripts.setup_web_search import add_search_config

add_search_config(
    search_engine='google',
    api_key='你的Google API Key',
    api_url='https://www.googleapis.com/customsearch/v1',
    extra_params={'cx': '你的搜索引擎ID'},
    is_default=True
)

配置示例 (Bing):
-----------------
add_search_config(
    search_engine='bing',
    api_key='你的Bing API Key',
    api_url='https://api.bing.microsoft.com/v7.0/search',
    is_default=True
)
""")


if __name__ == '__main__':
    has_config = check_web_search_config()
    if not has_config:
        print_usage()
