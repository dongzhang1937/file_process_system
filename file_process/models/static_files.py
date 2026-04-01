import os
from flask import Blueprint, send_from_directory, abort

# 创建静态文件蓝图
static_bp = Blueprint('static_files', __name__)

@static_bp.route('/images/<path:filename>')
def serve_image(filename):
    """提供图片文件服务"""
    try:
        # 获取 file_process 目录下的 images 目录
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        images_dir = os.path.join(current_dir, "images")  # file_process/images
        
        # 安全检查：确保文件路径在images目录内
        full_path = os.path.join(images_dir, filename)
        if not os.path.commonpath([images_dir, full_path]) == images_dir:
            abort(403)  # 禁止访问images目录外的文件
            
        return send_from_directory(images_dir, filename)
    except Exception as e:
        print(f"图片服务错误: {e}")
        abort(404)