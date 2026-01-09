from flask import Blueprint,request,redirect,render_template,url_for,flash,session
from config.db_config import fetch_one,fetch_all,dml_sql


au=Blueprint('au',__name__)

@au.route('/',methods=['GET','POST'])
def index():
    if request.method == 'POST':
        username: str | None = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash(message='用户名和密码不能为空')
            return render_template(template_name_or_list='index.html')
        user = fetch_one('select * from user where username=%s and password=%s', (username, password))
        if not user:
            flash('用户名或密码错误')
            return render_template(template_name_or_list='index.html')
        session['user'] = user
        return redirect('/documentlist')
    return render_template('index.html')


@au.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # print('asdasdasd')
        username: str | None = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash(message='用户名和密码不能为空')
            return render_template(template_name_or_list='register.html')
        if fetch_one('select * from user where username=%s', (username,)):
            flash('用户名已存在')
            return redirect(url_for('au.register'))
        dml_sql('insert into user(username,password) values(%s,%s)', (username, password))
        # 注册成功后重定向到首页
        return redirect('/')
    return render_template('register.html')


@au.route('/logout', methods=['GET', 'POST'])
def logout():
    """用户退出登录"""
    session.clear()
    return redirect('/')