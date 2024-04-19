# -*- coding: utf-8 -*-#
# -------------------------------------------------------------------------------
# Name:         chat_api.py
# Description:  
# Author:       xaoyaoo
# Date:         2024/01/02
# -------------------------------------------------------------------------------
import base64
import json
import logging
import os
import re
import time
import shutil

from flask import Flask, request, render_template, g, Blueprint, send_file, make_response, session
from pywxdump import analyzer, read_img_dat, read_audio, get_wechat_db, get_core_db
from pywxdump.analyzer.export_chat import get_contact, get_room_user_list
from pywxdump.api.rjson import ReJson, RqJson
from pywxdump.api.utils import read_session, get_session_wxids, save_session, error9999, gen_base64, validate_title
from pywxdump import read_info, VERSION_LIST, batch_decrypt, BiasAddr, merge_db, decrypt_merge, merge_real_time_db
import pywxdump
from pywxdump.dbpreprocess import wxid2userinfo, ParsingMSG, get_user_list, get_recent_user_list, ParsingMediaMSG
from pywxdump.dbpreprocess.utils import download_file

# app = Flask(__name__, static_folder='../ui/web/dist', static_url_path='/')

api = Blueprint('api', __name__, template_folder='../ui/web', static_folder='../ui/web/assets/', )
api.debug = False


@api.route('/api/init_last', methods=["GET", 'POST'])
@error9999
def init_last():
    """
    是否初始化
    :return:
    """
    my_wxid = read_session(g.sf, "test", "last")
    if my_wxid:
        merge_path = read_session(g.sf, my_wxid, "merge_path")
        wx_path = read_session(g.sf, my_wxid, "wx_path")
        key = read_session(g.sf, my_wxid, "key")
        rdata = {
            "merge_path": merge_path,
            "wx_path": wx_path,
            "key": key,
            "my_wxid": my_wxid,
            "is_init": True,
        }
        if merge_path and wx_path:
            return ReJson(0, rdata)
    return ReJson(0, {"is_init": False, "my_wxid": ""})


@api.route('/api/init_key', methods=["GET", 'POST'])
@error9999
def init_key():
    """
    初始化，包括key
    :return:
    """
    wx_path = request.json.get("wx_path", "").strip().strip("'").strip('"')
    key = request.json.get("key", "").strip().strip("'").strip('"')
    my_wxid = request.json.get("my_wxid", "").strip().strip("'").strip('"')
    if not wx_path:
        return ReJson(1002)
    if not os.path.exists(wx_path):
        return ReJson(1001, body=wx_path)
    if not key:
        return ReJson(1002)
    if not my_wxid:
        return ReJson(1002)

    out_path = os.path.join(g.tmp_path, "decrypted", my_wxid) if my_wxid else os.path.join(g.tmp_path, "decrypted")
    if os.path.exists(out_path):
        shutil.rmtree(out_path)

    code, merge_save_path = decrypt_merge(wx_path=wx_path, key=key, outpath=out_path)
    time.sleep(1)
    if code:
        save_session(g.sf, my_wxid, "merge_path", merge_save_path)
        save_session(g.sf, my_wxid, "wx_path", wx_path)
        save_session(g.sf, my_wxid, "key", key)
        save_session(g.sf, my_wxid, "my_wxid", my_wxid)
        save_session(g.sf, "test", "last", my_wxid)
        rdata = {
            "merge_path": merge_save_path,
            "wx_path": wx_path,
            "key": key,
            "my_wxid": my_wxid,
            "is_init": True,
        }
        return ReJson(0, rdata)
    else:
        return ReJson(2001, body=merge_save_path)


