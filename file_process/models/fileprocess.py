from flask import Blueprint, render_template, session

docp=Blueprint('docp',__name__)

@docp.route('/docprocess',methods=['GET','POST'])
def documentlist():
    # 简单返回模板，数据通过前端JavaScript从API加载
    return render_template(template_name_or_list='docprocess.html')

@docp.route('/settings',methods=['GET'])
def settings_page():
    """系统设置页面（所有用户可访问，部分功能按权限控制）"""
    user_info = session.get('user')
    username = user_info.get('username', 'anonymous') if user_info else 'anonymous'
    is_admin = username == 'asd'
    return render_template('settings.html', is_admin=is_admin, username=username)
