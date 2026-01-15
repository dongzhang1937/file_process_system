from pydoc import doc
from flask import Blueprint,request,redirect,render_template,url_for,flash,session,jsonify
from config.db_config import fetch_one,fetch_all,dml_sql
import os
import hashlib
import redis
import json
import sys
from datetime import datetime, timedelta
from celery import Celery
#from celery import shared_task
from .celery_app import celery

from config.logging_config import logger  # type: ignore

# 添加父目录到路径，以便导入统一配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from config.app_config import Config





upload_bp = Blueprint('upload', __name__)


# 文件上传配置信息
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录（file_process/models -> file_process -> 项目根目录）
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '../../'))
# 文件上传配置信息（使用绝对路径，与 prodetail.py 保持一致）
UPLOAD_FOLDER = os.path.abspath(os.path.join(PROJECT_ROOT, 'uploads/temp'))
FINAL_FOLDER = os.path.abspath(os.path.join(PROJECT_ROOT, 'uploads/final'))
CHUNK_SIZE = 1024 * 1024 * 20  # 20MB
MAX_FILE_SIZE = 1024 * 1024 * 5000  # 5000MB
ALLOWED_EXTENSIONS = {'docx', 'pdf', 'txt'}

# ============ 2. Redis配置 (仅用于缓存和 Celery Broker) ============
try:
    # 使用统一配置创建Redis连接
    redis_config = Config.get_redis_config_dict()
    redis_pool = redis.ConnectionPool(**redis_config)
    redis_client = redis.Redis(connection_pool=redis_pool)
    redis_client.ping()
    redis_available = True
except Exception as e:
    logger.warning(f"Redis不可用: {e}")
    redis_client = None
    redis_available = False

####辅助函数
def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_upload_session(upload_id):
    """获取上传会话（优先Redis，降级数据库SQL）"""
    # 1. 尝试 Redis
    if redis_available and redis_client:
        try:
            key = f'upload:{upload_id}'
            data = redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis获取失败: {e}")
    
    # 2. 尝试数据库 (原生 SQL)
    sql = ("""
        SELECT upload_id, filename, filesize, total_chunks, uploaded_chunks,
               status, final_path, created_at, username
        FROM upload_sessions
        WHERE upload_id = %s
    """)

    try:
        result =fetch_one(sql, parameters=(upload_id,))
        
        if result:
            # 兼容 SQLAlchemy 1.4+ 的行对象访问
            #row = result._mapping if hasattr(result, '_mapping') else result
            
            return {
                'upload_id': result['upload_id'],
                'filename': result['filename'],
                'filesize': result['filesize'],
                'total_chunks': result['total_chunks'],
                'uploaded_chunks': json.loads(result['uploaded_chunks']) if result['uploaded_chunks'] else [],
                'status': result['status'],
                'final_path': result['final_path'],
                'created_at': result['created_at'].isoformat() if result['created_at'] else None
            }
    except Exception as e:
        logger.error(f"数据库查询失败: {e}")
        
    return None


