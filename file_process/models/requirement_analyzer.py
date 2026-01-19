"""
需求分析服务模块
实现从上传文件中提取需求，并进行智能匹配和解答
"""
import os
import re
import json
import tempfile
from datetime import datetime
from docx import Document
from difflib import SequenceMatcher
from flask import Blueprint, request, jsonify, session, send_file
from config.db_config import fetch_one, fetch_all, dml_sql, dml_sql_with_insert_id, query_sql
from config.logging_config import logger
from .llm_service import LLMService, get_llm_service
from .llm_config import LLMConfigManager
from .web_search import WebSearchService


class RequirementAnalyzer:
    """需求分析器"""
    
    # 相似度阈值
    EXACT_MATCH_THRESHOLD = 0.95  # 精确匹配阈值
    FUZZY_MATCH_THRESHOLD = 0.6   # 模糊匹配阈值
    SEMANTIC_MATCH_THRESHOLD = 0.5  # 语义匹配阈值
    
    def __init__(self, llm_config_id=None):
        """
        初始化需求分析器
        
        Args:
            llm_config_id: LLM配置ID，为None则使用默认配置
        """
        self.llm_config_id = llm_config_id
        self.llm_service = None
        self.web_search_service = WebSearchService()
    
    def _get_llm_service(self):
        """延迟加载LLM服务"""
        if self.llm_service is None:
            try:
                self.llm_service = get_llm_service(self.llm_config_id)
            except Exception as e:
                logger.warning(f"LLM服务初始化失败: {e}")
                return None
        return self.llm_service
    
    def parse_requirements_from_file(self, file_path, section_filter=None):
        """
        从文件中解析需求列表
        
        Args:
            file_path: 文件路径（支持 .docx, .txt）
            section_filter: 章节过滤列表，如 ['1.4.1', '1.4.2']，为None则解析所有章节
        
        Returns:
            需求列表 [{'index': 1, 'content': '需求内容', 'title': '需求标题', 'section': {...}}, ...]
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.docx':
            return self._parse_docx_requirements(file_path, section_filter)
        elif ext == '.txt':
            return self._parse_txt_requirements(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
    
    def _parse_docx_requirements(self, file_path, section_filter=None):
        """
        解析Word文档中的需求
        
        支持三种格式：
        1. 编号列表格式：1. 要求内容  2. 要求内容
        2. 表格格式：序号 | 技术要求 | 技术规格
        3. 纯段落格式：无编号的段落文本，每个段落视为一条需求
        
        Args:
            file_path: 文档路径
            section_filter: 章节过滤列表，如 ['1.4.1', '1.4.2']，为None则解析所有章节
        """
        requirements = []
        doc = Document(file_path)
        
        current_section = None  # 当前章节
        current_requirement = None
        index = 0
        pending_paragraphs = []  # 收集章节内的纯段落文本
        
        # 辅助函数：检查当前章节是否在过滤列表中
        def is_section_allowed(section):
            if section_filter is None:
                return True
            if section is None:
                return False
            section_num = section.get('number', '')
            # 检查是否完全匹配或是子章节
            for allowed in section_filter:
                if section_num == allowed or section_num.startswith(allowed + '.'):
                    return True
            return False
        
        # 标记是否曾经进入过允许的章节
        has_entered_allowed_section = False
        # 标记是否刚解析完表格（用于检测表格后的隐式章节边界）
        just_finished_table = False
        
        for element in self._iter_block_items(doc):
            if hasattr(element, 'text'):
                # 段落
                text = element.text.strip()
                if not text:
                    continue
                
                # 检测是否是章节标题
                # 支持格式：1.4.1 xxx, 一、xxx, 二、xxx, (一)xxx, 第一章 xxx 等
                # 先清理文本中的特殊空白字符
                clean_text = re.sub(r'[\t\u3000]+', ' ', text)  # 将tab和全角空格替换为普通空格
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()  # 合并多个空白
                
                section_match = re.match(r'^(\d+(?:\.\d+)+)\s*(.+)', clean_text)
                # 中文数字章节标题（如 "一、文档交付要求", "（一）总体要求"）
                # 必须有明确的分隔符：、 ） ) ． . 或空格
                # 避免误匹配"一个"、"一种"等普通文本
                chinese_section_match = re.match(
                    r'^[（(]?([一二三四五六七八九十百]+)[）)、．.][ \t]*(.+)', clean_text
                ) if not section_match else None
                # "第X章/节/部分" 格式
                chapter_match = re.match(
                    r'^第([一二三四五六七八九十百\d]+)[章节部分条款]\s*(.+)', clean_text
                ) if not section_match and not chinese_section_match else None
                
                # 【关键逻辑】表格后的隐式章节边界检测
                # 如果刚解析完表格，遇到一个短段落（不是编号需求也不是章节标题），
                # 很可能是新的章节标题（如"文档交付要求"），将current_section设为None
                implicit_section_break = False
                if just_finished_table and not section_match and not chinese_section_match and not chapter_match:
                    is_req_item = self._is_requirement_item(text)
                    # 短文本（<=20字）且不是需求项 -> 可能是隐式章节标题
                    if len(clean_text) <= 20 and not is_req_item:
                        implicit_section_break = True
                        logger.info(f"[隐式章节边界] 表格后遇到短段落: '{clean_text}'")
                        # 保存之前的需求
                        if current_requirement and is_section_allowed(current_section):
                            requirements.append(current_requirement)
                        current_requirement = None
                        pending_paragraphs = []
                        # 设置为未知章节（不在过滤列表中）
                        current_section = {
                            'number': '',
                            'title': clean_text
                        }
                        just_finished_table = False
                        continue
                
                # 重置表格后状态
                just_finished_table = False
                
                if section_match or chinese_section_match or chapter_match:
                    # 保存之前的需求（如果章节允许）
                    if current_requirement and is_section_allowed(current_section):
                        requirements.append(current_requirement)
                    current_requirement = None
                    
                    # 处理上一章节收集的纯段落（如果没有编号需求且章节允许）
                    if pending_paragraphs and current_section and is_section_allowed(current_section):
                        para_reqs = self._process_pending_paragraphs(pending_paragraphs, current_section, index)
                        for req in para_reqs:
                            index += 1
                            req['index'] = index
                            requirements.append(req)
                    pending_paragraphs = []
                    
                    # 根据不同匹配类型设置章节信息
                    if section_match:
                        # 阿拉伯数字格式: 1.4.1 xxx
                        current_section = {
                            'number': section_match.group(1),
                            'title': section_match.group(2).strip()
                        }
                    elif chinese_section_match:
                        # 中文数字格式: 一、xxx 或 （一）xxx
                        chinese_num = chinese_section_match.group(1)
                        current_section = {
                            'number': chinese_num,  # 保留中文数字
                            'title': chinese_section_match.group(2).strip()
                        }
                    elif chapter_match:
                        # "第X章" 格式
                        chapter_num = chapter_match.group(1)
                        current_section = {
                            'number': chapter_num,
                            'title': chapter_match.group(2).strip()
                        }
                    
                    # 检查是否进入/离开了允许的章节
                    if is_section_allowed(current_section):
                        has_entered_allowed_section = True
                    elif has_entered_allowed_section:
                        # 曾经在允许的章节中，现在离开了 -> 可以提前结束（优化性能）
                        # 但不强制退出，因为可能后面还有其他允许的章节
                        pass
                    
                    continue
                
                # 检测是否是新的需求项（不是章节标题）
                is_new_requirement = self._is_requirement_item(text)
                
                if is_new_requirement:
                    # 有编号需求时，清空pending_paragraphs（它们可能是引导语）
                    pending_paragraphs = []
                    
                    # 保存之前的需求（如果章节允许）
                    if current_requirement and is_section_allowed(current_section):
                        requirements.append(current_requirement)
                    
                    # 只有当前章节允许时才创建新需求
                    if is_section_allowed(current_section):
                        index += 1
                        # 提取需求编号和内容
                        req_index, req_content = self._extract_requirement_content(text)
                        current_requirement = {
                            'index': index,
                            'req_index': req_index,
                            'title': req_content[:50] + '...' if len(req_content) > 50 else req_content,
                            'content': req_content,
                            'raw_text': text,
                            'section': current_section.copy() if current_section else None,
                            'type': 'list'
                        }
                    else:
                        current_requirement = None
                elif current_requirement:
                    # 追加到当前需求的内容（多行需求）
                    current_requirement['content'] += '\n' + text
                else:
                    # 【新增】收集无编号的段落，可能是纯段落格式的需求
                    if current_section and len(text) >= 20 and is_section_allowed(current_section):
                        pending_paragraphs.append(text)
            
            elif hasattr(element, 'rows'):
                # 表格
                # 遇到表格时，清空pending_paragraphs（表格前的内容可能是引导语）
                pending_paragraphs = []
                
                # 解析表格，表格内部会自行处理章节过滤
                # 同时返回检测到的新章节（如果有）
                table_reqs, new_section = self._parse_table_requirements(element, current_section, section_filter)
                for req in table_reqs:
                    index += 1
                    req['index'] = index
                    requirements.append(req)
                
                # 如果表格内检测到新的章节（如"二、文档交付要求"），更新current_section
                if new_section:
                    # 先保存之前的需求
                    if current_requirement and is_section_allowed(current_section):
                        requirements.append(current_requirement)
                    current_requirement = None
                    current_section = new_section
                else:
                    # 保存之前的需求（如果章节允许）
                    if current_requirement and is_section_allowed(current_section):
                        requirements.append(current_requirement)
                    current_requirement = None
                
                # 标记刚解析完表格，用于后续隐式章节边界检测
                just_finished_table = True
        
        # 添加最后一个需求
        if current_requirement and is_section_allowed(current_section):
            requirements.append(current_requirement)
        
        # 处理最后一个章节的pending_paragraphs
        if pending_paragraphs and current_section and is_section_allowed(current_section):
            para_reqs = self._process_pending_paragraphs(pending_paragraphs, current_section, index)
            for req in para_reqs:
                index += 1
                req['index'] = index
                requirements.append(req)
        
        return requirements
    
    def _process_pending_paragraphs(self, paragraphs, section, start_index):
        """
        处理收集的纯段落文本，将其转换为需求项
        
        Args:
            paragraphs: 段落文本列表
            section: 当前章节信息
            start_index: 起始索引
        
        Returns:
            需求列表
        """
        if not paragraphs:
            return []
        
        requirements = []
        
        # 过滤掉引导性语句
        skip_patterns = [
            r'.*需要满足以下要求.*',
            r'.*如下要求.*',
            r'.*具体要求.*',
            r'.*满足如下.*',
        ]
        
        for i, text in enumerate(paragraphs):
            # 检查是否是引导语（跳过）
            is_intro = False
            for pattern in skip_patterns:
                if re.match(pattern, text):
                    is_intro = True
                    break
            
            if is_intro:
                continue
            
            # 跳过太短的段落
            if len(text) < 20:
                continue
            
            requirements.append({
                'index': 0,  # 稍后设置
                'req_index': str(len(requirements) + 1),
                'title': text[:50] + '...' if len(text) > 50 else text,
                'content': text,
                'raw_text': text,
                'section': section.copy() if section else None,
                'type': 'paragraph'
            })
        
        return requirements
    
    def _iter_block_items(self, doc):
        """按文档流顺序遍历段落与表格"""
        from docx.document import Document as DocxDocument
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        
        parent_elm = doc.element.body
        
        for child in parent_elm.iterchildren():
            if child.tag.endswith("}p"):
                yield Paragraph(child, doc)
            elif child.tag.endswith("}tbl"):
                yield Table(child, doc)
    
    def _is_requirement_item(self, text):
        """判断是否是需求项（而非章节标题）"""
        # 排除章节标题格式（如 1.4.1 xxx）
        if re.match(r'^\d+\.\d+', text):
            return False
        
        # 常见的需求编号格式
        patterns = [
            r'^(\d+)[\.、\)]\s+',           # 1. 或 1、或 1) 后面有内容
            r'^[（\(](\d+)[）\)]\s*',        # (1) 或 （1）
            r'^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])\s*',  # 圆圈数字
            r'^[★▲●○◆]\s*',                 # 特殊符号开头
        ]
        
        for pattern in patterns:
            if re.match(pattern, text):
                return True
        
        return False
    
    def _extract_requirement_content(self, text):
        """从需求文本中提取编号和内容"""
        patterns = [
            r'^(\d+)[\.、\)]\s*(.+)',        # 1. xxx 或 1、xxx 或 1) xxx
            r'^[（\(](\d+)[）\)]\s*(.+)',    # (1) xxx 或 （1）xxx
            r'^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])\s*(.+)',  # ① xxx
            r'^[★▲●○◆]\s*(.+)',              # ★ xxx
        ]
        
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    return groups[0], groups[1]
                elif len(groups) == 1:
                    return '', groups[0]
        
        return '', text
    
    def _parse_table_requirements(self, table, current_section, section_filter=None):
        """
        从表格中解析需求
        
        Args:
            table: 表格对象
            current_section: 当前章节信息
            section_filter: 章节过滤列表
            
        Returns:
            tuple: (requirements列表, 检测到的新章节或None)
        """
        requirements = []
        detected_new_section = None  # 用于返回检测到的新章节
        
        if not table.rows:
            return requirements, detected_new_section
        
        # 获取表头
        headers = []
        header_row = table.rows[0]
        for cell in header_row.cells:
            cell_text = '\n'.join(p.text.strip() for p in cell.paragraphs if p.text.strip())
            headers.append(cell_text)
        
        # 识别是否是需求表格
        header_keywords = ['序号', '技术要求', '技术规格', '功能要求', '参数', '指标', '规格', '要求']
        is_requirement_table = any(kw in ''.join(headers) for kw in header_keywords)
        
        if not is_requirement_table:
            return requirements, detected_new_section
        
        # 识别列映射
        header_map = {'index': None, 'requirement': None, 'spec': None, 'section': None}
        
        for i, h in enumerate(headers):
            h_clean = h.strip()
            if h_clean in ['序号', '编号', '项', 'No', 'No.', '#']:
                header_map['index'] = i
            elif any(kw in h_clean for kw in ['技术要求', '功能要求', '要求', '功能', '项目', '名称']):
                header_map['requirement'] = i
            elif any(kw in h_clean for kw in ['技术规格', '规格', '参数', '参数值', '指标']):
                header_map['spec'] = i
            # 检测章节列（如"章节"、"条款"等）
            elif any(kw in h_clean for kw in ['章节', '条款', '节号', '条目']):
                header_map['section'] = i
        
        # 如果没有找到明确的要求列，使用启发式方法
        if header_map['requirement'] is None and len(headers) >= 2:
            header_map['requirement'] = 1 if header_map['index'] == 0 else 0
        if header_map['spec'] is None and len(headers) >= 3:
            for i in range(len(headers)):
                if i != header_map['index'] and i != header_map['requirement']:
                    header_map['spec'] = i
                    break
        
        # 辅助函数：检查章节是否允许
        def is_section_allowed_for_row(row_section):
            if section_filter is None:
                return True
            if row_section is None:
                return False
            section_num = row_section.get('number', '')
            for allowed in section_filter:
                if section_num == allowed or section_num.startswith(allowed + '.'):
                    return True
            return False
        
        # 跟踪表格内的当前章节（用于合并单元格的情况）
        table_current_section = current_section.copy() if current_section else None
        
        # 预扫描表格，检测是否有章节分隔行
        # 如果表格第一行的要求文本包含章节编号，可能整个表格跨越多章节
        has_section_markers = False
        for row in table.rows[1:]:
            cells_text = []
            for cell in row.cells:
                cell_text = '\n'.join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                cells_text.append(cell_text)
            all_text = ' '.join(cells_text)
            if re.search(r'^\d+\.\d+(?:\.\d+)*\s', all_text):
                has_section_markers = True
                break
        
        # 解析数据行
        for row_idx, row in enumerate(table.rows[1:], start=1):
            row_data = {}
            all_cells_text = []  # 收集所有单元格文本用于章节检测
            for col_idx, cell in enumerate(row.cells):
                cell_text = '\n'.join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                header = headers[col_idx] if col_idx < len(headers) else f'col_{col_idx}'
                row_data[header] = cell_text
                all_cells_text.append(cell_text)
            
            # 提取字段
            req_index = ''
            if header_map['index'] is not None:
                idx_key = headers[header_map['index']]
                req_index = row_data.get(idx_key, str(row_idx))
            else:
                req_index = str(row_idx)
            
            req_text = ''
            if header_map['requirement'] is not None:
                req_key = headers[header_map['requirement']]
                req_text = row_data.get(req_key, '')
            
            spec_text = ''
            if header_map['spec'] is not None:
                spec_key = headers[header_map['spec']]
                spec_text = row_data.get(spec_key, '')
            
            # 清理特殊字符
            req_index = str(req_index).replace('↵', '').replace('←', '').strip()
            req_text = req_text.replace('↵', '\n').replace('←', '').strip()
            spec_text = spec_text.replace('↵', '\n').replace('←', '').strip()
            
            # 检查行内是否有章节编号（可能在序号列、要求列或专门的章节列）
            row_section = table_current_section
            is_section_header_row = False  # 标记是否是章节标题行
            
            # 尝试从序号列检测章节（如 "1.4.1" 或 "1.4.2-1"）
            section_match = re.match(r'^(\d+(?:\.\d+)+)', req_index)
            if section_match:
                detected_section_num = section_match.group(1)
                # 只有在检测到至少2级章节时才认为是章节编号（如1.4, 1.4.1等）
                if detected_section_num.count('.') >= 1:
                    row_section = {
                        'number': detected_section_num,
                        'title': ''
                    }
                    table_current_section = row_section
            
            # 尝试从要求文本开头检测章节（如 "1.4.1 xxx要求：..."）
            if not section_match and req_text:
                text_section_match = re.match(r'^(\d+(?:\.\d+)+)\s+(.*)$', req_text)
                if text_section_match:
                    detected_section_num = text_section_match.group(1)
                    remaining_text = text_section_match.group(2).strip()
                    # 只有在检测到至少2级章节时才更新
                    if detected_section_num.count('.') >= 1:
                        row_section = {
                            'number': detected_section_num,
                            'title': remaining_text[:50] if remaining_text else ''
                        }
                        table_current_section = row_section
                        # 如果这是纯章节标题行（如"1.4.2 国产中间件技术要求"），跳过不作为需求
                        if len(remaining_text) < 50 and not spec_text:
                            is_section_header_row = True
            
            # 检查整行文本是否是章节标题（合并单元格的情况）
            if not section_match:
                full_row_text = ' '.join(all_cells_text).strip()
                # 清理特殊空白字符
                clean_full_row = re.sub(r'[\t\u3000]+', ' ', full_row_text)
                clean_full_row = re.sub(r'\s+', ' ', clean_full_row).strip()
                
                full_row_match = re.match(r'^(\d+(?:\.\d+)+)\s+(.*)$', clean_full_row)
                if full_row_match:
                    detected_section_num = full_row_match.group(1)
                    remaining_text = full_row_match.group(2).strip()
                    if detected_section_num.count('.') >= 1:
                        row_section = {
                            'number': detected_section_num,
                            'title': remaining_text[:50] if remaining_text else ''
                        }
                        table_current_section = row_section
                        # 如果行内没有具体的技术规格，可能是章节分隔行
                        if len(remaining_text) < 80 and not spec_text:
                            is_section_header_row = True
                
                # 【新增】检查是否是中文数字章节标题（如"二、文档交付要求"）
                if not full_row_match:
                    chinese_section_match = re.match(
                        r'^[（(]?([一二三四五六七八九十百]+)[）)、．.][ \t]*(.+)', clean_full_row
                    )
                    if chinese_section_match:
                        chinese_num = chinese_section_match.group(1)
                        section_title = chinese_section_match.group(2).strip()
                        # 这是一个新的主章节，需要返回给调用者
                        detected_new_section = {
                            'number': chinese_num,
                            'title': section_title
                        }
                        # 【关键】更新表格内的当前章节，后续行将使用新章节
                        table_current_section = detected_new_section
                        row_section = detected_new_section
                        is_section_header_row = True
                        logger.info(f"[表格内检测到中文章节] {chinese_num} {section_title}")
            
            # 跳过章节标题行
            if is_section_header_row:
                continue
            
            # 检查章节过滤
            if section_filter and not is_section_allowed_for_row(row_section):
                continue
            
            if req_text or spec_text:
                # 组合技术要求和技术规格作为完整内容
                full_content = req_text
                if spec_text:
                    full_content += f"\n【技术规格】{spec_text}"
                
                requirements.append({
                    'index': 0,  # 稍后设置
                    'req_index': req_index,
                    'title': req_text[:50] + '...' if len(req_text) > 50 else req_text,
                    'content': full_content,
                    'raw_text': f"{req_text} | {spec_text}",
                    'section': row_section.copy() if row_section else None,
                    'type': 'table',
                    'spec': spec_text
                })
        
        return requirements, detected_new_section
    
    def _parse_txt_requirements(self, file_path):
        """解析TXT文件中的需求（每行一个）"""
        requirements = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        index = 0
        for line in lines:
            text = line.strip()
            if not text:
                continue
            
            # 跳过章节标题
            if re.match(r'^\d+\.\d+', text):
                continue
            
            index += 1
            req_index, content = self._extract_requirement_content(text)
            requirements.append({
                'index': index,
                'req_index': req_index,
                'title': content[:50] + '...' if len(content) > 50 else content,
                'content': content,
                'raw_text': text,
                'type': 'list'
            })
        
        return requirements
    
    def _is_requirement_start(self, text):
        """判断是否是需求项的开始（保留兼容性）"""
        return self._is_requirement_item(text)
    
    def _extract_title_content(self, text):
        """从文本中提取标题和内容（保留兼容性）"""
        req_index, content = self._extract_requirement_content(text)
        title = content[:50] + '...' if len(content) > 50 else content
        return title, content
    
    def analyze_requirement(self, requirement, user_id, document_ids=None, enable_web_search=True):
        """
        分析单个需求并生成答案
        
        流程：
        1. 先在已上传文档中精确匹配
        2. 匹配不上则进行语义相似度匹配
        3. 都匹配不上则从网上搜索
        
        Args:
            requirement: 需求内容（字符串或字典）
            user_id: 用户ID
            document_ids: 指定搜索的文档ID列表
            enable_web_search: 是否启用网络搜索
        
        Returns:
            {
                'requirement': '原始需求',
                'answer': '回答内容',
                'match_type': 'exact/semantic/web/none',
                'source': {'type': 'document/web', 'details': {...}},
                'confidence': 0.95
            }
        """
        # 处理输入
        if isinstance(requirement, dict):
            req_content = requirement.get('content', requirement.get('title', ''))
            req_title = requirement.get('title', '')
        else:
            req_content = str(requirement)
            req_title = req_content[:50] if len(req_content) > 50 else req_content
        
        result = {
            'requirement': req_content,
            'requirement_title': req_title,
            'answer': None,
            'match_type': 'none',
            'source': None,
            'confidence': 0
        }
        
        # 1. 精确匹配
        exact_match = self._exact_match_in_documents(req_title, req_content, user_id, document_ids)
        if exact_match:
            content = exact_match['content']
            result['answer'] = content
            result['match_type'] = 'exact'
            # 获取图片：优先从内容提取，其次从章节关联
            images = self._get_images_from_content(content)
            if not images:
                images = self._get_chapter_images(exact_match.get('chapter_id'))
            result['source'] = {
                'type': 'document',
                'filename': exact_match.get('filename', ''),
                'chapter_id': exact_match.get('chapter_id'),
                'chapter_title': exact_match.get('chapter_title', ''),
                'path': exact_match.get('path', []),
                'images': images
            }
            result['confidence'] = exact_match.get('similarity', 1.0)
            return result
        
        # 2. 语义相似度匹配（使用LLM）
        semantic_match = self._semantic_match_in_documents(req_content, user_id, document_ids)
        if semantic_match:
            content = semantic_match['content']
            result['answer'] = content
            result['match_type'] = 'semantic'
            # 获取图片：优先从内容提取，其次从章节关联
            images = self._get_images_from_content(content)
            if not images:
                images = self._get_chapter_images(semantic_match.get('chapter_id'))
            result['source'] = {
                'type': 'document',
                'filename': semantic_match.get('filename', ''),
                'chapter_id': semantic_match.get('chapter_id'),
                'chapter_title': semantic_match.get('chapter_title', ''),
                'path': semantic_match.get('path', []),
                'images': images
            }
            result['confidence'] = semantic_match.get('similarity', 0.7)
            return result
        
        # 3. 网络搜索
        if enable_web_search:
            web_result = self._search_from_web(req_content)
            if web_result:
                result['answer'] = web_result['answer']
                result['match_type'] = 'web'
                result['source'] = {
                    'type': 'web',
                    'search_results': web_result.get('sources', [])
                }
                result['confidence'] = 0.5
                return result
        
        # 4. 都没匹配上，使用LLM直接回答
        llm_answer = self._generate_llm_answer(req_content)
        if llm_answer:
            result['answer'] = llm_answer
            result['match_type'] = 'llm_generated'
            result['source'] = {'type': 'llm'}
            result['confidence'] = 0.3
        else:
            result['answer'] = '抱歉，未能找到相关答案。'
            result['match_type'] = 'none'
            result['confidence'] = 0
        
        return result
    
    def _exact_match_in_documents(self, title, content, user_id, document_ids=None):
        """在文档中进行精确匹配"""
        # 构建查询条件
        conditions = ["dpr.username = %s", "dpr.status = 'completed'"]
        params = [user_id]
        
        if document_ids:
            placeholders = ','.join(['%s'] * len(document_ids))
            conditions.append(f"c.document_id IN ({placeholders})")
            params.extend(document_ids)
        
        # 先尝试标题精确匹配
        sql = f"""
            SELECT c.id as chapter_id, c.document_id, c.title as chapter_title, 
                   c.content, c.level, c.parent_id,
                   dpr.filename
            FROM chapters c
            JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
            WHERE {' AND '.join(conditions)}
            AND c.title = %s
            LIMIT 5
        """
        params_with_title = params + [title]
        
        results = fetch_all(sql, params_with_title)
        
        if results:
            best_match = results[0]
            # 获取章节路径
            path = self._get_chapter_path(best_match['chapter_id'])
            best_match['path'] = path
            best_match['similarity'] = 1.0
            return best_match
        
        # 尝试内容模糊匹配
        search_term = self._clean_text(title)[:30]  # 取前30个字符搜索
        
        sql = f"""
            SELECT c.id as chapter_id, c.document_id, c.title as chapter_title, 
                   c.content, c.level, c.parent_id,
                   dpr.filename
            FROM chapters c
            JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
            WHERE {' AND '.join(conditions)}
            AND (c.title LIKE %s OR c.content LIKE %s)
            LIMIT 20
        """
        params_with_like = params + [f'%{search_term}%', f'%{search_term}%']
        
        results = fetch_all(sql, params_with_like)
        
        if results:
            # 计算相似度并排序
            best_match = None
            best_similarity = 0
            
            for r in results:
                # 计算标题相似度
                title_sim = SequenceMatcher(None, 
                    self._clean_text(title), 
                    self._clean_text(r['chapter_title'] or '')
                ).ratio()
                
                # 计算内容相似度
                content_sim = SequenceMatcher(None,
                    self._clean_text(content)[:200],
                    self._clean_text(r['content'] or '')[:200]
                ).ratio()
                
                similarity = max(title_sim, content_sim * 0.8)
                
                if similarity > best_similarity and similarity >= self.FUZZY_MATCH_THRESHOLD:
                    best_similarity = similarity
                    best_match = r
                    best_match['similarity'] = similarity
            
            if best_match:
                path = self._get_chapter_path(best_match['chapter_id'])
                best_match['path'] = path
                return best_match
        
        return None
    
    def _semantic_match_in_documents(self, content, user_id, document_ids=None):
        """
        使用向量相似度进行语义匹配
        
        优先使用 embedding 向量搜索，如果向量搜索失败则回退到 LLM 方式
        """
        # 1. 尝试向量搜索
        vector_result = self._vector_search_match(content, user_id, document_ids)
        if vector_result:
            return vector_result
        
        # 2. 回退到 LLM 方式
        return self._llm_semantic_match(content, user_id, document_ids)
    
    def _vector_search_match(self, content, user_id, document_ids=None):
        """使用向量搜索进行语义匹配"""
        try:
            from .embedding_service import get_vector_store
            
            vector_store = get_vector_store()
            
            # 获取用户有权访问的文档ID
            if not document_ids:
                sql = """
                    SELECT doc_id FROM doc_process_records 
                    WHERE username = %s AND status = 'completed'
                """
                docs = fetch_all(sql, (user_id,))
                document_ids = [d['doc_id'] for d in docs] if docs else []
            
            if not document_ids:
                return None
            
            # 向量搜索
            results = vector_store.search_similar(
                query=content,
                document_ids=document_ids,
                top_k=5,
                threshold=self.SEMANTIC_MATCH_THRESHOLD
            )
            
            if not results:
                return None
            
            # 取最佳匹配
            best = results[0]
            
            # 获取章节详细信息
            chapter_sql = """
                SELECT c.id as chapter_id, c.document_id, c.title as chapter_title,
                       c.content, c.level, dpr.filename
                FROM chapters c
                JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
                WHERE c.id = %s
            """
            chapter = fetch_one(chapter_sql, (best['chapter_id'],))
            
            if chapter:
                chapter['similarity'] = best['similarity']
                chapter['path'] = self._get_chapter_path(chapter['chapter_id'])
                chapter['match_method'] = 'vector'  # 标记匹配方式
                logger.info(f"向量搜索匹配成功: similarity={best['similarity']:.3f}")
                return chapter
            
        except Exception as e:
            logger.warning(f"向量搜索失败，回退到LLM方式: {e}")
        
        return None
    
    def _llm_semantic_match(self, content, user_id, document_ids=None):
        """使用LLM进行语义相似度匹配（备用方案）"""
        llm = self._get_llm_service()
        if not llm:
            return None
        
        # 获取候选章节
        conditions = ["dpr.username = %s", "dpr.status = 'completed'"]
        params = [user_id]
        
        if document_ids:
            placeholders = ','.join(['%s'] * len(document_ids))
            conditions.append(f"c.document_id IN ({placeholders})")
            params.extend(document_ids)
        
        sql = f"""
            SELECT c.id as chapter_id, c.document_id, c.title as chapter_title, 
                   c.content, c.level,
                   dpr.filename
            FROM chapters c
            JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
            WHERE {' AND '.join(conditions)}
            AND c.content IS NOT NULL AND c.content != ''
            LIMIT 50
        """
        
        candidates = fetch_all(sql, params)
        
        if not candidates:
            return None
        
        # 构建提示词让LLM评估相似度
        candidate_texts = []
        for i, c in enumerate(candidates):
            title = c.get('chapter_title', '(无标题)')
            text = c.get('content', '')[:300]  # 限制长度
            candidate_texts.append(f"[{i+1}] 标题: {title}\n内容: {text}")
        
        candidates_str = '\n\n'.join(candidate_texts)
        
        prompt = f"""请分析以下需求与候选文档内容的相关性，找出最相关的内容。

