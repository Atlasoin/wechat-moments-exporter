# 此脚本 在 8.0.43 的微信提取的数据中可正常使用 
import json
import sqlite3
import os
import re
import base64
import urllib.request

# CHANGE IT TO YOUR OWN HASH!!!
hash = "eb8a6093b56e2f1c27fbf471ee97c7f9"

# MAGIC CONSTANTS

# 用于把 id 转换为实际 create time
magic_number = 8388607990

# 典型的 payload:
# hex = [ FLAG [ LEN | CONTENT ]]
#       |      |
#       |      |
#       |      |----- msg_payload
#       |  
#       |------------ var_payload

# wxid_xxxx 标识位
WXID_FLAG = b'\x18\x00\x20'
# 朋友圈文字内容标识位
CONTENT_FLAG = b'\xba\x01'
# 朋友圈图片标识位
IMG_FLAG = b'\x01\x10\x01\x0A'
# 朋友圈分享标题标识位（应该不需要这么长的标识位，但是先这么写着，it works for me anyway）
SHARE_TITLE_FLAG = b'\x00\xA8\x02\x00\xB8\x02\x00\x0A'
SHARE_TITLE_FLAG_2 = b'\x88\x02\x00\x2A'
# 朋友圈分享描述标识位
SHARE_DESC_FLAG = b'\x30\x00\x12'
SHARE_DESC_FLAG_2 = b'\xe8\x01\x00\x32'


# DIR CONSTANTS
my_wc_dir = "./my_wc"
assets_dir = "./assets"
assets_img_dir = "./assets/img"

moments = []
wxId = ""

def query_database(db_path, query, parameters=(), fetch_all=False):
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            res = cur.execute(query, parameters)
            return res.fetchall() if fetch_all else res.fetchone()
    except Exception as e:
        print(f"Database query error: {e}")
        return None
    
# 从缓存数据库中读取朋友圈数据，写入本地文件
def load_moments(hash):
    entries = query_database("wc005_008.db", "SELECT Buffer,Id FROM MyWC01_" + hash, fetch_all=True)
    unique_ids = set()

    for entry in entries:
        buffer, id_ = entry
        if id_ not in unique_ids:
            unique_ids.add(id_)
            with open(f"my_wc/{id_}.bin", "wb") as f:
                f.write(buffer)

    print(f"共找到朋友圈数据{len(entries)}条")


# 根据 start 和 off 截取 hex 并解码为文字
def decode_msg(hex_includes_msg, start, off):
    msg_hex = hex_includes_msg[start:start+off]
    if off == 0x00:
        return ""
    else:
        try:
            msg_str = msg_hex.decode()
            return msg_str
        except:
            print("解密失败，请手动处理")
            return "(解密失败，请手动处理)"

# msg_payload 包含文字长度和文字内容本身，从 msg_payload 中获取实际 msg 的偏移量和长度
def get_msg_off_and_len(hex_includes_msg):
    msg_len = ord(hex_includes_msg[:1])
    next_char = ord(hex_includes_msg[1:2])
    if msg_len == 0x00:
        return 1, msg_len
    if next_char >= 0x01 and next_char <= 0x1f: # in my case, <=0x07 has been all test. longer text never test. 1f here because ascii table
        increment = (next_char - 1) * 0x80
        msg_len += increment
        return 2, msg_len
    else:
        return 1, msg_len

# var_payload 包含标识位和 msg payload，从 var_payload 中解析出包含 msg_payload 的 hex 及实际 msg 的 off 和 l
def get_hex_by_flag(var_payload, flag, first=False):
    flag_index = (var_payload.index(flag) if first else var_payload.rindex(flag))+len(flag)
    hex_includes_msg = var_payload[flag_index:]
    off, l = get_msg_off_and_len(hex_includes_msg)
    return hex_includes_msg, off, l

# 从 var_payload 中解析出实际的 msg
def get_text_by_flag(var_payload, flag, first=False):
    hex_includes_msg, off, len = get_hex_by_flag(var_payload, flag, first)
    return decode_msg(hex_includes_msg, off, len)

# \xba\x01 是朋友圈文字内容的标志，后一位是发送的文字信息的长度，再后面是文字内容
def get_content(hex):
    return get_text_by_flag(hex, CONTENT_FLAG)

def get_img(hex):
    # IMG_FLAG + len
    urls = []
    # get all index of IMG_FLAG
    for img_index in re.finditer(IMG_FLAG, hex):
        i = img_index.start()
        off = i + len(IMG_FLAG)
        url_len = ord(hex[off:off+1])
        url = hex[off+1:off+1+url_len].decode()
        urls.append(url)
    
    return urls

def get_pattern1_share_title(hex):
    return get_text_by_flag(hex, SHARE_TITLE_FLAG)

def get_pattern1_share_desc(hex):
    return get_text_by_flag(hex, SHARE_DESC_FLAG)

def get_pattern_share_url(hex):
    # share url is just after share desc, so we need to get (off, l) for share desc first
    hex_includes_msg, off, l = get_hex_by_flag(hex, SHARE_DESC_FLAG)
    hex_includes_msg = hex_includes_msg[(off+l+1):]
    off, l = get_msg_off_and_len(hex_includes_msg)
    return decode_msg(hex_includes_msg, off, l)

