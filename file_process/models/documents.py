from flask import Blueprint, render_template

docu=Blueprint('docu',__name__)

@docu.route('/documentlist',methods=['GET','POST'])
def documentlist():
    # 简单返回模板，数据通过前端JavaScript从API加载
    return render_template(template_name_or_list='documentlist.html')