需求内容：
{content}

候选文档内容：
{candidates_str}

请返回JSON格式的结果：
{{"best_match_index": 序号（1-{len(candidates)}，如果没有相关内容返回0）, "relevance_score": 0-1的相关性分数, "reason": "判断理由"}}

只返回JSON，不要其他内容。"""

        try:
            result = llm.chat_completion([
                {'role': 'system', 'content': '你是一个文档匹配助手，负责分析需求与文档内容的相关性。'},
                {'role': 'user', 'content': prompt}
            ])
            
            response_text = result['content']
            # 提取JSON
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                match_result = json.loads(json_match.group())
                best_idx = match_result.get('best_match_index', 0)
                score = match_result.get('relevance_score', 0)
                
                if best_idx > 0 and score >= self.SEMANTIC_MATCH_THRESHOLD:
                    best_match = candidates[best_idx - 1]
                    best_match['similarity'] = score
                    best_match['match_method'] = 'llm'  # 标记匹配方式
                    path = self._get_chapter_path(best_match['chapter_id'])
                    best_match['path'] = path
                    return best_match
        except Exception as e:
            logger.error(f"LLM语义匹配失败: {e}")
        
        return None
    
    def _search_from_web(self, content):
        """从网络搜索答案"""
        if not self.web_search_service.config:
            return None
        
        try:
            # 提取关键词进行搜索
            search_query = self._extract_search_keywords(content)
            
            results = self.web_search_service.search(search_query, num_results=5)
            
            if not results:
                return None
            
            # 使用LLM整合搜索结果生成答案
            llm = self._get_llm_service()
            if llm:
                context = '\n\n'.join([
                    f"[{r['title']}]\n{r['snippet']}\n来源: {r['url']}"
                    for r in results
                ])
                
                prompt = f"""根据以下搜索结果，回答用户的需求：