def save_upload_session(upload_id, session_data):
    user_info=session.get('user')
    username=user_info.get('username') if user_info else 'anonymous'
    """保存上传会话（双写Redis和数据库SQL）"""
    try:
        # 1. 写入Redis
        if redis_available and redis_client:
            print('回话信息写入redis中')
            key = f'upload:{upload_id}'
            redis_client.setex(
                key,
                timedelta(hours=24),
                json.dumps(session_data)
            )
    except Exception as e:
        logger.error(f"Redis写入失败: {upload_id} - {e}")
        # Redis失败后继续写入数据库

    # 2. 写入数据库 (原生 SQL Upsert 逻辑)
    try:
        current_time = datetime.utcnow()
        
        # 准备参数
        uploaded_chunks_str = json.dumps(session_data.get('uploaded_chunks', []))
        status = session_data.get('status', 'initialized')
        final_path = session_data.get('final_path')
        
        # 尝试更新
        update_sql = ("""
            UPDATE upload_sessions 
            SET filename = %s,
                filesize = %s,
                total_chunks = %s,
                uploaded_chunks = %s,
                status = %s,
                final_path =%s,
                updated_at = %s,
                completed_at = %s
            WHERE upload_id = %s
        """)
        
        params = {
            'upload_id': upload_id,
            'filename': session_data['filename'],
            'filesize': session_data['filesize'],
            'total_chunks': session_data['total_chunks'],
            'uploaded_chunks': uploaded_chunks_str,
            'status': status,
            'final_path': final_path,
            'updated_at': current_time,
            'completed_at': current_time if status == 'completed' else None
        }
        
        result = dml_sql(sql=update_sql, parameters=(
            params['filename'],
            params['filesize'],
            params['total_chunks'],
            params['uploaded_chunks'],
            params['status'],
            params['final_path'],
            params['updated_at'],
            params['completed_at'],
            params['upload_id']
        ))
        print('result',result,type(result))
        # 如果没有更新任何行，说明是新记录，执行插入
        if result == 0:
            insert_sql = ("""
                INSERT INTO upload_sessions 
                (upload_id, filename, filesize, total_chunks, uploaded_chunks, 
                 status, final_path,updated_at, created_at, username )
                VALUES 
                (%s, %s, %s, %s, %s, 
                 %s, %s, %s, %s,%s)
            """)
            params = {
            'upload_id': upload_id,
            'filename': session_data['filename'],
            'filesize': session_data['filesize'],
            'total_chunks': session_data['total_chunks'],
            'uploaded_chunks': uploaded_chunks_str,
            'status': status,
            'final_path': final_path,
            'updated_at': current_time,
            'username': username
        }
            # 插入需要 created_at
            params['created_at'] = current_time
            # print('params',params)
            
            dml_sql(sql=insert_sql,
            parameters=(
                params['upload_id'],
                params['filename'],
                params['filesize'],
                params['total_chunks'],
                params['uploaded_chunks'],
                params['status'],
                params['final_path'],
                params['updated_at'],
                params['created_at'],
                params['username']
                ))

        #db.session.commit()
        return True

    except Exception as e:
        logger.error(f"数据库写入失败 {upload_id}: {e}")
       # db.session.rollback()
        return False

# ============ 页面路由 ============

@upload_bp.route('/upload')
def upload_page():
    """文件上传页面"""
    return render_template('fileupload.html')


@upload_bp.route('/process')
def process_page():
    """文档处理页面"""
    return render_template('fileupload.html')


@upload_bp.route('/入库')
def storage_page():
    """文档入库页面"""
    return render_template('fileupload.html')


@upload_bp.route('/query')
def query_page():
    """文档查询页面"""
    return render_template('fileupload.html')


@upload_bp.route('/chat')
def chat_page():
    """文档对话页面"""
    return render_template('fileupload.html')


# ============ API路由 ============
@upload_bp.route('/upload/init', methods=['POST'])
def init_upload():
    """初始化上传会话"""
    # print(request.json)
    user_info=session.get('user')
    username=user_info.get('username') if user_info else 'anonymous'
    try:
        data = request.json
        # print(data)
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400
        filename = data.get('filename')
        filesize = data.get('filesize')
        
        if not filename or not filesize:
            return jsonify({'error': '缺少文件名或文件大小'}), 400
        
        # 检查文件类型
        if not allowed_file(filename):
            return jsonify({'error': '不支持的文件格式，仅支持: .docx, .pdf, .txt'}), 400
        
        # 检查文件大小
        if filesize > MAX_FILE_SIZE:
            return jsonify({'error': f'文件过大，最大支持{MAX_FILE_SIZE / (1024*1024)}MB'}), 400
       
       # 检查该用户下是否已存在同名文件
        try:
            check_sql = """
                SELECT upload_id, filename, status, final_path
                FROM upload_sessions
                WHERE username = %s AND filename = %s 
                LIMIT 1
            """
            # print(username,filename)
            existing_file = fetch_one(check_sql, parameters=(username, filename,))
            # print(existing_file)
            
            if existing_file:
                print('已存在，请勿重复上传')
                return jsonify({'error': f'文件 "{filename}" 已存在，请勿重复上传'}), 400
        except Exception as db_error:
            logger.error(f"检查同名文件失败: {db_error}")


        # 生成上传ID
        upload_id = hashlib.md5(
            f"{filename}{username}".encode()
        ).hexdigest()
        
        total_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        # 创建上传目录
        upload_dir = os.path.join(UPLOAD_FOLDER, upload_id)
        os.makedirs(upload_dir, exist_ok=True)
        
        # 创建会话数据
        session_data = {
            'upload_id': upload_id,
            'filename': filename,
            'filesize': filesize,
            'total_chunks': total_chunks,
            'uploaded_chunks': [],
            'status': 'initialized',
            'created_at': datetime.now().isoformat(),
            'username': username  # 添加 username
        }
        print('session_data',session_data,)
        save_upload_session(upload_id, session_data)
        
        logger.info(f"上传初始化: {upload_id} - {filename}")
        
        return jsonify({
            'upload_id': upload_id,
            'total_chunks': total_chunks,
            'chunk_size': CHUNK_SIZE
        })
        
    except Exception as e:
        logger.error(f"初始化上传失败: {e}")
        return jsonify({'error': f'初始化失败: {str(e)}'}), 500

