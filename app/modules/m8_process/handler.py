from flask import Blueprint
from app.web import api,page
bp=Blueprint('m8_process',__name__)
@bp.get('/m8_process')
def screen():return page(7,'m8_process.html')
@bp.route('/api/m8_process',methods=['GET','POST'])
def preview():return api(8)