@api.route('/api/init_nokey', methods=["GET", 'POST'])
@error9999
def init_nokey():
    """
    初始化，包括key
    :return:
    """
    merge_path = request.json.get("merge_path", "").strip().strip("'").strip('"')
    wx_path = request.json.get("wx_path", "").strip().strip("'").strip('"')
    my_wxid = request.json.get("my_wxid", "").strip().strip("'").strip('"')

    if not wx_path:
        return ReJson(1002)
    if not os.path.exists(wx_path):
        return ReJson(1001, body=wx_path)
    if not merge_path:
        return ReJson(1002)
    if not my_wxid:
        return ReJson(1002)

    key = read_session(g.sf, my_wxid, "key")

    save_session(g.sf, my_wxid, "merge_path", merge_path)
    save_session(g.sf, my_wxid, "wx_path", wx_path)
    save_session(g.sf, my_wxid, "key", key)
    save_session(g.sf, my_wxid, "my_wxid", my_wxid)
    save_session(g.sf, "test", "last", my_wxid)
    rdata = {
        "merge_path": merge_path,
        "wx_path": wx_path,
        "key": "",
        "my_wxid": my_wxid,
        "is_init": True,
    }
    return ReJson(0, rdata)


@api.route('/api/version', methods=["GET", 'POST'])
@error9999
def version():
    """
    版本
    :return:
    """
    return ReJson(0, pywxdump.__version__)


# start 以下为聊天联系人相关api

@api.route('/api/recent_user_list', methods=["GET", 'POST'])
@error9999
def recent_user_list():
    """
    获取联系人列表
    :return:
    """
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    merge_path = read_session(g.sf, my_wxid, "merge_path")
    user_list = get_recent_user_list(merge_path, merge_path, limit=200)
    return ReJson(0, user_list)


@api.route('/api/user_list', methods=["GET", 'POST'])
@error9999
def user_list():
    """
    获取联系人列表
    :return:
    """
    if request.method == "GET":
        word = request.args.get("word", "")
    elif request.method == "POST":
        word = request.json.get("word", "")
    else:
        return ReJson(1003, msg="Unsupported method")
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    merge_path = read_session(g.sf, my_wxid, "merge_path")
    user_list = get_user_list(merge_path, merge_path, word)
    return ReJson(0, user_list)


@api.route('/api/wxid2user', methods=["GET", 'POST'])
@error9999
def wxid2user():
    """
    获取联系人列表
    :return:
    """
    if request.method == "GET":
        word = request.args.get("wxid", "")
    elif request.method == "POST":
        word = request.json.get("wxid", "")
    else:
        return ReJson(1003, msg="Unsupported method")

    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    merge_path = read_session(g.sf, my_wxid, "merge_path")
    user_info = wxid2userinfo(merge_path, merge_path, wxid=word)
    return ReJson(0, user_info)


@api.route('/api/mywxid', methods=["GET", 'POST'])
@error9999
def mywxid():
    """
    获取联系人列表
    :return:
    """
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    return ReJson(0, {"my_wxid": my_wxid})


# end 以上为聊天联系人相关api

# start 以下为聊天记录相关api

@api.route('/api/realtimemsg', methods=["GET", "POST"])
@error9999
def get_real_time_msg():
    """
    获取实时消息 使用 merge_real_time_db()函数
    :return:
    """
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")

    merge_path = read_session(g.sf, my_wxid, "merge_path")
    key = read_session(g.sf, my_wxid, "key")
    wx_path = read_session(g.sf, my_wxid, "wx_path")

    if not merge_path or not key or not wx_path or not wx_path:
        return ReJson(1002, body="msg_path or media_path or wx_path or key is required")

    db_paths = get_core_db(wx_path, ["MediaMSG", "MSG", "MicroMsg"])
    if not db_paths[0]:
        return ReJson(1001, body="media_paths or msg_paths is required")
    db_paths = db_paths[1]

    for i in db_paths:
        merge_real_time_db(key=key, db_path=i, merge_path=merge_path)
    return ReJson(0, "success")


