from flask import Blueprint, request, jsonify, session, send_file
from config.db_config import fetch_one, fetch_all, dml_sql
from .celery_app import celery
import os
import re
import json
import shutil
from datetime import datetime, timedelta
from config.logging_config import logger

# 创建文档处理蓝图
doc_proc = Blueprint('doc_proc', __name__)

# 获取基础目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL_FOLDER = os.path.abspath(os.path.join(BASE_DIR, '../../uploads/final'))

# 配置选项：是否优先使用异步处理
USE_ASYNC_PROCESSING = True
CELERY_TIMEOUT = 5  # Celery 任务提交超时时间（秒）
TASK_TIMEOUT_MINUTES = 30  # 任务超时时间（分钟）


def recover_orphaned_tasks():
    """恢复孤儿任务：检查长时间处理中的任务并重新提交或重置状态"""
    try:
        # 查找超时的处理中任务（超过30分钟仍在处理中的任务）
        timeout_sql = """
            SELECT doc_id, file_path, username, filename, process_start_time
            FROM doc_process_records 
            WHERE status = 'processing' 
            AND process_start_time < NOW() - INTERVAL %s MINUTE
        """
        orphaned_tasks = fetch_all(timeout_sql, parameters=(TASK_TIMEOUT_MINUTES,))
        
        if not orphaned_tasks:
            logger.info("没有发现孤儿任务")
            return
            
        logger.info(f"发现 {len(orphaned_tasks)} 个孤儿任务，开始恢复...")
        
        for task in orphaned_tasks:
            doc_id = task['doc_id']
            file_path = task['file_path']
            username = task['username']
            filename = task['filename']
            start_time = task['process_start_time']
            
            logger.info(f"恢复孤儿任务: doc_id={doc_id}, 开始时间={start_time}")
            
            # 检查文件是否还存在
            if not os.path.exists(file_path):
                logger.warning(f"文件不存在，将任务标记为失败: {file_path}")
                dml_sql("""
                    UPDATE doc_process_records 
                    SET status = 'failed', 
                        process_end_time = NOW(),
                        error_message = '文件不存在，系统重启后恢复时发现'
                    WHERE doc_id = %s
                """, parameters=(doc_id,))
                continue
            
            # 重新提交任务
            try:
                if USE_ASYNC_PROCESSING:
                    # 重新提交到Celery
                    celery.send_task(
                        'file_process.models.prodetail.process_document_task',
                        args=[doc_id, file_path, username, filename],
                        countdown=0,
                        expires=3600
                    )
                    # 刷新开始时间，避免一直被当成“超时处理中”重复恢复
                    dml_sql(
                        "UPDATE doc_process_records SET status='processing', process_start_time=NOW(), error_message=NULL WHERE doc_id=%s",
                        parameters=(doc_id,)
                    )
                    logger.info(f"孤儿任务已重新提交到Celery: doc_id={doc_id}")
                else:
                    # 同步处理
                    logger.info(f"开始同步恢复孤儿任务: doc_id={doc_id}")
                    result = process_document_task(None, doc_id, file_path, username, filename)
                    if not result or result.get('status') != 'success':
                        logger.error(f"同步恢复任务失败: doc_id={doc_id}")
                        dml_sql(
                            "UPDATE doc_process_records SET status='pending', process_start_time=NULL, error_message=%s WHERE doc_id=%s",
                            parameters=("孤儿任务同步恢复失败，已重置为 pending，可手动重试", doc_id)
                        )

            except Exception as e:
                logger.error(f"重新提交孤儿任务失败: doc_id={doc_id}, 错误: {e}")
                # 将任务状态重置为pending，用户可以手动重试
                dml_sql("""
                    UPDATE doc_process_records 
                    SET status = 'pending', 
                        process_start_time = NULL,
                        error_message = %s
                    WHERE doc_id = %s
                """, parameters=(f"系统重启恢复失败: {str(e)}", doc_id))
                
    except Exception as e:
        logger.error(f"恢复孤儿任务时发生错误: {e}")


