#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM模块初始化脚本
创建数据库表和初始化默认配置
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.db_config import dml_sql, query_sql, fetch_one


def create_tables():
    """创建LLM相关数据库表"""
    
    # 1. LLM配置表
    sql_llm_configs = """
    CREATE TABLE IF NOT EXISTS llm_configs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        config_name VARCHAR(100) NOT NULL COMMENT '配置名称',
        model_type VARCHAR(50) NOT NULL COMMENT '模型类型: openai/qianwen/wenxin/zhipu/deepseek/custom',
        api_base_url VARCHAR(500) COMMENT 'API基础URL',
        api_key VARCHAR(500) NOT NULL COMMENT 'API密钥',
        model_name VARCHAR(100) NOT NULL COMMENT '模型名称',
        max_tokens INT DEFAULT 2048 COMMENT '最大token数',
        temperature DECIMAL(3,2) DEFAULT 0.70 COMMENT '温度参数',
        is_default TINYINT(1) DEFAULT 0 COMMENT '是否默认配置',
        is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
        extra_params TEXT COMMENT '额外参数(JSON)',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_model_type (model_type),
        INDEX idx_is_default (is_default),
        INDEX idx_is_active (is_active)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM配置表';
    """
    
    # 2. 问答记录表
    sql_qa_records = """
    CREATE TABLE IF NOT EXISTS llm_qa_records (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL COMMENT '会话ID',
        question TEXT NOT NULL COMMENT '用户问题',
        answer TEXT COMMENT 'AI回答',
        source_type VARCHAR(50) COMMENT '来源类型: document/web/document_and_web/none',
        source_documents TEXT COMMENT '来源文档(JSON)',
        web_search_results TEXT COMMENT '网络搜索结果(JSON)',
        created_at DATETIME NOT NULL,
        INDEX idx_session_id (session_id),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM问答记录表';
    """
    
    # 3. 网络搜索配置表
    sql_search_configs = """
    CREATE TABLE IF NOT EXISTS web_search_configs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        search_engine VARCHAR(50) NOT NULL COMMENT '搜索引擎: google/baidu/bing/custom',
        api_url VARCHAR(500) COMMENT 'API URL',
        api_key VARCHAR(500) COMMENT 'API密钥',
        extra_params TEXT COMMENT '额外参数(JSON)',
        is_default TINYINT(1) DEFAULT 0 COMMENT '是否默认',
        is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_search_engine (search_engine),
        INDEX idx_is_default (is_default)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网络搜索配置表';
    """
    
    # 4. 问答会话表
    sql_qa_sessions = """
    CREATE TABLE IF NOT EXISTS document_qa_sessions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL COMMENT '用户ID',
        title VARCHAR(200) COMMENT '会话标题',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_user_id (user_id),
        INDEX idx_updated_at (updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档问答会话表';
    """
    
    # 5. 文档内容表（用于存储解析后的文档内容，便于搜索）
    sql_document_contents = """
    CREATE TABLE IF NOT EXISTS document_contents (
        id INT AUTO_INCREMENT PRIMARY KEY,
        document_id INT NOT NULL COMMENT '文档ID',
        section_title VARCHAR(500) COMMENT '章节标题',
        content TEXT COMMENT '内容',
        content_type VARCHAR(50) DEFAULT 'text' COMMENT '内容类型: text/table/image',
        page_number INT COMMENT '页码',
        sequence_order INT DEFAULT 0 COMMENT '顺序',
        created_at DATETIME NOT NULL,
        INDEX idx_document_id (document_id),
        FULLTEXT INDEX ft_content (content)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档内容表';
    """
    
    tables = [
        ('llm_configs', sql_llm_configs),
        ('llm_qa_records', sql_qa_records),
        ('web_search_configs', sql_search_configs),
        ('document_qa_sessions', sql_qa_sessions),
        ('document_contents', sql_document_contents)
    ]
    
    for table_name, sql in tables:
        try:
            dml_sql(sql)
            print(f"✓ 表 {table_name} 创建成功")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"○ 表 {table_name} 已存在")
            else:
                print(f"✗ 表 {table_name} 创建失败: {e}")


def init_default_configs():
    """初始化默认配置（可选）"""
    
    # 检查是否已有配置
    existing = fetch_one("SELECT COUNT(*) as cnt FROM llm_configs")
    if existing and existing.get('cnt', 0) > 0:
        print("○ LLM配置已存在，跳过初始化")
        return
    
    print("\n是否要初始化示例配置？(y/n): ", end='')
    choice = input().strip().lower()
    
    if choice != 'y':
        print("○ 跳过配置初始化")
        return
    
    # 示例配置（需要用户填入真实的API Key）
    from datetime import datetime
    now = datetime.now()
    
    sample_configs = [
        {
            'config_name': 'OpenAI GPT-4',
            'model_type': 'openai',
            'api_base_url': 'https://api.openai.com/v1',
            'api_key': 'sk-your-api-key-here',
            'model_name': 'gpt-4',
            'max_tokens': 2048,
            'temperature': 0.7,
            'is_default': 1
        },
        {
            'config_name': '通义千问',
            'model_type': 'qianwen',
            'api_base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'api_key': 'sk-your-api-key-here',
            'model_name': 'qwen-plus',
            'max_tokens': 2048,
            'temperature': 0.7,
            'is_default': 0
        }
    ]
    
    for config in sample_configs:
        try:
            sql = """
                INSERT INTO llm_configs 
                (config_name, model_type, api_base_url, api_key, model_name, 
                 max_tokens, temperature, is_default, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
            """
            dml_sql(sql, (
                config['config_name'], config['model_type'], config['api_base_url'],
                config['api_key'], config['model_name'], config['max_tokens'],
                config['temperature'], config['is_default'], now, now
            ))
            print(f"✓ 示例配置 '{config['config_name']}' 创建成功")
        except Exception as e:
            print(f"✗ 示例配置创建失败: {e}")
    
    print("\n⚠ 请在系统中修改API Key为真实的密钥！")


def add_parsed_content_column():
    """为documents表添加parsed_content列（如果不存在）"""
    try:
        # 检查列是否存在
        check_sql = """
            SELECT COUNT(*) as cnt 
            FROM information_schema.columns 
            WHERE table_schema = DATABASE() 
            AND table_name = 'documents' 
            AND column_name = 'parsed_content'
        """
        result = fetch_one(check_sql)
        
        if result and result.get('cnt', 0) == 0:
            alter_sql = """
                ALTER TABLE documents 
                ADD COLUMN parsed_content LONGTEXT COMMENT '解析后的文档内容'
            """
            dml_sql(alter_sql)
            print("✓ documents表添加parsed_content列成功")
        else:
            print("○ documents表parsed_content列已存在")
    except Exception as e:
        print(f"✗ 添加parsed_content列失败: {e}")


def main():
    print("=" * 50)
    print("LLM模块初始化脚本")
    print("=" * 50)
    print()
    
    print("1. 创建数据库表...")
    create_tables()
    
    print("\n2. 检查documents表结构...")
    add_parsed_content_column()
    
    print("\n3. 初始化默认配置...")
    init_default_configs()
    
    print("\n" + "=" * 50)
    print("初始化完成！")
    print("=" * 50)
    print("\n后续步骤：")
    print("1. 在系统中配置真实的LLM API Key")
    print("2. 配置网络搜索引擎（可选）")
    print("3. 访问 /llm 页面开始使用智能问答功能")


if __name__ == '__main__':
    main()
