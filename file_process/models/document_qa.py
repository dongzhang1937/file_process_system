"""
文档问答处理模块
实现从已上传文档搜索内容，结合网络搜索，调用LLM生成回答
"""
import json
from datetime import datetime
from config.db_config import dml_sql, query_sql, fetch_one, dml_sql_with_insert_id
from config.logging_config import logger
from .llm_service import LLMService, get_llm_service
from .llm_config import LLMConfigManager
from .web_search import WebSearchService


class DocumentQAService:
    """文档问答服务"""
    
    # 相关性阈值
    RELEVANCE_THRESHOLD = 0.3
    
    def __init__(self, llm_config_id=None):
        """
        初始化问答服务
        
        Args:
            llm_config_id: LLM配置ID，为None则使用默认配置
        """
        self.llm_service = get_llm_service(llm_config_id)
        self.web_search_service = WebSearchService()
    
    def create_session(self, user_id, title=None):
        """
        创建问答会话
        
        Args:
            user_id: 用户ID
            title: 会话标题
        
        Returns:
            会话ID
        """
        sql = """
            INSERT INTO document_qa_sessions (user_id, title, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
        """
        now = datetime.now()
        title = title or f"新会话 {now.strftime('%Y-%m-%d %H:%M')}"
        session_id, _ = dml_sql_with_insert_id(sql, (user_id, title, now, now))
        return session_id
    
    def get_session(self, session_id):
        """获取会话信息"""
        sql = "SELECT * FROM document_qa_sessions WHERE id = %s"
        return fetch_one(sql, (session_id,))
    
    def list_sessions(self, user_id, limit=20, offset=0):
        """列出用户的会话"""
        sql = """
            SELECT * FROM document_qa_sessions 
            WHERE user_id = %s 
            ORDER BY updated_at DESC 
            LIMIT %s OFFSET %s
        """
        return query_sql(sql, (user_id, limit, offset))
    
    def delete_session(self, session_id):
        """删除会话及其记录"""
        # 删除问答记录
        dml_sql("DELETE FROM llm_qa_records WHERE session_id = %s", (session_id,))
        # 删除会话
        dml_sql("DELETE FROM document_qa_sessions WHERE id = %s", (session_id,))
        return True
    
    def process_question(self, session_id, question, user_id, 
                         document_ids=None, enable_web_search=True, 
                         custom_search_urls=None, stream=False):
        """
        处理用户问题
        
        Args:
            session_id: 会话ID
            question: 用户问题
            user_id: 用户ID
            document_ids: 指定搜索的文档ID列表（可选）
            enable_web_search: 是否启用网络搜索
            custom_search_urls: 自定义搜索网址列表
            stream: 是否流式输出
        
        Returns:
            如果stream=False: {'answer': '', 'source_type': '', 'sources': []}
            如果stream=True: 生成器
        """
        # 1. 从文档中搜索相关内容
        doc_results = self._search_documents(question, user_id, document_ids)
        
        source_type = 'document'
        web_results = []
        
        # 2. 判断是否需要网络搜索
        if not doc_results or self._need_web_search(doc_results, question):
            if enable_web_search:
                web_results = self.web_search_service.search(
                    question, 
                    num_results=5,
                    custom_urls=custom_search_urls
                )
                if web_results:
                    source_type = 'document_and_web' if doc_results else 'web'
        
        # 3. 构建上下文
        context = self._build_context(doc_results, web_results)
        
        # 4. 构建消息
        messages = self._build_messages(question, context, session_id)
        
        # 5. 调用LLM生成回答
        if stream:
            return self._stream_answer(session_id, question, messages, 
                                       source_type, doc_results, web_results)
        else:
            result = self.llm_service.chat_completion(messages, stream=False)
            answer = result['content']
            
            # 6. 保存问答记录
            self._save_qa_record(session_id, question, answer, source_type, 
                                doc_results, web_results)
            
            # 7. 更新会话时间
            self._update_session_time(session_id)
            
            return {
                'answer': answer,
                'source_type': source_type,
                'sources': {
                    'documents': doc_results,
                    'web': web_results
                }
            }
    
    def _search_documents(self, question, user_id, document_ids=None):
        """
        从已上传的文档中搜索相关内容
        
        Args:
            question: 用户问题
            user_id: 用户ID
            document_ids: 指定的文档ID列表
        
        Returns:
            相关文档内容列表
        """
        # 提取问题关键词
        keywords = self._extract_keywords(question)
        
        if not keywords:
            return []
        
        # 构建搜索条件
        conditions = ["user_id = %s"]
        params = [user_id]
        
        if document_ids:
            placeholders = ','.join(['%s'] * len(document_ids))
            conditions.append(f"id IN ({placeholders})")
            params.extend(document_ids)
        
        # 搜索文档内容（假设有document_contents表存储解析后的内容）
        # 这里使用简单的LIKE搜索，实际可以使用全文索引或向量搜索
        keyword_conditions = []
        for keyword in keywords[:5]:  # 限制关键词数量
            keyword_conditions.append("content LIKE %s")
            params.append(f"%{keyword}%")
        
        if keyword_conditions:
            conditions.append(f"({' OR '.join(keyword_conditions)})")
        
        sql = f"""
            SELECT dc.id, dc.document_id, dc.content, dc.section_title,
                   d.filename, d.original_filename
            FROM document_contents dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.user_id = %s AND d.status = 'completed'
            {"AND d.id IN (" + placeholders + ")" if document_ids else ""}
            AND ({' OR '.join(keyword_conditions) if keyword_conditions else '1=1'})
            LIMIT 10
        """
        
        try:
            results = query_sql(sql, params)
            return results
        except Exception as e:
            logger.warning(f"文档搜索失败，尝试简化搜索: {e}")
            # 如果document_contents表不存在，尝试从其他地方获取
            return self._fallback_document_search(question, user_id, document_ids)
    
    def _fallback_document_search(self, question, user_id, document_ids=None):
        """备用文档搜索方法"""
        # 从word_parser解析的内容中搜索
        try:
            sql = """
                SELECT id, filename, original_filename, parsed_content
                FROM documents 
                WHERE user_id = %s AND status = 'completed'
            """
            params = [user_id]
            
            if document_ids:
                placeholders = ','.join(['%s'] * len(document_ids))
                sql += f" AND id IN ({placeholders})"
                params.extend(document_ids)
            
            sql += " LIMIT 20"
            
            documents = query_sql(sql, params)
            
            keywords = self._extract_keywords(question)
            results = []
            
            for doc in documents:
                content = doc.get('parsed_content', '')
                if not content:
                    continue
                
                # 简单的关键词匹配
                score = sum(1 for kw in keywords if kw.lower() in content.lower())
                if score > 0:
                    # 提取相关段落
                    relevant_text = self._extract_relevant_paragraphs(content, keywords)
                    results.append({
                        'document_id': doc['id'],
                        'filename': doc.get('original_filename', doc.get('filename', '')),
                        'content': relevant_text,
                        'score': score
                    })
            
            # 按相关性排序
            results.sort(key=lambda x: x['score'], reverse=True)
            return results[:5]
            
        except Exception as e:
            logger.error(f"备用文档搜索也失败: {e}")
            return []
    
    def _extract_keywords(self, text):
        """提取关键词（简单实现）"""
        import re
        # 移除标点符号
        text = re.sub(r'[^\w\s]', ' ', text)
        # 分词
        words = text.split()
        # 过滤停用词和短词
        stopwords = {'的', '是', '在', '有', '和', '与', '了', '这', '那', '什么', 
                     '怎么', '如何', '为什么', 'the', 'is', 'are', 'what', 'how', 'why'}
        keywords = [w for w in words if len(w) > 1 and w.lower() not in stopwords]
        return keywords
    
    def _extract_relevant_paragraphs(self, content, keywords, max_length=1000):
        """提取包含关键词的相关段落"""
        paragraphs = content.split('\n')
        relevant = []
        total_length = 0
        
        for para in paragraphs:
            if any(kw.lower() in para.lower() for kw in keywords):
                if total_length + len(para) <= max_length:
                    relevant.append(para)
                    total_length += len(para)
                else:
                    break
        
        return '\n'.join(relevant) if relevant else content[:max_length]
    
    def _need_web_search(self, doc_results, question):
        """判断是否需要网络搜索"""
        if not doc_results:
            return True
        
        # 如果文档结果较少或相关性不高，进行网络搜索
        if len(doc_results) < 2:
            return True
        
        # 检查是否有明确的时效性需求
        time_keywords = ['最新', '今天', '昨天', '本周', '本月', '最近', 
                        'latest', 'today', 'recent', 'current']
        if any(kw in question.lower() for kw in time_keywords):
            return True
        
        return False
    
    def _build_context(self, doc_results, web_results):
        """构建上下文"""
        context_parts = []
        
        if doc_results:
            context_parts.append("=== 文档内容 ===")
            for i, doc in enumerate(doc_results, 1):
                filename = doc.get('filename', doc.get('original_filename', '未知文档'))
                content = doc.get('content', '')
                context_parts.append(f"[文档{i}: {filename}]\n{content}\n")
        
        if web_results:
            context_parts.append("=== 网络搜索结果 ===")
            for i, result in enumerate(web_results, 1):
                context_parts.append(
                    f"[来源{i}: {result['title']}]\n"
                    f"URL: {result['url']}\n"
                    f"{result['snippet']}\n"
                )
        
        return '\n'.join(context_parts)
    
    def _build_messages(self, question, context, session_id):
        """构建消息列表"""
        # 获取历史对话
        history = self._get_conversation_history(session_id, limit=5)
        
        system_prompt = """你是一个智能问答助手。请根据提供的上下文信息回答用户问题。

回答要求：
1. 优先使用文档内容回答，确保答案准确
2. 如果文档内容不足，可以参考网络搜索结果
3. 如果无法从提供的信息中找到答案，请诚实说明
4. 回答要简洁明了，条理清晰
5. 如果引用了具体来源，请注明"""

        messages = [{'role': 'system', 'content': system_prompt}]
        
        # 添加历史对话
        for record in history:
            messages.append({'role': 'user', 'content': record['question']})
            messages.append({'role': 'assistant', 'content': record['answer']})
        
        # 添加当前问题
        user_message = f"上下文信息：\n{context}\n\n用户问题：{question}"
        messages.append({'role': 'user', 'content': user_message})
        
        return messages
    
    def _get_conversation_history(self, session_id, limit=5):
        """获取对话历史"""
        sql = """
            SELECT question, answer FROM llm_qa_records 
            WHERE session_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """
        results = query_sql(sql, (session_id, limit))
        return list(reversed(results))  # 按时间正序
    
    def _stream_answer(self, session_id, question, messages, 
                       source_type, doc_results, web_results):
        """流式生成回答"""
        full_answer = []
        
        for chunk in self.llm_service.chat_completion(messages, stream=True):
            full_answer.append(chunk)
            yield {
                'type': 'content',
                'content': chunk
            }
        
        # 保存完整回答
        answer = ''.join(full_answer)
        self._save_qa_record(session_id, question, answer, source_type, 
                            doc_results, web_results)
        self._update_session_time(session_id)
        
        # 发送完成信号
        yield {
            'type': 'done',
            'source_type': source_type,
            'sources': {
                'documents': doc_results,
                'web': web_results
            }
        }
    
    def _save_qa_record(self, session_id, question, answer, source_type, 
                        doc_results, web_results):
        """保存问答记录"""
        sql = """
            INSERT INTO llm_qa_records 
            (session_id, question, answer, source_type, source_documents, 
             web_search_results, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        source_docs = json.dumps(doc_results, ensure_ascii=False) if doc_results else None
        web_results_json = json.dumps(web_results, ensure_ascii=False) if web_results else None
        
        dml_sql(sql, (
            session_id, question, answer, source_type,
            source_docs, web_results_json, datetime.now()
        ))
    
    def _update_session_time(self, session_id):
        """更新会话时间"""
        sql = "UPDATE document_qa_sessions SET updated_at = %s WHERE id = %s"
        dml_sql(sql, (datetime.now(), session_id))
    
    def get_qa_history(self, session_id, limit=50, offset=0):
        """获取问答历史"""
        sql = """
            SELECT * FROM llm_qa_records 
            WHERE session_id = %s 
            ORDER BY created_at ASC 
            LIMIT %s OFFSET %s
        """
        results = query_sql(sql, (session_id, limit, offset))
        
        for r in results:
            if r.get('source_documents'):
                r['source_documents'] = json.loads(r['source_documents'])
            if r.get('web_search_results'):
                r['web_search_results'] = json.loads(r['web_search_results'])
        
        return results


def get_document_qa_service(llm_config_id=None):
    """获取文档问答服务实例"""
    return DocumentQAService(llm_config_id)