@api.route('/api/msg_count', methods=["GET", 'POST'])
@error9999
def msg_count():
    """
    获取联系人的聊天记录数量
    :return:
    """
    if request.method == "GET":
        wxid = request.args.get("wxid")
    elif request.method == "POST":
        wxid = request.json.get("wxid")
    else:
        return ReJson(1003, msg="Unsupported method")

    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    merge_path = read_session(g.sf, my_wxid, "merge_path")
    chat_count = ParsingMSG(merge_path).msg_count(wxid)
    return ReJson(0, chat_count)


@api.route('/api/imgsrc/<path:imgsrc>', methods=["GET", 'POST'])
def get_imgsrc(imgsrc):
    """
    获取图片
    :return:
    """
    if not imgsrc:
        return ReJson(1002)

    # 将?后面的参数连接到imgsrc
    imgsrc = imgsrc + "?" + request.query_string.decode("utf-8")

    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")

    img_tmp_path = os.path.join(g.tmp_path, my_wxid, "imgsrc")
    if not os.path.exists(img_tmp_path):
        os.makedirs(img_tmp_path)
    file_name = imgsrc.replace("http://", "").replace("https://", "").replace("/", "_").replace("?", "_")
    file_name = file_name + ".jpg"
    # 如果文件名过长，则将文件明分为目录和文件名
    if len(file_name) > 255:
        file_name = file_name[:255] + "/" + file_name[255:]

    img_path_all = os.path.join(img_tmp_path, file_name)
    if os.path.exists(img_path_all):
        return send_file(img_path_all)
    else:
        download_file(imgsrc, img_path_all)
        if os.path.exists(img_path_all):
            return send_file(img_path_all)
        else:
            return ReJson(4004, body=imgsrc)


@api.route('/api/msgs', methods=["GET", 'POST'])
@error9999
def get_msgs():
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    merge_path = read_session(g.sf, my_wxid, "merge_path")

    start = request.json.get("start")
    limit = request.json.get("limit")
    wxid = request.json.get("wxid")

    if not wxid:
        return ReJson(1002, body=f"wxid is required: {wxid}")
    if start and isinstance(start, str) and start.isdigit():
        start = int(start)
    if limit and isinstance(limit, str) and limit.isdigit():
        limit = int(limit)
    if start is None or limit is None:
        return ReJson(1002, body=f"start or limit is required {start} {limit}")
    if not isinstance(start, int) and not isinstance(limit, int):
        return ReJson(1002, body=f"start or limit is not int {start} {limit}")

    parsing_msg = ParsingMSG(merge_path)
    msgs, wxid_list = parsing_msg.msg_list(wxid, start, limit)
    wxid_list.append(my_wxid)
    user_list = wxid2userinfo(merge_path, merge_path, wxid_list)
    return ReJson(0, {"msg_list": msgs, "user_list": user_list})


@api.route('/api/img/<path:img_path>', methods=["GET", 'POST'])
@error9999
def get_img(img_path):
    """
    获取图片
    :return:
    """

    if not img_path:
        return ReJson(1002)

    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    wx_path = read_session(g.sf, my_wxid, "wx_path")

    img_path = img_path.replace("\\\\", "\\")

    img_tmp_path = os.path.join(g.tmp_path, my_wxid, "img")
    original_img_path = os.path.join(wx_path, img_path)

    if os.path.exists(original_img_path):
        fomt, md5, out_bytes = read_img_dat(original_img_path)
        imgsavepath = os.path.join(img_tmp_path, img_path + "_" + ".".join([md5, fomt]))
        if not os.path.exists(os.path.dirname(imgsavepath)):
            os.makedirs(os.path.dirname(imgsavepath))
        with open(imgsavepath, "wb") as f:
            f.write(out_bytes)
        return send_file(imgsavepath)
    else:
        return ReJson(1001, body=original_img_path)