@doc_proc.route('/api/doc-process/recover-tasks', methods=['POST'])
def recover_tasks_api():
    """手动触发任务恢复的API接口"""
    try:
        recover_orphaned_tasks()
        return jsonify({
            'success': True,
            'message': '任务恢复检查完成'
        })
    except Exception as e:
        logger.error(f"手动恢复任务失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/list', methods=['GET'])
def get_doc_process_list():
    """获取文档处理列表"""
    try:
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        sql = """
            SELECT id, doc_id, upload_id, filename, file_path, username, status,
                   process_result, process_start_time, process_end_time, created_at
            FROM doc_process_records
            WHERE username = %s
            ORDER BY created_at DESC
        """

        records = fetch_all(sql, parameters=(username,))

        # 格式化返回数据
        for record in records:
            if record.get('process_result'):
                try:
                    record['process_result'] = json.loads(record['process_result'])
                except:
                    record['process_result'] = None

        return jsonify({
            'success': True,
            'data': records
        })

    except Exception as e:
        logger.error(f"获取文档处理列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/add', methods=['POST'])
def add_to_process_list():
    """从documentlist添加文档到处理列表"""
    try:
        data = request.json
        upload_id = data.get('upload_id')

        if not upload_id:
            return jsonify({
                'success': False,
                'error': '缺少upload_id'
            }), 400

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        # 检查该文档是否已在处理列表中
        check_sql = "SELECT id FROM doc_process_records WHERE doc_id = %s"
        existing = fetch_one(check_sql, parameters=(upload_id,))

        if existing:
            return jsonify({
                'success': False,
                'error': '文档已在处理列表中'
            }), 400

        # 从upload_sessions获取文档信息
        sql = """
            SELECT upload_id, filename, final_path, username
            FROM upload_sessions
            WHERE upload_id = %s AND status = 'completed'
        """
        upload_record = fetch_one(sql, parameters=(upload_id,))

        if not upload_record:
            return jsonify({
                'success': False,
                'error': '文档不存在或未上传完成'
            }), 404

        # 检查文件是否存在
        file_path = upload_record.get('final_path')
        if file_path and os.path.exists(file_path):
            pass
        else:
            # 兼容历史错误路径：优先按“项目根目录/uploads/final/<username>/<filename>”重建
            project_root = os.path.abspath(os.path.join(BASE_DIR, '..'))
            candidate = os.path.join(project_root, 'uploads', 'final', upload_record.get('username') or username, upload_record['filename'])
            candidate = os.path.abspath(candidate)
            if os.path.exists(candidate):
                file_path = candidate
                # 同步修正 upload_sessions.final_path，避免后续继续写入错误路径
                dml_sql(
                    "UPDATE upload_sessions SET final_path = %s WHERE upload_id = %s",
                    parameters=(file_path, upload_id)
                )
                logger.info(f"修正 upload_sessions.final_path: upload_id={upload_id}, final_path={file_path}")
            else:
                return jsonify({
                    'success': False,
                    'error': '文件不存在'
                }), 404

        # 添加到处理列表
        insert_sql = """
            INSERT INTO doc_process_records
            (doc_id, upload_id, filename, file_path, username, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        """
        dml_sql(insert_sql, parameters=(
            upload_id,
            upload_id,
            upload_record['filename'],
            file_path,
            username
        ))

        logger.info(f"添加文档到处理列表: upload_id={upload_id}, filename={upload_record['filename']}")

        return jsonify({
            'success': True,
            'message': '添加成功'
        })

    except Exception as e:
        logger.error(f"添加文档到处理列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/process', methods=['POST'])
def process_document():
    """处理文档"""
    try:
        # 不要在请求过程中修改全局开关，使用局部变量做本次请求的回退控制
        use_async_processing = USE_ASYNC_PROCESSING
        data = request.json
        doc_id = data.get('doc_id')

        if not doc_id:
            return jsonify({
                'success': False,
                'error': '缺少doc_id'
            }), 400

        # 检查文档是否存在
        check_sql = "SELECT * FROM doc_process_records WHERE doc_id = %s"
        doc_record = fetch_one(check_sql, parameters=(doc_id,))

        if not doc_record:
            return jsonify({
                'success': False,
                'error': '文档不存在'
            }), 404

        # 检查状态
        if doc_record['status'] == 'processing':
            return jsonify({
                'success': False,
                'error': '文档正在处理中'
            }), 400

        # 允许已完成的文档重新处理：用于解析规则升级后的“重跑”
        # （前端会显示为“重新处理”按钮）
        # if doc_record['status'] == 'completed':
        #     return jsonify({
        #         'success': False,
        #         'error': '文档已处理完成'
        #     }), 400

        # 检查并清理该文档的旧数据(chapters, document_images, chapter_images)
        # 避免重复处理导致数据重复
        check_chapters_sql = "SELECT COUNT(*) as count FROM chapters WHERE document_id = %s"
        chapters_count = fetch_one(check_chapters_sql, parameters=(doc_id,))

        if chapters_count['count'] > 0:
            logger.info(f"文档 {doc_id} 存在旧数据,开始清理...")
            # 删除关联表
            delete_chapter_images_sql = """
                DELETE ci FROM chapter_images ci
                INNER JOIN chapters c ON ci.chapter_id = c.id
                WHERE c.document_id = %s
            """
            dml_sql(delete_chapter_images_sql, parameters=(doc_id,))
            # 删除图片
            delete_images_sql = "DELETE FROM document_images WHERE document_id = %s"
            dml_sql(delete_images_sql, parameters=(doc_id,))
            # 删除章节
            delete_chapters_sql = "DELETE FROM chapters WHERE document_id = %s"
            dml_sql(delete_chapters_sql, parameters=(doc_id,))
            logger.info(f"文档 {doc_id} 旧数据清理完成")
        else:
            logger.info(f"文档 {doc_id} 没有旧数据")

        # 更新状态为processing
        update_sql = """
            UPDATE doc_process_records
            SET status = 'processing', process_start_time = NOW()
            WHERE doc_id = %s
        """
        dml_sql(update_sql, parameters=(doc_id,))

        # 异步处理文档
        if use_async_processing:
            try:
                # 直接提交 Celery 任务，不使用 signal（signal 在非主线程中不工作）
                logger.info(f"提交异步任务: doc_id={doc_id}")
                
                # 设置较短的超时时间，避免阻塞用户请求
                celery.send_task(
                    'file_process.models.prodetail.process_document_task', 
                    args=[doc_id, doc_record['file_path'], doc_record['username'], doc_record['filename']],
                    # 添加任务选项，设置超时
                    countdown=0,  # 立即执行
                    expires=3600  # 1小时后过期
                )
                logger.info(f"异步任务提交成功: doc_id={doc_id}")
                
                return jsonify({
                    'success': True,
                    'message': '处理任务已提交'
                })
                    
            except Exception as celery_error:
                # 如果 Celery 任务提交失败，回退到同步处理
                logger.warning(f"Celery 任务提交失败，回退到同步处理: {celery_error}")
                # 设置标志，继续执行同步处理逻辑（仅本次请求生效）
                use_async_processing = False
        
        # 同步处理逻辑（Celery 失败时的回退方案或者 use_async_processing=False 时）
        if not use_async_processing:
            logger.info(f"使用同步处理模式: doc_id={doc_id}")
            # 同步处理逻辑
            try:
                # 直接在当前请求中同步处理
                logger.info(f"开始同步处理文档: doc_id={doc_id}")
                result = process_document_task(None, doc_id, doc_record['file_path'], doc_record['username'], doc_record['filename'])
                
                if result and result.get('status') == 'success':
                    return jsonify({
                        'success': True,
                        'message': '文档处理完成'
                    })
                else:
                    # 恢复状态为 pending
                    dml_sql("UPDATE doc_process_records SET status = 'pending', process_start_time = NULL WHERE doc_id = %s", parameters=(doc_id,))
                    return jsonify({
                        'success': False,
                        'error': f"处理失败: {result.get('msg', '未知错误') if result else '处理异常'}"
                    }), 500
                    
            except Exception as sync_error:
                # 同步处理也失败，恢复状态
                logger.error(f"同步处理失败: {sync_error}")
                dml_sql("UPDATE doc_process_records SET status = 'failed', process_end_time = NOW() WHERE doc_id = %s", parameters=(doc_id,))
                return jsonify({
                    'success': False,
                    'error': f"处理失败: {str(sync_error)}"
                }), 500

        # 理论上不会走到这里：异步成功会提前 return，异步失败会回退同步并 return。
        return jsonify({
            'success': False,
            'error': '处理任务提交失败'
        }), 500

    except Exception as e:
        logger.error(f"处理文档失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/delete', methods=['DELETE'])
def delete_document():
    """删除处理记录"""
    try:
        data = request.json
        doc_id = data.get('doc_id')

        if not doc_id:
            return jsonify({
                'success': False,
                'error': '缺少doc_id'
            }), 400

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        # 先获取文档信息，用于后续清理文件
        doc_info_sql = "SELECT file_path FROM doc_process_records WHERE doc_id = %s AND username = %s"
        doc_info = fetch_one(doc_info_sql, parameters=(doc_id, username))

        if not doc_info:
            return jsonify({
                'success': False,
                'error': '记录不存在或无权限删除'
            }), 404

        file_path = doc_info.get('file_path')

        # 1. 先获取所有图片路径，用于后续删除文件
        get_images_sql = "SELECT image_path FROM document_images WHERE document_id = %s"
        image_records = fetch_all(get_images_sql, parameters=(doc_id,))
        image_paths = [img['image_path'] for img in image_records]

        # 2. 删除章节-图片关联表（必须在删除章节之前）
        delete_chapter_images_sql = """
            DELETE ci FROM chapter_images ci
            INNER JOIN chapters c ON ci.chapter_id = c.id
            WHERE c.document_id = %s
        """
        dml_sql(delete_chapter_images_sql, parameters=(doc_id,))
        logger.info(f"删除章节-图片关联: document_id={doc_id}")

        # 3. 删除文档图片记录
        delete_images_sql = "DELETE FROM document_images WHERE document_id = %s"
        dml_sql(delete_images_sql, parameters=(doc_id,))
        logger.info(f"删除文档图片记录: document_id={doc_id}")

        # 4. 删除章节记录
        delete_chapters_sql = "DELETE FROM chapters WHERE document_id = %s"
        dml_sql(delete_chapters_sql, parameters=(doc_id,))
        logger.info(f"删除章节记录: document_id={doc_id}")

        # 5. 删除处理记录
        delete_record_sql = "DELETE FROM doc_process_records WHERE doc_id = %s AND username = %s"
        affected_rows = dml_sql(delete_record_sql, parameters=(doc_id, username))

        if affected_rows == 0:
            return jsonify({
                'success': False,
                'error': '记录不存在或无权限删除'
            }), 404

        # 6. 删除处理过程中生成的图片文件（不删除原始word文件）
        # 先记录图片目录路径，再删除文件
        images_dir = None
        if image_paths:
            images_dir = os.path.dirname(image_paths[0])
        
        deleted_count = 0
        for img_path in image_paths:
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
                    deleted_count += 1
                    logger.info(f"删除图片文件: {img_path}")
            except Exception as e:
                logger.warning(f"删除图片文件失败 {img_path}: {e}")

        # 7. 删除图片目录（如果目录为空或只剩空目录则删除）
        if images_dir:
            try:
                # 检查目录是否存在且为空
                if os.path.exists(images_dir) and not os.listdir(images_dir):
                    shutil.rmtree(images_dir)
                    logger.info(f"删除空的图片目录: {images_dir}")
            except Exception as e:
                logger.warning(f"删除图片目录失败: {e}")

        logger.info(f"删除处理记录完成: doc_id={doc_id}, 删除了 {deleted_count} 个图片文件")

        return jsonify({
            'success': True,
            'message': '删除成功'
        })

    except Exception as e:
        logger.error(f"删除处理记录失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/download', methods=['GET'])
def download_document():
    """下载文档"""
    try:
        doc_id = request.args.get('doc_id')

        if not doc_id:
            return jsonify({
                'success': False,
                'error': '缺少doc_id'
            }), 400

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        # 获取文档信息
        sql = "SELECT * FROM doc_process_records WHERE doc_id = %s AND username = %s"
        doc_record = fetch_one(sql, parameters=(doc_id, username))

        if not doc_record:
            return jsonify({
                'success': False,
                'error': '文档不存在或无权限'
            }), 404

        file_path = doc_record.get('file_path')
        filename = doc_record.get('filename')

        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404

        # 返回文件
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"下载文档失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/detail', methods=['GET'])
def get_document_detail():
    """获取文档处理详情"""
    try:
        doc_id = request.args.get('doc_id')

        if not doc_id:
            return jsonify({
                'success': False,
                'error': '缺少doc_id'
            }), 400

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        # 获取文档信息
        sql = "SELECT * FROM doc_process_records WHERE doc_id = %s AND username = %s"
        doc_record = fetch_one(sql, parameters=(doc_id, username))

        if not doc_record:
            return jsonify({
                'success': False,
                'error': '文档不存在或无权限'
            }), 404

        # 解析处理结果
        if doc_record.get('process_result'):
            try:
                doc_record['process_result'] = json.loads(doc_record['process_result'])
            except:
                doc_record['process_result'] = None

        return jsonify({
            'success': True,
            'data': doc_record
        })

    except Exception as e:
        logger.error(f"获取文档详情失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/status', methods=['GET'])
def get_process_status():
    """获取文档处理状态（用于轮询）"""
    try:
        doc_id = request.args.get('doc_id')

        if not doc_id:
            return jsonify({
                'success': False,
                'error': '缺少doc_id'
            }), 400

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        # 获取文档状态
        sql = """
            SELECT doc_id, filename, status, process_result,
                   process_start_time, process_end_time, created_at
            FROM doc_process_records
            WHERE doc_id = %s AND username = %s
        """
        doc_record = fetch_one(sql, parameters=(doc_id, username))

        if not doc_record:
            return jsonify({
                'success': False,
                'error': '文档不存在或无权限'
            }), 404

        # 解析处理结果
        if doc_record.get('process_result'):
            try:
                doc_record['process_result'] = json.loads(doc_record['process_result'])
            except:
                doc_record['process_result'] = None

        return jsonify({
            'success': True,
            'data': {
                'doc_id': doc_record['doc_id'],
                'filename': doc_record['filename'],
                'status': doc_record['status'],
                'process_result': doc_record['process_result'],
                'process_start_time': doc_record['process_start_time'].strftime('%Y-%m-%d %H:%M:%S') if doc_record['process_start_time'] else None,
                'process_end_time': doc_record['process_end_time'].strftime('%Y-%m-%d %H:%M:%S') if doc_record['process_end_time'] else None,
                'created_at': doc_record['created_at'].strftime('%Y-%m-%d %H:%M:%S') if doc_record['created_at'] else None
            }
        })

    except Exception as e:
        logger.error(f"获取处理状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@doc_proc.route('/api/doc-process/chapters', methods=['GET'])
def get_document_chapters():
    """获取文档的章节树"""
    try:
        doc_id = request.args.get('doc_id')

        if not doc_id:
            return jsonify({
                'success': False,
                'error': '缺少doc_id'
            }), 400

        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'

        # 获取所有章节及其关联的图片信息
        sql = """
            SELECT c.id, c.title, c.level, c.content, c.parent_id, c.order_index,
                   c.paragraph_index, c.is_bold, c.font_size, c.style_name,
                   GROUP_CONCAT(
                       CONCAT(di.id, ':', di.image_path, ':', di.image_url)
                       ORDER BY ci.position_in_chapter
                       SEPARATOR '|'
                   ) as images
            FROM chapters c
            LEFT JOIN chapter_images ci ON c.id = ci.chapter_id
            LEFT JOIN document_images di ON ci.image_id = di.id
            WHERE c.document_id = %s
            GROUP BY c.id, c.title, c.level, c.content, c.parent_id, c.order_index,
                     c.paragraph_index, c.is_bold, c.font_size, c.style_name
            ORDER BY c.level, c.order_index, c.paragraph_index
        """
        chapters = fetch_all(sql, parameters=(doc_id,))

        # 处理图片数据
        for chapter in chapters:
            if chapter['images']:
                # 解析图片信息
                image_list = []
                for img_info in chapter['images'].split('|'):
                    if img_info.strip():
                        parts = img_info.split(':', 2)  # 最多分割2次，防止URL中的冒号被分割
                        if len(parts) >= 3:
                            image_list.append({
                                'id': parts[0],
                                'image_path': parts[1],
                                'image_url': parts[2]
                            })
                chapter['images'] = image_list
            else:
                chapter['images'] = []

        # 构建树形结构
        # 找出所有存在的ID
        existing_ids = {c['id'] for c in chapters}

        # 找出孤节点（parent_id指向不存在的节点）
        orphan_chapters = [
            c for c in chapters
            if c.get('parent_id') and c.get('parent_id') not in existing_ids
        ]

        def build_tree(parent_id=None):
            children = [c for c in chapters if c.get('parent_id') == parent_id]
            children.sort(key=lambda x: (x['level'], x['order_index']))

            result = []
            for child in children:
                node = {
                    'id': child['id'],
                    'title': child['title'],
                    'level': child['level'],
                    'content': child['content'],
                    'parent_id': child['parent_id'],
                    'order_index': child['order_index'],
                    'paragraph_index': child['paragraph_index'],
                    'is_bold': child['is_bold'],
                    'font_size': child['font_size'],
                    'style_name': child['style_name'],
                    'has_content': bool(child['content']),
                    'images': child['images'],  # 添加图片信息
                    'children': build_tree(child['id'])
                }
                result.append(node)

            return result

        # 构建树形结构
        tree = build_tree()

        # 将孤节点也作为根节点显示
        for orphan in orphan_chapters:
            node = {
                'id': orphan['id'],
                'title': orphan['title'],
                'level': orphan['level'],
                'content': orphan['content'],
                'parent_id': orphan['parent_id'],
                'order_index': orphan['order_index'],
                'paragraph_index': orphan['paragraph_index'],
                'is_bold': orphan['is_bold'],
                'font_size': orphan['font_size'],
                'style_name': orphan['style_name'],
                'has_content': bool(orphan['content']),
                'images': orphan['images'],  # 添加图片信息
                'children': build_tree(orphan['id'])
            }
            tree.append(node)

        return jsonify({
            'success': True,
            'data': {
                'doc_id': doc_id,
                'chapters': tree,
                'total_count': len(chapters)
            }
        })

    except Exception as e:
        logger.error(f"获取章节树失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@celery.task(bind=True, max_retries=3)
def process_document_task(self, doc_id, file_path, username, filename):
    """Celery异步处理文档任务"""
    from config.db_config import dml_sql as task_dml_sql, query_sql, dml_sql_with_insert_id

    try:
        from pathlib import Path

        logger.info(f"开始处理文档: doc_id={doc_id}, file_path={file_path}")

        # 根据文件类型选择处理方式
        if file_path.endswith('.docx'):
            # 直接调用 WordParser 处理 Word 文档（不通过 Celery，避免任务嵌套）
            logger.info(f"直接调用WordParser处理Word文档: {file_path}")
            from .word_parser import WordParser
            
            # 配置基础路径 - 存储在 file_process/images 目录下
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            BASE_STORAGE = os.path.join(current_dir, "images")  # file_process/images
            BASE_URL = "/images"
            
            # 直接调用 WordParser 类进行处理
            try:
                parser = WordParser(file_path, username, doc_id, BASE_STORAGE, BASE_URL)
                chapters, images = parser.parse(doc_id)
                
                # A. 清理旧数据
                task_dml_sql("DELETE FROM chapters WHERE document_id = %s", (doc_id,))
                task_dml_sql("DELETE FROM document_images WHERE document_id = %s", (doc_id,))
                task_dml_sql("""
                    DELETE ci FROM chapter_images ci
                    INNER JOIN chapters c ON ci.chapter_id = c.id
                    WHERE c.document_id = %s
                """, (doc_id,))

                # B. 建立临时ID到数据库真实ID的映射
                temp_to_real_id: dict[object, object] = {None: None}

                # C. 遍历章节并入库
                for c in chapters:
                    parent_db_id = temp_to_real_id.get(c['parent_temp_id'])
                    
                    # 计算同级排序 index
                    count_res = query_sql(
                        "SELECT COUNT(*) as count FROM chapters WHERE document_id = %s AND parent_id <=> %s", 
                        (doc_id, parent_db_id)
                    )
                    order_index = count_res[0]['count'] if count_res else 0

                    # 插入章节并获取自增ID
                    chapter_sql = """
                        INSERT INTO chapters (document_id, parent_id, level, order_index, title, content, 
                                             style_name, font_size, is_bold, paragraph_index)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    params = (
                        doc_id, parent_db_id, c['level'], order_index, c['title'], c['content'],
                        c['style_name'], c['font_size'], int(bool(c.get('is_bold'))), c['paragraph_index']
                    )
                    
                    new_id, _ = dml_sql_with_insert_id(chapter_sql, params)
                    temp_to_real_id[c['temp_id']] = new_id

                # D. 插入图片数据并建立章节关联（按章节内位置写入 position_in_chapter）
                img_sql = """
                    INSERT INTO document_images (document_id, image_name, image_path, image_url, 
                                                image_type, paragraph_index, order_in_doc, file_size)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """

                # 记录 order_in_doc -> image_id，用于回写章节 content 占位符
                order_to_image_id: dict[int, int] = {}

                for img in images:
                    # 插入图片并获取图片ID
                    image_id, _ = dml_sql_with_insert_id(img_sql, (
                        doc_id,
                        img['image_name'],
                        img['image_path'],
                        img.get('image_url'),
                        img.get('image_type'),
                        img.get('paragraph_index'),
                        img.get('order_in_doc'),
                        img.get('file_size')
                    ))

                    # order_in_doc -> image_id
                    order_in_doc = img.get('order_in_doc')
                    try:
                        order_in_doc_int = int(order_in_doc) if order_in_doc is not None else None
                    except Exception:
                        order_in_doc_int = None

                    if image_id and order_in_doc_int is not None:
                        order_to_image_id[order_in_doc_int] = int(image_id)

                    # 图片所属章节：优先使用解析阶段记录的 chapter_temp_id
                    chapter_temp_id = img.get('chapter_temp_id')
                    target_chapter_id = temp_to_real_id.get(chapter_temp_id) if chapter_temp_id is not None else None

                    # 兜底：如果缺失归属信息，落到“正文”章节
                    if target_chapter_id is None and chapters:
                        target_chapter_id = temp_to_real_id.get(chapters[0]['temp_id'])

                    position = img.get('position_in_chapter', 0)
                    try:
                        position_int = int(position) if position is not None else 0
                    except Exception:
                        position_int = 0

                    # 建立章节-图片关联（带章节内顺序）
                    if target_chapter_id and image_id:
                        chapter_image_sql = """
                            INSERT INTO chapter_images (chapter_id, image_id, position_in_chapter)
                            VALUES (%s, %s, %s)
                        """
                        task_dml_sql(
                            chapter_image_sql,
                            (target_chapter_id, image_id, position_int)
                        )

                # E. 回写章节 content：将 IMAGE_ORDER 占位符替换为 IMAGE_ID 占位符
                for c in chapters:
                    chapter_db_id = temp_to_real_id.get(c['temp_id'])
                    if not chapter_db_id:
                        continue
                    content = str(c.get('content') or '')
                    if '{{IMAGE_ORDER_' not in content:
                        continue

                    def _repl(m):
                        order = int(m.group(1))
                        img_id = order_to_image_id.get(order)
                        return f"{{{{IMAGE_ID_{img_id}}}}}" if img_id else m.group(0)

                    new_content = re.sub(r"\{\{IMAGE_ORDER_(\d+)\}\}", _repl, content)
                    if new_content != content:
                        task_dml_sql(
                            "UPDATE chapters SET content=%s WHERE id=%s",
                            parameters=(new_content, chapter_db_id)
                        )

                result = {
                    "status": "success", 
                    "doc_id": doc_id, 
                    "chapters": len(chapters), 
                    "images": len(images)
                }
                
            except Exception as e:
                logger.error(f"Word文档处理失败: {e}")
                result = {"status": "error", "msg": str(e)}

            # 更新处理状态到 doc_process_records
            if result.get('status') == 'success':
                process_result = {
                    'metadata': {
                        'chapter_count': result.get('chapters', 0),
                        'image_count': result.get('images', 0)
                    },
                    'process_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'success'
                }

                update_sql = """
                    UPDATE doc_process_records
                    SET status = 'completed',
                        process_result = %s,
                        process_end_time = NOW()
                    WHERE doc_id = %s
                """
                task_dml_sql(update_sql, parameters=(json.dumps(process_result, ensure_ascii=False), doc_id))

                logger.info(f"Word文档处理成功: doc_id={doc_id}, chapters={result.get('chapters')}, images={result.get('images')}")
                return process_result
            else:
                # 处理失败
                error_info = {
                    'error': result.get('msg', '未知错误'),
                    'process_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'failed'
                }

                update_sql = """
                    UPDATE doc_process_records
                    SET status = 'failed',
                        process_result = %s,
                        process_end_time = NOW()
                    WHERE doc_id = %s
                """
                task_dml_sql(update_sql, parameters=(json.dumps(error_info, ensure_ascii=False), doc_id))

                logger.error(f"Word文档处理失败: doc_id={doc_id}, error={result.get('msg')}")
                return error_info

        elif file_path.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                file_info = {
                    'file_size': os.path.getsize(file_path),
                    'file_type': '.txt',
                    'process_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'message': '文档处理成功',
                    'details': {
                        'word_count': len(content),
                        'paragraph_count': len([p for p in content.split('\n') if p.strip()]),
                        'summary': content[:200] + '...' if len(content) > 200 else content
                    },
                    'status': 'success'
                }

                # 更新处理结果
                update_sql = """
                    UPDATE doc_process_records
                    SET status = 'completed',
                        process_result = %s,
                        process_end_time = NOW()
                    WHERE doc_id = %s
                """
                task_dml_sql(update_sql, parameters=(json.dumps(file_info, ensure_ascii=False), doc_id))

                return file_info

        elif file_path.endswith('.pdf'):
            file_info = {
                'file_size': os.path.getsize(file_path),
                'file_type': '.pdf',
                'process_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'message': 'PDF文档处理(需要安装pdfplumber等库)',
                'details': {
                    'summary': 'PDF文档处理(需要安装pdfplumber等库)'
                },
                'status': 'success'
            }

            # 更新处理结果
            update_sql = """
                UPDATE doc_process_records
                SET status = 'completed',
                    process_result = %s,
                    process_end_time = NOW()
                WHERE doc_id = %s
            """
            task_dml_sql(update_sql, parameters=(json.dumps(file_info, ensure_ascii=False), doc_id))

            return file_info

        else:
            # 不支持的文件类型
            from pathlib import Path
            file_info = {
                'file_size': os.path.getsize(file_path),
                'file_type': Path(file_path).suffix,
                'process_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'message': '不支持的文件类型',
                'status': 'failed'
            }

            # 更新处理结果
            update_sql = """
                UPDATE doc_process_records
                SET status = 'failed',
                    process_result = %s,
                    process_end_time = NOW()
                WHERE doc_id = %s
            """
            task_dml_sql(update_sql, parameters=(json.dumps(file_info, ensure_ascii=False), doc_id))

            return file_info

    except Exception as e:
        logger.error(f"文档处理失败: doc_id={doc_id}, error={e}")

        # 更新为失败状态
        update_sql = """
            UPDATE doc_process_records
            SET status = 'failed',
                process_result = %s,
                process_end_time = NOW()
            WHERE doc_id = %s
        """
        error_info = {
            'error': str(e),
            'process_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'failed'
        }
        task_dml_sql(update_sql, parameters=(json.dumps(error_info, ensure_ascii=False), doc_id))

        raise
