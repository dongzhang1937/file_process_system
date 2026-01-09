import os
import re
from docx import Document as DocumentLoader
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from .celery_app import celery
from config.db_config import (
    dml_sql,
    query_sql,
    dml_sql_with_insert_id,
    close_db_connection,
)


class WordParser:
    """Word 解析器：按文档流顺序提取文字/图片/表格。

    - 章节：沿用原有“标题/Heading/大纲级别”识别逻辑
    - 内容：章节 content 内插入图片占位符 `{{IMAGE_ORDER_<n>}}`
    - 表格：转为可读的文本块（保留单元格内文字/图片顺序）
    """

    def __init__(self, file_path, username, doc_id, base_storage_path, base_url):
        self.file_path = file_path
        self.doc = DocumentLoader(file_path)

        # 物理路径隔离: /base_path/username/doc_id/
        self.storage_dir = os.path.join(base_storage_path, username, str(doc_id))
        os.makedirs(self.storage_dir, exist_ok=True)

        # URL 隔离: /base_url/username/doc_id/
        self.url_prefix = f"{base_url}/{username}/{doc_id}"

        # 图片命名前缀：原始文件名（去掉 .docx）
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        self.image_name_prefix = self._sanitize_filename(base_name)

        self.chapters = []
        self.images = []
        self._img_order_counter = 1

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """尽量保留可读性（含中文），但确保不会生成危险路径。"""
        if not name:
            return "document"
        name = name.replace("/", "_").replace("\\", "_")
        name = name.strip().strip(".")
        # 去掉控制字符
        name = re.sub(r"[\x00-\x1f]", "", name)
        return (name or "document")[:100]

    @staticmethod
    def _extract_plain_text_from_paragraph(para: Paragraph) -> str:
        parts = []
        for run in para.runs:
            if run.text:
                parts.append(run.text)
        return "".join(parts)

    def _get_paragraph_outline_level(self, para: Paragraph):
        """识别大纲层级 (核心逻辑保持不变)"""
        try:
            p_pr = para._element.pPr
            if p_pr is not None:
                outline_lvl = p_pr.find(qn("w:outlineLvl"))
                if outline_lvl is not None:
                    return int(outline_lvl.get(qn("w:val"))) + 1
        except Exception:
            pass

        style_name = getattr(para.style, "name", "")
        if any(h in style_name for h in ["Heading", "标题", "Title"]):
            match = re.search(r"(\d+)", style_name)
            return int(match.group(1)) if match else 1
        return None

    def _iter_block_items(self, parent):
        """按文档流顺序遍历段落与表格。

        参考 python-docx 官方示例：
        - parent 可以是 Document 或 _Cell
        """
        if isinstance(parent, DocxDocument):
            parent_elm = parent.element.body
            parent_obj = parent
        elif isinstance(parent, _Cell):
            parent_elm = parent._tc
            parent_obj = parent
        else:
            # fallback
            parent_elm = parent
            parent_obj = parent

        for child in parent_elm.iterchildren():
            if child.tag.endswith("}p"):
                yield Paragraph(child, parent_obj)
            elif child.tag.endswith("}tbl"):
                yield Table(child, parent_obj)

    @staticmethod
    def _extract_rids_from_elm(elm) -> list[str]:
        """从 drawing/pict 节点里提取图片 rId。"""
        r_ids: list[str] = []

        # a:blip @r:embed
        try:
            for blip in elm.xpath(".//*[local-name()='blip']"):
                rid = blip.get(qn("r:embed")) or blip.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                )
                if rid:
                    r_ids.append(rid)
        except Exception:
            pass

        # v:imagedata @r:id (旧式 pict)
        try:
            for imagedata in elm.xpath(".//*[local-name()='imagedata']"):
                rid = imagedata.get(qn("r:id")) or imagedata.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                if rid:
                    r_ids.append(rid)
        except Exception:
            pass

        return r_ids

    def _save_image_by_rid(self, r_id: str, doc_id: str, block_index: int):
        """落盘保存图片并返回图片元信息。"""
        image_part = self.doc.part.related_parts.get(r_id)
        if not image_part:
            return None

        ext = image_part.content_type.split("/")[-1]
        order_in_doc = self._img_order_counter
        self._img_order_counter += 1

        img_name = f"{self.image_name_prefix}_{order_in_doc:04d}.{ext}"
        img_path = os.path.join(self.storage_dir, img_name)

        with open(img_path, "wb") as f:
            f.write(image_part.blob)

        return {
            "document_id": doc_id,
            "image_name": img_name,
            "image_path": img_path,
            "image_url": f"{self.url_prefix}/{img_name}",
            "image_type": ext,
            "paragraph_index": block_index,
            "order_in_doc": order_in_doc,
            "file_size": len(image_part.blob),
        }

    def _parse_run_children(self, run, doc_id: str, block_index: int, current_chapter: dict) -> list[str]:
        """按 run 的 XML 子节点顺序提取文字/换行/图片，解决图文混排顺序问题。"""
        out: list[str] = []

        for child in run._element.iterchildren():
            tag = child.tag

            # w:t
            if tag.endswith("}t"):
                if child.text:
                    out.append(child.text)
                continue

            # w:tab
            if tag.endswith("}tab"):
                out.append("\t")
                continue

            # w:br
            if tag.endswith("}br"):
                out.append("\n")
                continue

            # w:drawing / w:pict
            if tag.endswith("}drawing") or tag.endswith("}pict"):
                for r_id in self._extract_rids_from_elm(child):
                    img = self._save_image_by_rid(r_id, doc_id, block_index)
                    if not img:
                        continue

                    # 记录图片归属章节与章节内顺序
                    img["chapter_temp_id"] = current_chapter.get("temp_id")
                    pos = current_chapter.setdefault("_img_pos", 0)
                    img["position_in_chapter"] = pos
                    current_chapter["_img_pos"] = pos + 1

                    self.images.append(img)
                    out.append(f"{{{{IMAGE_ORDER_{img['order_in_doc']}}}}}")
                continue

        # 兜底：有些 run.text 可能没被 w:t 覆盖（极少）
        if not out and run.text:
            out.append(run.text)

        return out

    def _parse_paragraph_inline(self, para: Paragraph, doc_id: str, block_index: int, current_chapter: dict) -> str:
        fragments: list[str] = []
        for run in para.runs:
            fragments.extend(self._parse_run_children(run, doc_id, block_index, current_chapter))
        return "".join(fragments).strip()

    def _parse_cell(self, cell: _Cell, doc_id: str, block_index: int, current_chapter: dict) -> str:
        parts: list[str] = []
        for block in self._iter_block_items(cell):
            if isinstance(block, Paragraph):
                txt = self._parse_paragraph_inline(block, doc_id, block_index, current_chapter)
                if txt:
                    parts.append(txt)
            elif isinstance(block, Table):
                parts.append(self._parse_table(block, doc_id, block_index, current_chapter))
        return "\n".join(parts).strip()

    def _parse_table(self, table: Table, doc_id: str, block_index: int, current_chapter: dict) -> str:
        """把表格序列化成可读文本块，并解析单元格内的文字+图片。"""
        lines: list[str] = ["[表格]"]

        for row in table.rows:
            row_cells: list[str] = []
            for cell in row.cells:
                cell_text = self._parse_cell(cell, doc_id, block_index, current_chapter)
                # 表格单元格尽量收敛成单行，避免破坏表格行结构
                cell_text = re.sub(r"\s+", " ", cell_text).strip()
                row_cells.append(cell_text)

            lines.append("| " + " | ".join(row_cells) + " |")

        lines.append("[/表格]")
        return "\n".join(lines)

    def parse(self, doc_id: str):
        """执行流式解析：按 body 子元素顺序处理段落/表格。"""
        temp_id_counter = 0
        block_index = 0

        # 默认起始章节
        current_chapter = {
            "temp_id": 0,
            "level": 1,
            "title": "正文",
            "parent_temp_id": None,
            "content_list": [],
            "paragraph_index": 0,
            "style_name": "Normal",
            "is_bold": False,
            "font_size": None,
            "_img_pos": 0,
        }
        self.chapters = [current_chapter]
        parent_stack = [{"level": 0, "temp_id": None}]

        for block in self._iter_block_items(self.doc):
            if isinstance(block, Paragraph):
                level = self._get_paragraph_outline_level(block)

                # 标题段落：创建新章节
                if level is not None:
                    title_text = self._extract_plain_text_from_paragraph(block).strip()
                    if title_text:
                        temp_id_counter += 1
                        while parent_stack and parent_stack[-1]["level"] >= level:
                            parent_stack.pop()

                        parent_temp_id = parent_stack[-1]["temp_id"] if parent_stack else None
                        is_bold = any(run.bold for run in block.runs) if block.runs else False
                        f_size = (
                            block.runs[0].font.size.pt
                            if (block.runs and block.runs[0].font.size)
                            else None
                        )

                        current_chapter = {
                            "temp_id": temp_id_counter,
                            "level": level,
                            "title": title_text,
                            "parent_temp_id": parent_temp_id,
                            "content_list": [],
                            "paragraph_index": block_index,
                            "style_name": block.style.name,
                            "is_bold": is_bold,
                            "font_size": f_size,
                            "_img_pos": 0,
                        }
                        self.chapters.append(current_chapter)
                        parent_stack.append({"level": level, "temp_id": temp_id_counter})
                        block_index += 1
                        continue

                # 普通段落：按 run 子节点顺序拼接（含图片占位符）
                txt = self._parse_paragraph_inline(block, doc_id, block_index, current_chapter)
                if txt:
                    current_chapter["content_list"].append(txt)

                block_index += 1
                continue

            if isinstance(block, Table):
                table_text = self._parse_table(block, doc_id, block_index, current_chapter)
                if table_text:
                    current_chapter["content_list"].append(table_text)
                block_index += 1
                continue

        for c in self.chapters:
            c["content"] = "\n".join(c.get("content_list", [])).strip()

        return self.chapters, self.images