def get_pattern2_share_title(hex):
    return get_text_by_flag(hex, SHARE_TITLE_FLAG_2)

def get_pattern2_share_desc(hex):
    return get_text_by_flag(hex, SHARE_DESC_FLAG_2)

def get_pattern3_share_title(hex):
    SHARE_PATTERN2_TITLE_FLAG = wxId.encode() + b'\x0A'
    return get_text_by_flag(hex, SHARE_PATTERN2_TITLE_FLAG)



def dl_img(url):
    url_b64 = base64.b64encode(bytes(url, 'utf-8')).decode()
    f = open(assets_img_dir + "/" +url_b64+".jpg",'wb')
    f.write(urllib.request.urlopen(url).read())
    f.close()


def extract_share_pattern1(hex):
    title = get_pattern1_share_title(hex)
    if len(title) == 0:
        raise ValueError("not pattern1")
    else:
        desc = get_pattern1_share_desc(hex)
        url = get_pattern_share_url(hex)
        return {"share_title": title, "share_desc": desc, "share_url": url}

def extract_share_pattern2(hex):
    title = get_pattern2_share_title(hex)
    desc = get_pattern2_share_desc(hex)
    url = get_pattern_share_url(hex)
    return {"share_title": title, "share_desc": desc, "share_url": url}

def extract_share_pattern3(hex):
    title = get_pattern3_share_title(hex)
    desc = get_pattern1_share_desc(hex)
    url = get_pattern_share_url(hex)
    return {"share_title": title, "share_desc": desc, "share_url": url}


def extract_moment(hex, id):
    moment = {
        "id": id,
        "content": get_content(hex),
        "images": get_img(hex),
        "publish_time": int(1000 * int(id)/magic_number)
    }

    # Attempt extraction for each share pattern
    share_patterns = [extract_share_pattern1, extract_share_pattern2, extract_share_pattern3]
    for pattern_func in share_patterns:
        try:
            share_data = pattern_func(hex)
            moment.update(share_data)
            moment["type"] = "share"
            return moment
        except Exception as e:
            pass
    
    moment["type"] = "text"
    return moment

def get_url(hex):
    imgStr = hex.decode('utf-8', errors='ignore')
    return re.findall(r'https?://(?!.*https?://).*?/0\b', imgStr)[0]


    
def load_account():
    avatar_data = query_database("WCDB_Contact.sqlite", "SELECT dbContactHeadImage from Friend WHERE userName = ?", (wxId,))
    avatar = get_url(avatar_data[0]) if avatar_data else ""
    if not avatar_data:
        print("Failed to load avatar")

    banner_data = query_database("wc005_008.db", "SELECT Buffer from WCCover WHERE userName = ?", (wxId,))
    banner = get_url(banner_data[0]) if banner_data else ""
    if not banner_data:
        print("Failed to load banner")

    nickname_data = query_database("wc005_008.db", "SELECT to_nickname from MyWC_Message01 WHERE ToUser = ?", (wxId,))
    nickname = nickname_data[0] if nickname_data else ""
    if not nickname_data:
        print("Failed to load nickname")

    account = {
        "id": wxId,
        "avatar": avatar,
        "banner": banner,
        "nickname": nickname
    }

    return account


default_option = {
    "dl_img": False,
}

def main(options=default_option):
    
    global wxId

    load_moments(hash)

    for i in os.listdir(my_wc_dir):
        with open(f"{my_wc_dir}/{i}", "rb") as f:
            hex = f.read()
            id = i[:-4]
            if len(wxId) == 0:
                wxId = get_text_by_flag(hex, WXID_FLAG, first=True)
            print(f"Parsing: {i}")
            moment = extract_moment(hex, id)
            moments.append(moment)

    account = load_account()

    print_moments(account)

    if options["dl_img"]:
        img_urls = [account["avatar"], account["banner"]]
        for moment in moments:
            for url in  moment["images"]:
                img_urls.append(url)
        l = len(img_urls)
        for i, img in enumerate(img_urls):
            print(
            "downloading image " + str(i + 1) + "/" + str(l), end=' \r')
            try:
                dl_img(img)
            except Exception as e:
                print("error downloading image " + str(i + 1) + "/" + str(l), e)
                print(img)
                continue


def set_up():
    paths = [my_wc_dir, assets_dir, assets_img_dir]
    try:
        for path in paths:
            if not os.path.exists(path):
                os.mkdir(path)
    except Exception as e:
        print("Failed to create directory:", e)

def print_moments(account):
    # sort moments by fileName
    ordered_moments = sorted(moments, key=lambda k: k['publish_time'])
    data = {
        "account": account,
        "moments": ordered_moments
    }
    with open("moments.json", "w") as f:
        f.write(json.dumps(data, ensure_ascii=False))
    print("朋友圈数据已写入 moments.json")
        

if __name__ == "__main__":
    set_up()
    main({
        "dl_img": True,
    })


    