@api.route('/api/video/<path:videoPath>', methods=["GET", 'POST'])
def get_video(videoPath):
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    wx_path = read_session(g.sf, my_wxid, "wx_path")

    videoPath = videoPath.replace("\\\\", "\\")

    video_tmp_path = os.path.join(g.tmp_path, my_wxid, "video")
    original_img_path = os.path.join(wx_path, videoPath)
    if not os.path.exists(original_img_path):
        return ReJson(5002)
    # 复制文件到临时文件夹
    video_save_path = os.path.join(video_tmp_path, videoPath)
    if not os.path.exists(os.path.dirname(video_save_path)):
        os.makedirs(os.path.dirname(video_save_path))
    shutil.copy(original_img_path, video_save_path)
    return send_file(original_img_path)


@api.route('/api/audio/<path:savePath>', methods=["GET", 'POST'])
def get_audio(savePath):
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    merge_path = read_session(g.sf, my_wxid, "merge_path")

    savePath = os.path.join(g.tmp_path, my_wxid, "audio", savePath)  # 这个是从url中获取的
    if os.path.exists(savePath):
        return send_file(savePath)

    MsgSvrID = savePath.split("_")[-1].replace(".wav", "")
    if not savePath:
        return ReJson(1002)

    # 判断savePath路径的文件夹是否存在
    if not os.path.exists(os.path.dirname(savePath)):
        os.makedirs(os.path.dirname(savePath))

    parsing_media_msg = ParsingMediaMSG(merge_path)
    wave_data = parsing_media_msg.get_audio(MsgSvrID, is_play=False, is_wave=True, save_path=savePath, rate=24000)
    if not wave_data:
        return ReJson(1001, body="wave_data is required")

    if os.path.exists(savePath):
        return send_file(savePath)
    else:
        return ReJson(4004, body=savePath)


@api.route('/api/file_info', methods=["GET", 'POST'])
def get_file_info():
    file_path = request.args.get("file_path")
    file_path = request.json.get("file_path", file_path)
    if not file_path:
        return ReJson(1002)

    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    wx_path = read_session(g.sf, my_wxid, "wx_path")

    all_file_path = os.path.join(wx_path, file_path)
    if not os.path.exists(all_file_path):
        return ReJson(5002)
    file_name = os.path.basename(all_file_path)
    file_size = os.path.getsize(all_file_path)
    return ReJson(0, {"file_name": file_name, "file_size": str(file_size)})


@api.route('/api/file/<path:filePath>', methods=["GET", 'POST'])
def get_file(filePath):
    my_wxid = read_session(g.sf, "test", "last")
    if not my_wxid: return ReJson(1001, body="my_wxid is required")
    wx_path = read_session(g.sf, my_wxid, "wx_path")

    all_file_path = os.path.join(wx_path, filePath)
    if not os.path.exists(all_file_path):
        return ReJson(5002)
    return send_file(all_file_path)


# end 以上为聊天记录相关api

@api.route('/api/msgs_user_list', methods=['GET', 'POST'])
@error9999
def get_msg_user_list():
    """
    获取消息联系人列表
    :return:
    """
    msg_path = request.headers.get("msg_path")
    micro_path = request.headers.get("micro_path")
    if not msg_path:
        msg_path = read_session(g.sf, "msg_path")
    if not micro_path:
        micro_path = read_session(g.sf, "micro_path")
    wxid = request.json.get("wxid")
    # msg_list = analyzer.get_msg_list(msg_path, wxid, start_index=start, page_size=limit)
    my_wxid = read_session(g.sf, "my_wxid")
    userlist = []
    if wxid.endswith("@chatroom"):
        # 群聊
        userlist = get_room_user_list(msg_path, wxid)
    else:
        # 单聊
        user = get_contact(micro_path, wxid)
        my_user = get_contact(micro_path, my_wxid)
        userlist.append(user)
        userlist.append(my_user)
    return ReJson(0, {"user_list": userlist})


