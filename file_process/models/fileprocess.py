from flask import Blueprint,request,redirect,render_template,url_for,flash,session
from config.db_config import fetch_one,fetch_all,dml_sql

docp=Blueprint('docp',__name__)

@docp.route('/docprocess',methods=['GET','POST'])
def documentlist():
    # 简单返回模板，数据通过前端JavaScript从API加载
    return render_template(template_name_or_list='docprocess.html')

@docp.route('/settings',methods=['GET'])
def settings_page():
    """系统设置页面（所有用户可访问，部分功能按权限控制）"""
    user_info = session.get('user')
    is_admin = user_info and user_info.get('username') == 'asd'
    return render_template('settings.html', is_admin=is_admin)
