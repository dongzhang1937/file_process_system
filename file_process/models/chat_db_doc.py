"""
文档对话模块 - 支持精准匹配和LLM匹配
"""
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, session, send_file
from config.db_config import fetch_one, fetch_all
from config.logging_config import logger

chatdoc = Blueprint('chatdoc', __name__)


@chatdoc.route('/chatdoc', methods=['GET', 'POST'])
def chat_page():
    """渲染文档对话页面"""
    return render_template('chat_doc.html')


@chatdoc.route('/api/chat/documents', methods=['GET'])
def get_available_documents():
    """获取可用于查询的文档列表"""
    try:
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'
        
        sql = """
            SELECT doc_id, filename, status, created_at
            FROM doc_process_records
            WHERE username = %s AND status = 'completed'
            ORDER BY created_at DESC
        """
        documents = fetch_all(sql, (username,))
        
        return jsonify({
            'success': True,
            'data': documents
        })
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/llm-search', methods=['POST'])
def llm_search():
    """
    LLM智能匹配搜索
    
    支持单条查询，先在文档中精确匹配，匹配不上则语义匹配，都不行则网络搜索
    """
    try:
        from .requirement_analyzer import get_requirement_analyzer
        from .llm_config import LLMConfigManager
        
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'
        
        data = request.json
        query = data.get('query', '').strip()
        document_ids = data.get('document_ids', [])
        enable_web_search = data.get('enable_web_search', True)
        llm_config_id = data.get('llm_config_id')
        
        if not query:
            return jsonify({
                'success': False,
                'error': '查询内容不能为空'
            }), 400
        
        # 检查LLM配置
        if llm_config_id:
            config = LLMConfigManager.get_config(llm_config_id)
        else:
            config = LLMConfigManager.get_default_config(username=username)
        
        if not config:
            return jsonify({
                'success': False,
                'error': '未配置LLM，请先在设置中配置大模型'
            }), 400
        
        # 创建分析器并执行分析
        analyzer = get_requirement_analyzer(llm_config_id, username=username)
        enable_sql_validation = data.get('enable_sql_validation', True)
        sql_db_types = data.get('sql_db_types', None)
        result = analyzer.analyze_requirement(
            query, 
            username, 
            document_ids if document_ids else None,
            enable_web_search=enable_web_search,
            enable_sql_validation=enable_sql_validation,
            sql_db_types=sql_db_types
        )
        
        # 调试日志: 确认 process_logs 是否在结果中
        process_logs = result.get('process_logs')
        process_logs_count = len(process_logs) if isinstance(process_logs, list) else 0
        has_pl = process_logs_count > 0
        logger.info(
            f"[单条查询结果] match_type={result.get('match_type')}, "
            f"has_process_logs={has_pl}, process_logs_count={process_logs_count}"
        )
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        logger.error(f"LLM搜索失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/analyze-file', methods=['POST'])
def analyze_uploaded_file():
    """
    分析上传的需求文件
    
    支持上传 .docx, .txt 或 .pdf 文件，解析其中的需求并逐条分析。
    TXT文件支持多级编号层级结构解析，返回完整的需求树和叶子节点。
    """
    try:
        from .requirement_analyzer import get_requirement_analyzer
        from .llm_config import LLMConfigManager
        
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'
        
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': '未上传文件'
            }), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '未选择文件'
            }), 400
        
        # 检查文件类型
        allowed_extensions = {'.docx', '.txt', '.pdf'}
        filename = file.filename or ''
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'error': f'不支持的文件格式，仅支持: {", ".join(allowed_extensions)}'
            }), 400
        
        # 获取其他参数
        enable_sql_validation = request.form.get('enable_sql_validation', 'true').lower() == 'true'
        llm_config_id = request.form.get('llm_config_id')
        section_filter = request.form.get('section_filter')  # 章节过滤，如 "1.4.1,1.4.2"
        use_llm = request.form.get('use_llm', 'false').lower() == 'true'  # 是否使用LLM智能识别章节
        
        if llm_config_id:
            llm_config_id = int(llm_config_id)
        
        # 解析章节过滤参数
        section_filter_list = None
        if section_filter:
            section_filter_list = [s.strip() for s in section_filter.replace('、', ',').split(',') if s.strip()]
        
        # 检查LLM配置
        if llm_config_id:
            config = LLMConfigManager.get_config(llm_config_id)
        else:
            config = LLMConfigManager.get_default_config(username=username)
        
        if not config:
            return jsonify({
                'success': False,
                'error': '未配置LLM，请先在设置中配置大模型'
            }), 400
        
        # 保存上传的文件到临时目录
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"req_upload_{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}")
        file.save(temp_path)
        
        try:
            # 创建分析器
            analyzer = get_requirement_analyzer(llm_config_id, username=username)
            
            # 解析需求（应用章节过滤，可选使用LLM智能识别章节）
            requirements = analyzer.parse_requirements_from_file(
                temp_path, 
                section_filter=section_filter_list,
                use_llm=use_llm
            )
            
            if not requirements:
                error_msg = '未能从文件中解析出需求'
                if section_filter_list:
                    error_msg += f'（过滤章节: {", ".join(section_filter_list)}）'
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 400
            
            # 构建响应数据
            response_data = {
                'requirements': requirements,
                'count': len(requirements),
                'temp_file': temp_path,
                'filename': file.filename,
                'section_filter': section_filter_list,
                'enable_sql_validation': enable_sql_validation
            }
            
            # TXT文件额外返回完整的树结构
            if ext == '.txt':
                try:
                    tree_data = analyzer.parse_txt_as_tree(temp_path)
                    response_data['tree_structure'] = tree_data
                except Exception as e:
                    logger.warning(f"获取树结构失败: {e}")
            
            # 返回解析出的需求，让前端确认后再分析
            return jsonify({
                'success': True,
                'data': response_data
            })
            
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
        
    except Exception as e:
        logger.error(f"分析上传文件失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 后台任务模式 API ====================

@chatdoc.route('/api/chat/task/submit', methods=['POST'])
def submit_analysis_task():
    """
    提交批量分析后台任务
    任务在服务端后台线程中执行，前端可刷新/关闭页面后恢复查看进度
    """
    try:
        from .analysis_tasks import AnalysisTaskManager
        from flask import current_app

        data = request.json
        requirements = data.get('requirements', [])
        if not requirements:
            return jsonify({'success': False, 'error': '需求列表为空'}), 400

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        # 检查是否已有活跃任务
        active = AnalysisTaskManager.get_active_task(username)
        if active:
            return jsonify({
                'success': False,
                'error': '您已有一个正在执行的任务，请等待完成或取消后再提交',
                'active_task': active
            }), 409

        params = {
            'document_ids': data.get('document_ids', []),
            'enable_web_search': data.get('enable_web_search', True),
            'enable_sql_validation': data.get('enable_sql_validation', True),
            'sql_db_types': data.get('sql_db_types'),
            'llm_config_id': data.get('llm_config_id'),
            'temp_file': data.get('temp_file')
        }

        # 创建任务记录
        task_id = AnalysisTaskManager.create_task(username, requirements, params)

        # 启动后台线程（传入 Flask app 实例以获取 app context）
        app_getter = getattr(current_app, '_get_current_object', None)
        flask_app = app_getter() if callable(app_getter) else current_app
        AnalysisTaskManager.start_task(task_id, flask_app)

        return jsonify({
            'success': True,
            'data': {
                'task_id': task_id,
                'total': len(requirements),
                'status': 'running'
            },
            'message': '任务已提交，后台开始处理'
        })
    except Exception as e:
        logger.error(f"提交分析任务失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@chatdoc.route('/api/chat/task/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    """
    查询任务进度（轻量接口，前端 2 秒轮询一次）
    返回: status, total, current, current_title 等
    """
    try:
        from .analysis_tasks import AnalysisTaskManager
        status = AnalysisTaskManager.get_task_status(task_id)
        if not status:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@chatdoc.route('/api/chat/task/<task_id>/results', methods=['GET'])
def get_task_results(task_id):
    """
    获取任务完整结果（含 results_json 和 summary_json）
    前端在任务完成后调用一次，渲染最终结果
    """
    try:
        from .analysis_tasks import AnalysisTaskManager
        task = AnalysisTaskManager.get_task_results(task_id)
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        return jsonify({
            'success': True,
            'data': {
                'status': task.get('status'),
                'total': task.get('total'),
                'current': task.get('current'),
                'results': task.get('results_json', []),
                'summary': task.get('summary_json', {}),
                'error': task.get('error')
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@chatdoc.route('/api/chat/task/<task_id>/cancel', methods=['POST'])
def cancel_analysis_task(task_id):
    """取消正在执行的任务"""
    try:
        from .analysis_tasks import AnalysisTaskManager
        task = AnalysisTaskManager.get_task_status(task_id)
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        if task['status'] not in ('pending', 'running'):
            return jsonify({'success': False, 'error': f'任务状态为 {task["status"]}，无法取消'}), 400

        AnalysisTaskManager.cancel_task(task_id)
        return jsonify({'success': True, 'message': '任务已取消'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@chatdoc.route('/api/chat/task/active', methods=['GET'])
def get_active_task():
    """
    检查当前用户是否有活跃任务（pending/running）
    前端页面加载时调用，如果有则恢复显示进度
    """
    try:
        from .analysis_tasks import AnalysisTaskManager

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        active = AnalysisTaskManager.get_active_task(username)
        return jsonify({
            'success': True,
            'data': active  # None if no active task
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@chatdoc.route('/api/chat/export-llm-results', methods=['POST'])
def export_llm_results():
    """
    导出LLM分析结果为Word文档
    
    支持层级结构输出和SQL验证结果表格
    """
    try:
        from .requirement_analyzer import get_requirement_analyzer
        
        data = request.json
        results = data.get('results', [])
        title = data.get('title', '需求分析报告')
        requirement_tree = data.get('requirement_tree')  # 需求树结构（可选）
        format_config = data.get('format_config')  # 格式配置（预留）
        
        if not results:
            return jsonify({
                'success': False,
                'error': '没有可导出的结果'
            }), 400
        
        # 创建分析器并导出
        analyzer = get_requirement_analyzer()
        filepath, filename = analyzer.export_to_word(
            results, title,
            requirement_tree=requirement_tree,
            format_config=format_config
        )
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except Exception as e:
        logger.error(f"导出LLM结果失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500




# ==================== 招标文档智能应答API ====================

@chatdoc.route('/api/chat/parse-bid-instruction', methods=['POST'])
def parse_bid_instruction():
    """
    解析用户的招标作答指令
    
    请求参数:
        instruction: 用户指令，如 "针对文档中的1.4.1,1.4.2作答"
        doc_id: 文档ID（可选，用于从数据库获取已解析的章节）
        file_path: 文档路径（可选，用于直接解析文件）
    
    返回:
        解析出的章节编号和对应的技术要求
    """
    try:
        from .bid_document_parser import UserInstructionParser, BidResponseGenerator
        
        data = request.json
        instruction = data.get('instruction', '').strip()
        doc_id = data.get('doc_id')
        
        if not instruction:
            return jsonify({
                'success': False,
                'error': '请输入作答指令'
            }), 400
        
        # 解析用户指令
        parser = UserInstructionParser()
        instruction_info = parser.parse_instruction(instruction)
        
        if not instruction_info['parsed']:
            return jsonify({
                'success': False,
                'error': '无法解析指令，请使用格式如："针对文档中的1.4.1,1.4.2作答"',
                'instruction_info': instruction_info
            })
        
        # 如果提供了doc_id，尝试获取章节详情
        sections = {}
        if doc_id:
            generator = BidResponseGenerator()
            result = generator.process_instruction(instruction, doc_id=doc_id)
            if result['success']:
                sections = result['sections']
        
        return jsonify({
            'success': True,
            'data': {
                'instruction_info': instruction_info,
                'section_numbers': instruction_info['section_numbers'],
                'sections': sections
            }
        })
        
    except Exception as e:
        logger.error(f"解析招标指令失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/get-section-requirements', methods=['POST'])
def get_section_requirements():
    """
    获取指定章节的技术要求列表
    
    请求参数:
        doc_id: 文档ID（必需）
        section_numbers: 章节编号列表，如 ['1.4.1', '1.4.2']
    
    返回:
        各章节的技术要求详情（解析每一条具体要求）
    """
    try:
        from .bid_document_parser import BidDocumentParser
        
        data = request.json
        doc_id = data.get('doc_id')
        section_numbers = data.get('section_numbers', [])
        
        if not doc_id:
            return jsonify({
                'success': False,
                'error': '请提供文档ID'
            }), 400
        
        if not section_numbers:
            return jsonify({
                'success': False,
                'error': '请提供章节编号'
            }), 400
        
        # 获取文档信息
        sql = """
            SELECT dpr.final_path, dpr.filename
            FROM doc_process_records dpr
            WHERE dpr.doc_id = %s AND dpr.status = 'completed'
        """
        doc_info = fetch_one(sql, (doc_id,))
        
        if not doc_info:
            return jsonify({
                'success': False,
                'error': '文档不存在或未处理完成'
            }), 404
        
        file_path = doc_info['final_path']
        
        # 检查文件是否存在
        import os
        if not file_path or not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': f'文档文件不存在: {file_path}'
            }), 404
        
        # 【核心修改】直接解析文档文件，而不是从数据库查
        logger.info(f"解析文档: {file_path}")
        parser = BidDocumentParser(file_path)
        parser.parse_document_structure()
        
        # 打印解析到的所有章节编号
        all_section_numbers = list(parser.section_index.keys())
        logger.info(f"文档解析到的章节编号: {all_section_numbers}")
        
        sections_data = {}
        total_requirements = 0
        missing_sections = []
        
        for num in section_numbers:
            logger.info(f"查找章节 {num}...")
            
            # 从解析结果中查找章节
            section = parser.get_section_by_number(num)
            
            if section:
                logger.info(f"章节 {num} 找到: title={section.get('title', '')}, requirements={len(section.get('requirements', []))}")
                
                # 使用 BidDocumentParser 的方法获取所有需求
                requirements = parser.get_all_requirements_from_section(num)
                
                logger.info(f"章节 {num} 获取到 {len(requirements)} 条需求")
                
                sections_data[num] = {
                    'number': num,
                    'title': section.get('title', ''),
                    'content': section.get('content', ''),
                    'requirements': requirements,
                    'tables': section.get('tables', []),
                    'requirements_count': len(requirements)
                }
                total_requirements += len(requirements)
            else:
                logger.warning(f"章节 {num} 在文档中未找到，可用章节: {all_section_numbers}")
                missing_sections.append(num)
        
        return jsonify({
            'success': True,
            'data': {
                'doc_id': doc_id,
                'filename': doc_info['filename'],
                'sections': sections_data,
                'total_requirements': total_requirements,
                'found_sections': list(sections_data.keys()),
                'missing_sections': missing_sections,
                'available_sections': all_section_numbers  # 返回所有可用章节供调试
            }
        })
        
    except Exception as e:
        logger.error(f"获取章节需求失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/answer-bid-requirements', methods=['POST'])
def answer_bid_requirements():
    """
    对招标文档的技术要求进行智能作答
    
    请求参数:
        doc_id: 招标文档ID（必需）
        section_numbers: 要作答的章节编号列表
        knowledge_doc_ids: 知识库文档ID列表（用于匹配答案）
        llm_config_id: LLM配置ID（可选）
        enable_web_search: 是否启用网络搜索（默认True）
        export_format: 导出格式 'json' | 'word' | 'word_table'（默认json）
    
    返回:
        各技术要求的作答结果（对每一条具体要求分别作答）
    """
    try:
        from .bid_document_parser import BidDocumentParser, BidAnswerGenerator
        import os
        
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'
        
        data = request.json
        doc_id = data.get('doc_id')
        section_numbers = data.get('section_numbers', [])
        raw_knowledge_doc_ids = data.get('knowledge_doc_ids', [])
        knowledge_doc_ids = []
        if isinstance(raw_knowledge_doc_ids, list):
            for item in raw_knowledge_doc_ids:
                try:
                    knowledge_doc_ids.append(int(item))
                except (TypeError, ValueError):
                    continue
        llm_config_id = data.get('llm_config_id')
        enable_web_search = data.get('enable_web_search', True)
        export_format = data.get('export_format', 'json')
        
        if not doc_id:
            return jsonify({
                'success': False,
                'error': '请提供文档ID'
            }), 400
        
        if not section_numbers:
            return jsonify({
                'success': False,
                'error': '请提供要作答的章节编号'
            }), 400
        
        # 获取文档路径
        sql = """
            SELECT dpr.final_path, dpr.filename
            FROM doc_process_records dpr
            WHERE dpr.doc_id = %s AND dpr.status = 'completed'
        """
        doc_info = fetch_one(sql, (doc_id,))
        
        if not doc_info or not doc_info['final_path']:
            return jsonify({
                'success': False,
                'error': '文档不存在或未处理完成'
            }), 404
        
        file_path = doc_info['final_path']
        
        # 检查文件是否存在
        if not file_path or not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': f'文档文件不存在: {file_path}'
            }), 404
        
        # 【核心修改】直接解析文档文件
        logger.info(f"answer_bid_requirements - 解析文档: {file_path}")
        parser = BidDocumentParser(file_path)
        parser.parse_document_structure()
        
        all_section_numbers = list(parser.section_index.keys())
        logger.info(f"文档解析到的章节编号: {all_section_numbers}")
        
        all_requirements = []
        
        for num in section_numbers:
            logger.info(f"从文档获取章节 {num}...")
            
            # 使用 BidDocumentParser 获取章节的所有需求
            requirements = parser.get_all_requirements_from_section(num)
            
            if requirements:
                logger.info(f"章节 {num} 获取到 {len(requirements)} 条需求")
                for req in requirements:
                    all_requirements.append({
                        'section_number': num,
                        'section_title': req.get('section_title', ''),
                        'index': req.get('index', ''),
                        'content': req.get('text', ''),
                        'spec': req.get('spec', ''),
                        'type': req.get('type', 'list')
                    })
            else:
                logger.warning(f"章节 {num} 未找到，可用章节: {all_section_numbers}")
        
        logger.info(f"从文档获取到 {len(all_requirements)} 条需求")
        
        if not all_requirements:
            return jsonify({
                'success': False,
                'error': f'未找到需要作答的技术要求，可用章节: {all_section_numbers}'
            }), 400
        
        logger.info(f"开始处理 {len(all_requirements)} 条技术要求")
        
        # 使用新的作答生成器，对每一条要求分别执行匹配
        generator = BidAnswerGenerator(llm_config_id)
        results = generator.answer_requirements(
            all_requirements,
            username,
            knowledge_doc_ids,
            enable_web_search
        )
        
        # 统计
        summary = {
            'total': len(results),
            'exact': sum(1 for r in results if r['match_type'] == 'exact'),
            'semantic': sum(1 for r in results if r['match_type'] == 'semantic'),
            'web': sum(1 for r in results if r['match_type'] == 'web'),
            'llm_generated': sum(1 for r in results if r['match_type'] == 'llm_generated'),
            'none': sum(1 for r in results if r['match_type'] in ['none', 'error'])
        }
        
        # 如果需要导出Word
        if export_format in ['word', 'word_table']:
            bid_doc_info = {'filename': doc_info['filename'], 'doc_id': doc_id}
            format_type = 'table' if export_format == 'word_table' else 'default'
            filepath, filename = generator.export_to_word(
                results, 
                title='招标技术要求应答书',
                bid_doc_info=bid_doc_info
            ) if format_type == 'default' else generator.export_to_word_table_format(
                results,
                title='招标技术要求应答表',
                bid_doc_info=bid_doc_info
            )
            
            return send_file(
                filepath,
                as_attachment=True,
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        
        return jsonify({
            'success': True,
            'data': {
                'results': results,
                'summary': summary,
                'doc_info': {
                    'doc_id': doc_id,
                    'filename': doc_info['filename']
                }
            }
        })
        
    except Exception as e:
        logger.error(f"招标需求作答失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/export-bid-answers', methods=['POST'])
def export_bid_answers():
    """
    导出招标作答结果为Word文档
    
    请求参数:
        results: 作答结果列表
        title: 文档标题
        doc_info: 文档信息
        format_type: 格式类型 'default' | 'table'
    """
    try:
        from .bid_document_parser import BidAnswerGenerator
        
        data = request.json
        results = data.get('results', [])
        title = data.get('title', '招标技术要求应答书')
        doc_info = data.get('doc_info')
        format_type = data.get('format_type', 'default')
        
        if not results:
            return jsonify({
                'success': False,
                'error': '没有可导出的结果'
            }), 400
        
        generator = BidAnswerGenerator()
        
        if format_type == 'table':
            filepath, filename = generator.export_to_word_table_format(results, title, doc_info)
        else:
            filepath, filename = generator.export_to_word(results, title, doc_info)
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except Exception as e:
        logger.error(f"导出招标作答失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