@api.route('/api/msgs_list', methods=['GET', 'POST'])
@error9999
def get_msg_list():
    msg_path = request.headers.get("msg_path")
    micro_path = request.headers.get("micro_path")
    if not msg_path:
        msg_path = read_session(g.sf, "msg_path")
    if not micro_path:
        micro_path = read_session(g.sf, "micro_path")
    start = request.json.get("start")
    limit = request.json.get("limit")
    wxid = request.json.get("wxid")
    my_wxid = read_session(g.sf, "test", "last")
    msg_list = analyzer.get_msg_list(msg_path, wxid, start_index=start, page_size=limit)
    return ReJson(0, {"msg_list": msg_list, 'my_wxid': my_wxid})


def func_get_msgs(start, limit, wxid, msg_path, micro_path):
    msg_list = analyzer.get_msg_list(msg_path, wxid, start_index=start, page_size=limit)
    # row_data = {"MsgSvrID": MsgSvrID, "type_name": type_name, "is_sender": IsSender, "talker": talker,
    #             "room_name": StrTalker, "content": content, "CreateTime": CreateTime}
    if "merge_all" in micro_path:
        contact_list = analyzer.get_contact_list(micro_path, micro_path)
    else:
        contact_list = analyzer.get_contact_list(micro_path)

    userlist = {}
    my_wxid = read_session(g.sf, "my_wxid")
    if wxid.endswith("@chatroom"):
        # 群聊
        talkers = [msg["talker"] for msg in msg_list] + [wxid, my_wxid]
        talkers = list(set(talkers))
        for user in contact_list:
            if user["username"] in talkers:
                userlist[user["username"]] = user
    else:
        # 单聊
        for user in contact_list:
            if user["username"] == wxid or user["username"] == my_wxid:
                userlist[user["username"]] = user
            if len(userlist) == 2:
                break
    return {"msg_list": msg_list, "user_list": userlist, "my_wxid": my_wxid}