@celery.task(bind=True)
def process_word_task(self, doc_id, file_path, username):
    """兼容旧入口：仅供直接调用。"""
    # 配置基础路径 - 存储在 file_process/images 目录下
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    base_storage = os.path.join(current_dir, "images")  # file_process/images
    base_url = "/images"

    parser = WordParser(file_path, username, doc_id, base_storage, base_url)
    try:
        chapters, images = parser.parse(doc_id)
    except Exception as e:
        return {"status": "error", "msg": str(e)}

    # 2. 数据库操作逻辑（保持与 prodetail.py 一致的基本行为）
    try:
        dml_sql("DELETE FROM chapters WHERE document_id = %s", (doc_id,))
        dml_sql("DELETE FROM document_images WHERE document_id = %s", (doc_id,))
        dml_sql(
            """
            DELETE ci FROM chapter_images ci
            INNER JOIN chapters c ON ci.chapter_id = c.id
            WHERE c.document_id = %s
            """,
            (doc_id,),
        )

        temp_to_real_id = {None: None}

        for c in chapters:
            parent_db_id = temp_to_real_id.get(c["parent_temp_id"])
            count_res = query_sql(
                "SELECT COUNT(*) as count FROM chapters WHERE document_id = %s AND parent_id <=> %s",
                (doc_id, parent_db_id),
            )
            order_index = count_res[0]["count"] if count_res else 0

            chapter_sql = """
                INSERT INTO chapters (document_id, parent_id, level, order_index, title, content,
                                     style_name, font_size, is_bold, paragraph_index)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                doc_id,
                parent_db_id,
                c["level"],
                order_index,
                c["title"],
                c.get("content", ""),
                c.get("style_name"),
                c.get("font_size"),
                int(bool(c.get("is_bold"))),
                c.get("paragraph_index"),
            )
            new_id, _ = dml_sql_with_insert_id(chapter_sql, params)
            temp_to_real_id[c["temp_id"]] = new_id

        img_sql = """
            INSERT INTO document_images (document_id, image_name, image_path, image_url,
                                        image_type, paragraph_index, order_in_doc, file_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        order_to_image_id: dict[int, int] = {}
        for img in images:
            image_id, _ = dml_sql_with_insert_id(
                img_sql,
                (
                    doc_id,
                    img["image_name"],
                    img["image_path"],
                    img.get("image_url"),
                    img.get("image_type"),
                    img.get("paragraph_index"),
                    img.get("order_in_doc"),
                    img.get("file_size"),
                ),
            )
            if image_id:
                order_to_image_id[int(img["order_in_doc"])] = int(image_id)

                chapter_db_id = temp_to_real_id.get(img.get("chapter_temp_id"))
                if chapter_db_id:
                    dml_sql(
                        """
                        INSERT INTO chapter_images (chapter_id, image_id, position_in_chapter)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            chapter_db_id,
                            image_id,
                            int(img.get("position_in_chapter", 0)),
                        ),
                    )

        # 将章节 content 的 IMAGE_ORDER 占位符替换为 IMAGE_ID 占位符
        for c in chapters:
            chapter_db_id = temp_to_real_id.get(c["temp_id"])
            if not chapter_db_id:
                continue
            content = c.get("content", "") or ""
            if "{{IMAGE_ORDER_" not in content:
                continue

            def _repl(m):
                order = int(m.group(1))
                image_id = order_to_image_id.get(order)
                return f"{{{{IMAGE_ID_{image_id}}}}}" if image_id else m.group(0)

            new_content = re.sub(r"\{\{IMAGE_ORDER_(\d+)\}\}", _repl, content)
            if new_content != content:
                dml_sql("UPDATE chapters SET content=%s WHERE id=%s", (new_content, chapter_db_id))

        return {"status": "success", "doc_id": doc_id, "chapters": len(chapters), "images": len(images)}

    except Exception as e:
        return {"status": "error", "msg": str(e)}
    finally:
        close_db_connection()