@upload_bp.route('/upload/list', methods=['GET'])
def get_upload_list():
    """获取当前用户的上传列表"""
    try:
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'
        
        sql = """
            SELECT upload_id, filename, filesize, total_chunks, uploaded_chunks,
                   status, final_path, created_at, completed_at
            FROM upload_sessions  where username =%s
            ORDER BY created_at DESC
        """       
        results = fetch_all(sql, parameters=(username,))        
        # print('results', results)
        upload_list = []
        for row in results:
            upload_list.append({
                'upload_id': row['upload_id'],
                'filename': row['filename'],
                'filesize': row['filesize'],
                'total_chunks': row['total_chunks'],
                'uploaded_chunks': json.loads(row['uploaded_chunks']) if row['uploaded_chunks'] else [],
                'status': row['status'],
                'final_path': row['final_path'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None
            })        
        return jsonify({'uploads': upload_list})
        
    except Exception as e:
        logger.error(f"获取上传列表失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@upload_bp.route('/upload/delete/<upload_id>', methods=['DELETE'])
def delete_upload(upload_id):
    """删除上传记录"""
    try:
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'
        
        # 获取上传记录信息
        sql = """
            SELECT upload_id, filename, final_path, status 
            FROM upload_sessions 
            WHERE upload_id = %s AND username = %s
        """
        upload_record = fetch_one(sql, parameters=(upload_id, username))
        
        if not upload_record:
            return jsonify({'error': '记录不存在或无权限'}), 404
        
        # 删除物理文件
        if upload_record['final_path'] and os.path.exists(upload_record['final_path']):
            try:
                os.remove(upload_record['final_path'])
                logger.info(f"删除文件: {upload_record['final_path']}")
            except Exception as e:
                logger.warning(f"删除文件失败: {e}")
        
        # 删除临时分片目录
        upload_dir = os.path.join(UPLOAD_FOLDER, upload_id)
        if os.path.exists(upload_dir):
            try:
                import shutil
                shutil.rmtree(upload_dir, ignore_errors=True)
                logger.info(f"删除临时目录: {upload_dir}")
            except Exception as e:
                logger.warning(f"删除临时目录失败: {e}")
        
        # 删除数据库记录
        delete_sql = "DELETE FROM upload_sessions WHERE upload_id = %s AND username = %s"
        result = dml_sql(delete_sql, (upload_id, username))
        
        logger.info(f"删除上传记录: {upload_id}")
        
        return jsonify({'success': True, 'message': '删除成功'})
        
    except Exception as e:
        logger.error(f"删除上传记录失败: {upload_id} - {e}")
        return jsonify({'error': f'删除失败: {str(e)}'}), 500

@upload_bp.route('/upload/chunk', methods=['POST'])
def upload_chunk():
    """上传单个分片"""
    try:
        upload_id = request.form.get('upload_id')
        chunk_index = request.form.get('chunk_index')
        chunk_file = request.files.get('chunk')
        
        if not all([upload_id, chunk_index is not None, chunk_file]):
            return jsonify({'error': '缺少必要参数'}), 400
        
        chunk_index = int(chunk_index)
        
        # 获取会话信息
        session_data = get_upload_session(upload_id)
        
        if not session_data:
            return jsonify({'error': '上传会话不存在或已过期'}), 404
        
        # 验证分片索引
        if chunk_index >= session_data['total_chunks']:
            return jsonify({'error': f'无效的分片索引: {chunk_index}'}), 400
        
        # 保存分片
        upload_dir = os.path.join(UPLOAD_FOLDER, upload_id)
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir, exist_ok=True)
        
        chunk_path = os.path.join(upload_dir, f'chunk_{chunk_index}')
        chunk_file.save(chunk_path)
        
        # 更新已上传分片列表
        uploaded_chunks = session_data.get('uploaded_chunks', [])
        if chunk_index not in uploaded_chunks:
            uploaded_chunks.append(chunk_index)
            uploaded_chunks.sort()
            session_data['uploaded_chunks'] = uploaded_chunks
            session_data['status'] = 'uploading'
        
        save_upload_session(upload_id, session_data)
        
        progress = (len(uploaded_chunks) / session_data['total_chunks']) * 100
        
        logger.info(f"分片上传: {upload_id} - {chunk_index}/{session_data['total_chunks']}")
        
        return jsonify({
            'success': True,
            'chunk_index': chunk_index,
            'uploaded_chunks': len(uploaded_chunks),
            'total_chunks': session_data['total_chunks'],
            'progress': round(progress, 2)
        })
        
    except Exception as e:
        logger.error(f"分片上传失败: {e}")
        return jsonify({'error': f'分片上传失败: {str(e)}'}), 500



@upload_bp.route('/upload/complete', methods=['POST'])
def complete_upload():
    """完成上传，触发合并"""
    try:
        data = request.json
        upload_id = data.get('upload_id')
        
        if not upload_id:
            return jsonify({'error': '缺少upload_id'}), 400
        
        session_data = get_upload_session(upload_id)
        
        if not session_data:
            return jsonify({'error': '上传会话不存在'}), 404
        
        uploaded_chunks = session_data.get('uploaded_chunks', [])
        total_chunks = session_data['total_chunks']
        
        # 检查是否所有分片都已上传
        if len(uploaded_chunks) != total_chunks:
            return jsonify({
                'error': '分片未完全上传',
                'uploaded': len(uploaded_chunks),
                'total': total_chunks
            }), 400
        
        # 更新状态
        session_data['status'] = 'merging'
        save_upload_session(upload_id, session_data)
        
        # 触发异步合并任务
        merge_task = merge_chunks_task.delay(upload_id)
        
        logger.info(f"合并任务启动: {upload_id} - task_id: {merge_task.id}")
        
        return jsonify({
            'success': True,
            'message': '合并已开始',
            'task_id': merge_task.id,
            'upload_id': upload_id
        })
        
    except Exception as e:
        logger.error(f"完成上传失败: {e}")
        return jsonify({'error': f'完成上传失败: {str(e)}'}), 500


@upload_bp.route('/upload/merge-status/<task_id>', methods=['GET'])
def get_merge_status(task_id):
    """查询合并任务状态"""
    try:
        task = merge_chunks_task.AsyncResult(task_id)
        # 安全地获取 task.info（可能是字典、异常对象或其他类型）
        def safe_get_info(key, default=0):
            if isinstance(task.info, dict):
                return task.info.get(key, default)
            return default
        
        if task.state == 'PENDING':
            response = {'state': task.state, 'progress': 0}
        elif task.state == 'PROGRESS':
            response = {
                'state': task.state,
                'progress': safe_get_info('progress', 0)
            }
        elif task.state == 'SUCCESS':
            response = {
                'state': task.state,
                'progress': 100,
                'result': task.info if isinstance(task.info, dict) else {}
            }
        elif task.state == 'RETRY':
            # 对于 RETRY 状态，简化处理，不返回重试次数
            response = {
                'state': task.state,
                'progress': safe_get_info('progress', 0),
                'error':  str(task.info) if task.info else 'Unknown error'
            }
        else: # FAILURE, REJECTED, etc.
            response = {
                'state': task.state,
                'progress': 0,
                'error':  str(task.info) if task.info else 'Unknown error'
            }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"查询合并状态失败: {e}")
        return jsonify({'error': f'查询失败: {str(e)}'}), 500