# 导出聊天记录
@api.route('/api/export', methods=["GET", 'POST'])
@error9999
def export():
    """
    导出聊天记录
    :return:
    """
    export_type = request.json.get("export_type")
    start_time = request.json.get("start_time", 0)
    end_time = request.json.get("end_time", 0)
    chat_type = request.json.get("chat_type")
    username = request.json.get("username")
    wx_path = request.json.get("wx_path", read_session(g.sf, "wx_path"))
    key = request.json.get("key", read_session(g.sf, "key"))

    if not export_type or not isinstance(export_type, str):
        return ReJson(1002)

    # 导出路径
    outpath = os.path.join(g.tmp_path, "export", export_type)
    if not os.path.exists(outpath):
        os.makedirs(outpath)

    if export_type == "endb":  # 导出加密数据库
        # 获取微信文件夹路径
        if not wx_path:
            return ReJson(1002)
        if not os.path.exists(wx_path):
            return ReJson(1001, body=wx_path)

        # 分割wx_path的文件名和父目录
        code, wxdbpaths = get_core_db(wx_path)
        if not code:
            return ReJson(2001, body=wxdbpaths)

        for wxdb in wxdbpaths:
            # 复制wxdb->outpath, os.path.basename(wxdb)
            shutil.copy(wxdb, os.path.join(outpath, os.path.basename(wxdb)))
        return ReJson(0, body=outpath)

    elif export_type == "dedb":
        if isinstance(start_time, int) and isinstance(end_time, int):
            msg_path = read_session(g.sf, "msg_path")
            micro_path = read_session(g.sf, "micro_path")
            media_path = read_session(g.sf, "media_path")
            dbpaths = [msg_path, media_path, micro_path]
            dbpaths = list(set(dbpaths))
            mergepath = merge_db(dbpaths, os.path.join(outpath, "merge.db"), start_time, end_time)
            return ReJson(0, body=mergepath)
            # if msg_path == media_path and msg_path == media_path:
            #     shutil.copy(msg_path, os.path.join(outpath, "merge.db"))
            #     return ReJson(0, body=msg_path)
            # else:
            #     dbpaths = [msg_path, msg_path, micro_path]
            #     dbpaths = list(set(dbpaths))
            #     mergepath = merge_db(dbpaths, os.path.join(outpath, "merge.db"), start_time,  end_time)
            #     return ReJson(0, body=mergepath)
        else:
            return ReJson(1002, body={"start_time": start_time, "end_time": end_time})

    elif export_type == "csv":
        outpath = os.path.join(outpath, username)
        if not os.path.exists(outpath):
            os.makedirs(outpath)
        code, ret = analyzer.export_csv(username, outpath, read_session(g.sf, "msg_path"))
        if code:
            return ReJson(0, ret)
        else:
            return ReJson(2001, body=ret)
    elif export_type == "json":
        outpath = os.path.join(outpath, username)
        if not os.path.exists(outpath):
            os.makedirs(outpath)
        code, ret = analyzer.export_json(username, outpath, read_session(g.sf, "msg_path"))
        if code:
            return ReJson(0, ret)
        else:
            return ReJson(2001, body=ret)
    elif export_type == "html":
        outpath = os.path.join(outpath, username)
        if os.path.exists(outpath):
            shutil.rmtree(outpath)
        if not os.path.exists(outpath):
            os.makedirs(outpath)
        # chat_type_tups = []
        # for ct in chat_type:
        #     tup = analyzer.get_name_typeid(ct)
        #     if tup:
        #         chat_type_tups += tup
        # if not chat_type_tups:
        #     return ReJson(1002)

        # 复制文件 html
        export_html = os.path.join(os.path.dirname(pywxdump.VERSION_LIST_PATH), "ui", "export")
        indexhtml_path = os.path.join(export_html, "index.html")
        assets_path = os.path.join(export_html, "assets")
        if not os.path.exists(indexhtml_path) or not os.path.exists(assets_path):
            return ReJson(1001)
        js_path = ""
        css_path = ""
        for file in os.listdir(assets_path):
            if file.endswith('.js'):
                js_path = os.path.join(assets_path, file)
            elif file.endswith('.css'):
                css_path = os.path.join(assets_path, file)
            else:
                continue
        # 读取html,js,css
        with open(indexhtml_path, 'r', encoding='utf-8') as f:
            html = f.read()
        with open(js_path, 'r', encoding='utf-8') as f:
            js = f.read()
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()

        html = re.sub(r'<script .*?></script>', '', html)  # 删除所有的script标签
        html = re.sub(r'<link rel="stylesheet" .*?>', '', html)  # 删除所有的link标签

        html = html.replace('</head>', f'<style>{css}</style></head>')
        html = html.replace('</head>', f'<script type="module" crossorigin>{js}</script></head>')
        # END 生成index.html

        rdata = func_get_msgs(0, 10000000, username, "", "")

        msg_list = rdata["msg_list"]
        for i in range(len(msg_list)):
            if msg_list[i]["type_name"] == "语音":
                savePath = msg_list[i]["content"]["src"]
                MsgSvrID = savePath.split("_")[-1].replace(".wav", "")
                if not savePath:
                    continue
                media_path = read_session(g.sf, "media_path")
                wave_data = read_audio(MsgSvrID, is_wave=True, DB_PATH=media_path)
                if not wave_data:
                    continue
                # 判断savePath路径的文件夹是否存在
                savePath = os.path.join(outpath, savePath)
                if not os.path.exists(os.path.dirname(savePath)):
                    os.makedirs(os.path.dirname(savePath))
                with open(savePath, "wb") as f:
                    f.write(wave_data)
            elif msg_list[i]["type_name"] == "图片":
                img_path = msg_list[i]["content"]["src"]
                wx_path = read_session(g.sf, "wx_path")
                img_path_all = os.path.join(wx_path, img_path)

                if os.path.exists(img_path_all):
                    fomt, md5, out_bytes = read_img_dat(img_path_all)
                    imgsavepath = os.path.join(outpath, "img", img_path + "_" + ".".join([md5, fomt]))
                    if not os.path.exists(os.path.dirname(imgsavepath)):
                        os.makedirs(os.path.dirname(imgsavepath))
                    with open(imgsavepath, "wb") as f:
                        f.write(out_bytes)
                    msg_list[i]["content"]["src"] = os.path.join("img", img_path + "_" + ".".join([md5, fomt]))

        rdata["msg_list"] = msg_list
        rdata["myuserdata"] = rdata["user_list"][rdata["my_wxid"]]
        rdata["myuserdata"]["chat_count"] = len(rdata["msg_list"])
        save_data = rdata
        save_json_path = os.path.join(outpath, "data")
        if not os.path.exists(save_json_path):
            os.makedirs(save_json_path)
        with open(os.path.join(save_json_path, "msg_user.json"), "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False)

        json_base64 = gen_base64(os.path.join(save_json_path, "msg_user.json"))
        html = html.replace('"./data/msg_user.json"', f'"{json_base64}"')

        with open(os.path.join(outpath, "index.html"), 'w', encoding='utf-8') as f:
            f.write(html)
        return ReJson(0, outpath)

    elif export_type == "pdf":
        pass
    elif export_type == "docx":
        pass
    else:
        return ReJson(1002)

    return ReJson(9999, "")


# 这部分为专业工具的api
@api.route('/api/wxinfo', methods=["GET", 'POST'])
@error9999
def get_wxinfo():
    """
    获取微信信息
    :return:
    """
    import pythoncom
    pythoncom.CoInitialize()
    wxinfos = read_info(VERSION_LIST)
    pythoncom.CoUninitialize()
    return ReJson(0, wxinfos)


@api.route('/api/decrypt', methods=["GET", 'POST'])
@error9999
def decrypt():
    """
    解密
    :return:
    """
    key = request.json.get("key")
    if not key:
        return ReJson(1002)
    wxdb_path = request.json.get("wxdbPath")
    if not wxdb_path:
        return ReJson(1002)
    out_path = request.json.get("outPath")
    if not out_path:
        out_path = g.tmp_path
    wxinfos = batch_decrypt(key, wxdb_path, out_path=out_path)
    return ReJson(0, str(wxinfos))


@api.route('/api/biasaddr', methods=["GET", 'POST'])
@error9999
def biasaddr():
    """
    BiasAddr
    :return:
    """
    mobile = request.json.get("mobile")
    name = request.json.get("name")
    account = request.json.get("account")
    key = request.json.get("key", "")
    wxdbPath = request.json.get("wxdbPath", "")
    if not mobile or not name or not account:
        return ReJson(1002)
    rdata = BiasAddr(account, mobile, name, key, wxdbPath).run()
    return ReJson(0, str(rdata))


@api.route('/api/merge', methods=["GET", 'POST'])
@error9999
def merge():
    """
    合并
    :return:
    """
    wxdb_path = request.json.get("dbPath")
    if not wxdb_path:
        return ReJson(1002)
    out_path = request.json.get("outPath")
    if not out_path:
        return ReJson(1002)
    rdata = merge_db(wxdb_path, out_path)
    return ReJson(0, str(rdata))


# END 这部分为专业工具的api

# 关于、帮助、设置
@api.route('/api/check_update', methods=["GET", 'POST'])
@error9999
def check_update():
    """
    检查更新
    :return:
    """
    url = "https://api.github.com/repos/xaoyaoo/PyWxDump/tags"
    try:
        import requests
        res = requests.get(url)
        if res.status_code == 200:
            data = res.json()
            NEW_VERSION = data[0].get("name")
            if NEW_VERSION[1:] != pywxdump.__version__:
                msg = "有新版本"
            else:
                msg = "已经是最新版本"
            return ReJson(0, body={"msg": msg, "latest_version": NEW_VERSION,
                                   "latest_url": "https://github.com/xaoyaoo/PyWxDump/releases/tag/" + NEW_VERSION})
        else:
            return ReJson(2001, body="status_code is not 200")
    except Exception as e:
        return ReJson(9999, msg=str(e))


# END 关于、帮助、设置


@api.route('/')
@error9999
def index():
    return render_template('index.html')
