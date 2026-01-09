from pydoc import doc
from flask import Blueprint,request,redirect,render_template,url_for,flash,session
from config.db_config import fetch_one,fetch_all,dml_sql

docp=Blueprint('docp',__name__)

@docp.route('/docprocess',methods=['GET','POST'])
def documentlist():
    # 简单返回模板，数据通过前端JavaScript从API加载
    return render_template(template_name_or_list='docprocess.html')