需求：{content}

搜索结果：
{context}

请提供简洁准确的回答："""
                
                try:
                    result = llm.chat_completion([
                        {'role': 'system', 'content': '你是一个专业的技术顾问，根据搜索结果回答用户问题。'},
                        {'role': 'user', 'content': prompt}
                    ])
                    
                    return {
                        'answer': result['content'],
                        'sources': results
                    }
                except Exception as e:
                    logger.error(f"LLM生成答案失败: {e}")
            
            # 如果LLM不可用，返回搜索结果摘要
            summary = '\n'.join([f"- {r['title']}: {r['snippet']}" for r in results[:3]])
            return {
                'answer': f"根据网络搜索结果：\n{summary}",
                'sources': results
            }
            
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return None
    
    def _generate_llm_answer(self, content):
        """使用LLM直接生成答案"""
        llm = self._get_llm_service()
        if not llm:
            return None
        
        try:
            result = llm.chat_completion([
                {'role': 'system', 'content': '你是一个专业的技术顾问，请根据你的知识回答用户的需求。如果不确定，请说明。'},
                {'role': 'user', 'content': f"请回答以下需求：\n{content}"}
            ])
            return result['content']
        except Exception as e:
            logger.error(f"LLM回答生成失败: {e}")
            return None
    
    def _clean_text(self, text):
        """清理文本用于匹配"""
        if not text:
            return ""
        # 去掉标点符号和特殊字符
        cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
        return cleaned.lower()
    
    def _extract_search_keywords(self, text):
        """提取搜索关键词"""
        # 简单实现：去掉停用词
        stopwords = {'的', '是', '在', '有', '和', '与', '了', '这', '那', '什么', 
                     '怎么', '如何', '为什么', '需要', '要求', '功能', '支持'}
        words = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', text)
        keywords = [w for w in words if w not in stopwords and len(w) > 1]
        return ' '.join(keywords[:10])  # 取前10个关键词
    
    def _get_chapter_path(self, chapter_id):
        """获取章节的完整路径"""
        path = []
        current_id = chapter_id
        
        while current_id:
            sql = """
                SELECT id, parent_id, level, title
                FROM chapters
                WHERE id = %s
            """
            chapter = fetch_one(sql, (current_id,))
            if chapter:
                path.insert(0, {
                    'id': chapter['id'],
                    'level': chapter['level'],
                    'title': chapter['title']
                })
                current_id = chapter['parent_id']
            else:
                break
        
        return path
    
    def _get_images_from_content(self, content):
        """从内容中提取图片ID并获取图片信息
        
        内容中可能包含 {{IMAGE_ID_xxx}} 格式的占位符，
        需要提取这些ID并从数据库获取对应的图片信息
        """
        if not content:
            return []
        
        # 提取所有图片ID
        image_ids = re.findall(r'\{\{IMAGE_ID_(\d+)\}\}', content)
        if not image_ids:
            return []
        
        # 去重
        image_ids = list(set(image_ids))
        
        try:
            placeholders = ','.join(['%s'] * len(image_ids))
            sql = f"""
                SELECT id, image_url, image_path
                FROM document_images
                WHERE id IN ({placeholders})
            """
            images = fetch_all(sql, image_ids)
            return [
                {
                    'id': img['id'],
                    'image_url': img.get('image_url') or img.get('image_path', '')
                }
                for img in (images or [])
            ]
        except Exception as e:
            logger.warning(f"从内容获取图片失败: {e}")
            return []
    
    def _get_chapter_images(self, chapter_id):
        """获取章节关联的图片"""
        if not chapter_id:
            return []
        
        try:
            sql = """
                SELECT di.id, di.image_url, di.image_path
                FROM document_images di
                JOIN chapter_images ci ON di.id = ci.image_id
                WHERE ci.chapter_id = %s
                ORDER BY ci.position_in_chapter
            """
            images = fetch_all(sql, (chapter_id,))
            return [
                {
                    'id': img['id'],
                    'image_url': img.get('image_url') or img.get('image_path', '')
                }
                for img in (images or [])
            ]
        except Exception as e:
            logger.warning(f"获取章节图片失败: {e}")
            return []
    
    def analyze_requirements_batch(self, requirements, user_id, document_ids=None, 
                                   enable_web_search=True, progress_callback=None):
        """
        批量分析需求
        
        Args:
            requirements: 需求列表
            user_id: 用户ID
            document_ids: 文档ID列表
            enable_web_search: 是否启用网络搜索
            progress_callback: 进度回调函数 callback(current, total, result)
        
        Returns:
            分析结果列表
        """
        results = []
        total = len(requirements)
        
        for i, req in enumerate(requirements):
            try:
                result = self.analyze_requirement(
                    req, user_id, document_ids, enable_web_search
                )
                result['index'] = i + 1
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, total, result)
                    
            except Exception as e:
                logger.error(f"分析需求 {i+1} 失败: {e}")
                results.append({
                    'index': i + 1,
                    'requirement': req.get('content', str(req)) if isinstance(req, dict) else str(req),
                    'answer': f'分析失败: {str(e)}',
                    'match_type': 'error',
                    'confidence': 0
                })
        
        return results
    
    def export_to_word(self, results, title='需求分析报告'):
        """
        将分析结果导出为Word文档
        
        Args:
            results: 分析结果列表
            title: 文档标题
        
        Returns:
            临时文件路径
        """
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        
        doc = Document()
        
        # 添加标题
        heading = doc.add_heading(title, 0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 添加生成时间
        doc.add_paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph()
        
        # 添加统计信息
        total = len(results)
        exact_count = sum(1 for r in results if r.get('match_type') == 'exact')
        semantic_count = sum(1 for r in results if r.get('match_type') == 'semantic')
        web_count = sum(1 for r in results if r.get('match_type') == 'web')
        llm_count = sum(1 for r in results if r.get('match_type') == 'llm_generated')
        
        stats_para = doc.add_paragraph()
        stats_para.add_run(f"总计 {total} 条需求：").bold = True
        stats_para.add_run(f"\n• 精确匹配: {exact_count} 条")
        stats_para.add_run(f"\n• 语义匹配: {semantic_count} 条")
        stats_para.add_run(f"\n• 网络搜索: {web_count} 条")
        stats_para.add_run(f"\n• LLM生成: {llm_count} 条")
        
        doc.add_paragraph()
        
        # 添加每个需求的分析结果
        for result in results:
            index = result.get('index', 0)
            requirement = result.get('requirement', '')
            answer = result.get('answer', '无答案')
            match_type = result.get('match_type', 'none')
            confidence = result.get('confidence', 0)
            source = result.get('source', {})
            
            # 需求标题
            req_heading = doc.add_heading(f"需求 {index}", level=1)
            
            # 需求内容
            doc.add_paragraph().add_run("【需求内容】").bold = True
            doc.add_paragraph(requirement)
            
            # 匹配类型标签
            match_type_text = {
                'exact': '精确匹配',
                'semantic': '语义匹配',
                'web': '网络搜索',
                'llm_generated': 'LLM生成',
                'none': '未匹配',
                'error': '分析失败'
            }.get(match_type, '未知')
            
            type_para = doc.add_paragraph()
            type_run = type_para.add_run(f"【匹配类型】{match_type_text} (置信度: {confidence:.0%})")
            type_run.bold = True
            
            # 来源信息
            if source:
                source_type = source.get('type', '')
                if source_type == 'document':
                    path = source.get('path', [])
                    if path:
                        path_str = ' -> '.join([p.get('title', '') for p in path])
                        doc.add_paragraph(f"【来源路径】{path_str}")
                    doc.add_paragraph(f"【来源文件】{source.get('filename', '未知')}")
                elif source_type == 'web':
                    search_results = source.get('search_results', [])
                    if search_results:
                        doc.add_paragraph("【参考链接】")
                        for sr in search_results[:3]:
                            doc.add_paragraph(f"• {sr.get('title', '')}: {sr.get('url', '')}")
            
            # 答案内容
            doc.add_paragraph().add_run("【答案】").bold = True
            doc.add_paragraph(answer)
            
            # 分隔线
            doc.add_paragraph('─' * 50)
        
        # 保存到临时文件
        temp_dir = tempfile.gettempdir()
        filename = f"需求分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        filepath = os.path.join(temp_dir, filename)
        doc.save(filepath)
        
        return filepath, filename


def get_requirement_analyzer(llm_config_id=None):
    """获取需求分析器实例"""
    return RequirementAnalyzer(llm_config_id)