# ============ Celery异步任务 ============
# 不使用 @celery.task，改用 @shared_task
# 这样它会自动绑定到当前运行的 app 上的 celery 实例
@celery.task(bind=True, max_retries=3)
def merge_chunks_task(self, upload_id):
    """合并分片文件"""
    try:
        logger.info(f"开始合并: {upload_id}")
        logger.info(f"UPLOAD_FOLDER路径: {UPLOAD_FOLDER}")
        logger.info(f"FINAL_FOLDER路径: {FINAL_FOLDER}")
        
        # 从数据库获取会话信息
        sql='''SELECT upload_id, filename, filesize, total_chunks, uploaded_chunks, 
               status, final_path, created_at ,username
        FROM upload_sessions 
        WHERE upload_id = %s limit 1'''
        paras=(upload_id,)
        db_session = fetch_one(sql, parameters=paras)
        
        if not db_session:
            raise Exception(f'上传会话不存在: {upload_id}')
        
        filename = db_session['filename']
        total_chunks = db_session['total_chunks']
        filesize = db_session['filesize']
        username = db_session.get('username', 'anonymous')  # 获取 username
        # 创建用户目录
        user_final_folder = os.path.join(FINAL_FOLDER, username)
        if not os.path.exists(user_final_folder):
            os.makedirs(user_final_folder, exist_ok=True)
        upload_dir = os.path.abspath(os.path.join(UPLOAD_FOLDER, upload_id))
        final_path = os.path.abspath(os.path.join(user_final_folder, filename))
        
        # 检查所有分片是否存在
        missing_chunks = []
        for i in range(total_chunks):
            chunk_path = os.path.join(upload_dir, f'chunk_{i}')
            if not os.path.exists(chunk_path):
                missing_chunks.append(i)
        
        if missing_chunks:
            raise Exception(f'缺少分片: {missing_chunks}')
        
        # 合并分片
        with open(final_path, 'wb') as final_file:
            for i in range(total_chunks):
                chunk_path = os.path.join(upload_dir, f'chunk_{i}')
                
                with open(chunk_path, 'rb') as chunk_file:
                    final_file.write(chunk_file.read())
                
                # 更新进度
                progress = ((i + 1) / total_chunks) * 100
                self.update_state(
                    state='PROGRESS',
                    meta={'progress': progress}
                )
        
        # 验证文件大小
        actual_size = os.path.getsize(final_path)
        
        if actual_size != filesize:
            os.remove(final_path)
            raise Exception(f'文件大小不匹配: 期望{filesize}, 实际{actual_size}')
        
        # 清理临时文件
        import shutil
        shutil.rmtree(upload_dir, ignore_errors=True)
        
        # 更新数据库状态
        update_sql = """
            UPDATE upload_sessions 
            SET status = 'completed', 
                final_path = %s, 
                completed_at = %s 
            WHERE upload_id = %s
        """
        current_time = datetime.utcnow()
        dml_sql(update_sql, (final_path, current_time, upload_id))
        
        logger.info(f"合并完成: {upload_id} - {final_path}")
        
        return {
            'status': 'completed',
            'filename': filename,
            'path': final_path,
            'size': actual_size
        }
        
    except Exception as e:
        logger.error(f"合并失败: {upload_id} - {e}")
        
        # 更新失败状态
        try:
            fail_sql = "UPDATE upload_sessions SET status = 'failed' WHERE upload_id = %s"
            result = dml_sql(fail_sql, (upload_id,))
            logger.info(f"更新失败状态: {upload_id}, result={result}")
        except Exception as db_err:
            logger.error(f"更新失败状态失败: {upload_id} - {db_err}")
        
        # 如果是最后一次重试，不再重试
        if self.request.retries >= self.max_retries:
            logger.error(f"任务已达到最大重试次数: {upload_id}")
            raise
        else:
            raise self.retry(exc=e, countdown=60)