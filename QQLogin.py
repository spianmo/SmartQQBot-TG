# -*- coding: utf-8 -*-

# Code by Yinzo:        https://github.com/Yinzo
# Origin repository:    https://github.com/Yinzo/SmartQQBot


import time
import datetime
import re
import json
import logging
import thread as _thread
from PIL import Image

from Configs import *
from Msg import *
from Notify import *
from HttpClient import *


def init_logging():
    logging.basicConfig(
        filename='smartqq.log',
        level=logging.DEBUG,
        format='%(asctime)s  %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
        datefmt='%a, %d %b %Y %H:%M:%S',
    )

    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s  %(filename)s[line:%(lineno)d] %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(handler)


def display_QRCode(path):
    img = Image.open(path)
    img.show()


def get_revalue(html, rex, er, ex):
    v = re.search(rex, html)

    if v is None:

        if ex:
            logging.error(er)
            raise TypeError(er)
        else:
            logging.warning(er)
        return ''

    return v.group(1)


def date_to_millis(d):
    return int(time.mktime(d.timetuple())) * 1000


class QQ:
    def __init__(self):
        self.default_config = DefaultConfigs()
        self.req = HttpClient()

        # cache
        self.friend_list = {}
        self.__groupSig_list = {}
        self.__self_info = {}

        self.client_id = 53999199
        self.ptwebqq = ''
        self.psessionid = ''
        self.appid = 0
        self.vfwebqq = ''
        self.qrcode_path = self.default_config.conf.get("global", "qrcode_path")  # QRCode保存路径
        self.username = ''
        self.account = 0

        init_logging()

    def __hash_digest(self, uin, ptwebqq):
        """
        计算hash，貌似TX的这个算法会经常变化，暂时不使用
        get_user_friends2, get_group_name_list_mask2 会依赖此数据
        提取自http://pub.idqqimg.com/smartqq/js/mq.js
        :param uin:
        :param ptwebqq:
        :return:
        """
        N = [0, 0, 0, 0]
        # print(N[0])
        for t in range(len(ptwebqq)):
            N[t % 4] ^= ord(ptwebqq[t])
        U = ["EC", "OK"]
        V = [0, 0, 0, 0]
        V[0] = int(uin) >> 24 & 255 ^ ord(U[0][0])
        V[1] = int(uin) >> 16 & 255 ^ ord(U[0][1])
        V[2] = int(uin) >> 8 & 255 ^ ord(U[1][0])
        V[3] = int(uin) & 255 ^ ord(U[1][1])
        U = [0, 0, 0, 0, 0, 0, 0, 0]
        for T in range(8):
            if T % 2 == 0:
                U[T] = N[T >> 1]
            else:
                U[T] = V[T >> 1]
        N = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "C", "D", "E", "F"]
        V = ""
        for T in range(len(U)):
            V += N[U[T] >> 4 & 15]
            V += N[U[T] & 15]
        return V

    def __getGroupSig(self, guin, tuin, service_type=0):
        key = '%s --> %s' % (guin, tuin)
        if key not in self.__groupSig_list:
            url = "http://d1.web2.qq.com/channel/get_c2cmsg_sig2?id=%s&to_uin=%s&service_type=%s&clientid=%s&psessionid=%s&t=%d" % (
                guin, tuin, service_type, self.client_id, self.psessionid, int(time.time() * 100))
            response = self.req.Get(url)
            rsp_json = json.loads(response)
            if rsp_json["retcode"] != 0:
                return ""
            sig = rsp_json["result"]["value"]
            self.__groupSig_list[key] = sig
        if key in self.__groupSig_list:
            return self.__groupSig_list[key]
        return ""

    def __login(self, times=10):
        login_error = 1
        while login_error > 0:
            try:
                logging.info("Tring to login in with cookies. {0}".format(login_error))
                print('Tring to auto login in.')
                self.ptwebqq = self.req.getCookie('ptwebqq')

                html = self.req.Post('http://d1.web2.qq.com/channel/login2', {
                    'r': '{{"ptwebqq":"{0}","clientid":{1},"psessionid":"{2}","status":"online"}}'.format(self.ptwebqq,
                                                                                                          self.client_id,
                                                                                                          self.psessionid)
                }, self.default_config.conf.get("global", "connect_referer"))
                logging.debug("login html:  " + str(html))
                ret = json.loads(html)

                html2 = self.req.Get(
                        "http://s.web2.qq.com/api/getvfwebqq?ptwebqq={0}&clientid={1}&psessionid={2}&t={3}".format(
                                self.ptwebqq,
                                self.client_id,
                                self.psessionid,
                                self.req.getTimeStamp()
                        ))
                logging.debug("getvfwebqq html:  " + str(html2))
                ret2 = json.loads(html2)

                if (ret['retcode'] != 0) or (ret2['retcode'] != 0):
                    logging.debug(str(ret))
                    logging.debug(str(ret2))
                    logging.warning(
                        "login2 retcode: {login2}, getvfwebqq retcode: {getvfwebqq}".format(login2=str(ret['retcode']),
                                                                                            getvfwebqq=str(
                                                                                                    ret2['retcode'])))
                    raise

                self.psessionid = ret['result']['psessionid']
                self.account = ret['result']['uin']
                self.vfwebqq = ret2['result']['vfwebqq']
                logging.info("Login successfully.")
                print('Login successfully.')
                return True
            except:
                login_error += 1
                logging.info("login fail, retrying...")
                print('auto login fail')
                if login_error > times:
                    return False

    def __login_by_qrcode(self):
        try:
            logging.info("Trying to login by qrcode.")
            logging.info("Requesting the qrcode login pages...")
            initurl_html = self.req.Get(self.default_config.conf.get("global", "smartqq_url"))
            logging.debug("login page html: " + str(initurl_html))
            initurl = get_revalue(initurl_html, r'\.src = "(.+?)"', "Get Login Url Error.", 1)
            html = self.req.Get(initurl + '0')

            appid = get_revalue(html, r'<input type="hidden" name="aid" value="(\d+)" />', 'Get AppId Error', 1)
            sign = get_revalue(html, r'g_login_sig=encodeURIComponent\("(.*?)"\)', 'Get Login Sign Error', 0)
            js_ver = get_revalue(html, r'g_pt_version=encodeURIComponent\("(\d+)"\)', 'Get g_pt_version Error', 1)
            mibao_css = get_revalue(html, r'g_mibao_css=encodeURIComponent\("(.+?)"\)', 'Get g_mibao_css Error', 1)

            star_time = date_to_millis(datetime.datetime.utcnow())

            error_times = 0
            ret = []
            while True:
                error_times += 1
                print('download QR code image...')
                self.req.Download('https://ssl.ptlogin2.qq.com/ptqrshow?appid={0}&e=0&l=L&s=8&d=72&v=4'.format(appid),
                                  self.qrcode_path)
                logging.info("Please scan the downloaded QRCode")
                _thread.start_new_thread(display_QRCode, (self.qrcode_path,))

                while True:
                    html = self.req.Get(
                            'https://ssl.ptlogin2.qq.com/ptqrlogin?webqq_type=10&remember_uin=1&login2qq=1&aid={0}&u1=http%3A%2F%2Fw.qq.com%2Fproxy.html%3Flogin2qq%3D1%26webqq_type%3D10&ptredirect=0&ptlang=2052&daid=164&from_ui=1&pttype=1&dumy=&fp=loginerroralert&action=0-0-{1}&mibao_css={2}&t=undefined&g=1&js_type=0&js_ver={3}&login_sig={4}'.format(
                                    appid, date_to_millis(datetime.datetime.utcnow()) - star_time, mibao_css, js_ver,
                                    sign),
                            initurl)
                    logging.debug("QRCode check html:   " + str(html))
                    ret = html.split("'")
                    if ret[1] in ('0', '65'):  # 65: QRCode 失效, 0: 验证成功, 66: 未失效, 67: 验证中
                        break
                    time.sleep(1)
                if ret[1] == '0' or error_times > 10:
                    break

            if ret[1] != '0':
                return False

            # 删除QRCode文件
            if os.path.exists(self.qrcode_path):
                os.remove(self.qrcode_path)

            html = self.req.Get(ret[5])
            logging.debug("mibao_res html:  " + str(html))
            return True
        except:
            logging.info("qr login fail")
            print('qr login fail')
            return False

    def login(self):
        if not self.__login(1):
            while True:
                if self.__login_by_qrcode():
                    if self.__login(): break
        ret = self.get_self_info2()
        self.username = ret['nick']

        logging.info("QQ：{0} login successfully, Username：{1}".format(self.account, self.username))

    def check_msg(self, error_times=0):
        if error_times >= 5:
            if not self.__login(1):
                raise IOError("Account offline.")
            else:
                error_times = 0

        # 调用后进入单次轮询，等待服务器发回状态。
        html = self.req.Post('http://d1.web2.qq.com/channel/poll2', {
            'r': '{{"ptwebqq":"{ptwebqq}","clientid":{clientid},"psessionid":"{psessionid}","key":""}}'.format(
                psessionid=self.psessionid,
                ptwebqq=self.ptwebqq,
                clientid=self.client_id)
        }, self.default_config.conf.get("global", "connect_referer"))
        logging.debug("check_msg html:  " + str(html))
        try:
            if html == "":
                return self.check_msg()
            ret = json.loads(html)

            ret_code = ret['retcode']

            # if ret_code in (0,):
            #     logging.info("received retcode: " + str(ret_code) + ": No message.")
            #     time.sleep(1)
            #     return

            if ret_code in (103,):
                logging.warning("received retcode: " + str(ret_code) + ": Check error.retrying.." + str(error_times))
                time.sleep(1)
                return self.check_msg(error_times + 1)

            if ret_code in (121,):
                logging.warning("received retcode: " + str(ret_code))
                return self.check_msg(5)

            elif ret_code == 0:
                if 'result' not in ret or len(ret['result']) == 0:
                    logging.info("received retcode: " + str(ret_code) + ": No message.")
                    time.sleep(1)
                    return
                msg_list = []
                pm_list = []
                sess_list = []
                group_list = []
                notify_list = []
                for msg in ret['result']:
                    ret_type = msg['poll_type']
                    if ret_type == 'message':
                        pm_list.append(PmMsg(msg))
                    elif ret_type == 'group_message':
                        group_list.append(GroupMsg(msg))
                    elif ret_type == 'sess_message':
                        sess_list.append(SessMsg(msg))
                    elif ret_type == 'input_notify':
                        notify_list.append(InputNotify(msg))
                    elif ret_code == 'kick_message':
                        notify_list.append(KickMessage(msg))
                    else:
                        logging.warning("unknown message type: " + str(ret_type) + "details:    " + str(msg))

                group_list.sort(key=lambda x: x.msg_id)
                msg_list += pm_list + sess_list + group_list + notify_list
                if not msg_list:
                    return
                return msg_list

            elif ret_code == 100006:
                logging.warning("POST data error")
                return

            elif ret_code == 116:
                self.ptwebqq = ret['p']
                logging.info("ptwebqq updated.")
                return

            else:
                logging.warning("unknown retcode " + str(ret_code))
                return

        except ValueError as e:
            logging.warning("Check error occured: " + str(e))
            time.sleep(1)
            return self.check_msg(error_times + 1)

        except BaseException as e:
            logging.warning("Unknown check error occured, retrying. Error: " + str(e))
            time.sleep(1)
            return self.check_msg(error_times + 1)

    def uin_to_account(self, tuin):
        """
        将uin转换成用户QQ号
        :param tuin:
        :return:str 用户昵称
        """
        uin_str = str(tuin)
        try:
            logging.info("Requesting the account by uin:    " + str(tuin))
            info = json.loads(self.req.Get(
                    'http://s.web2.qq.com/api/get_friend_uin2?tuin={0}&type=1&vfwebqq={1}&t={2}'.format(uin_str,
                                                                                                        self.vfwebqq,
                                                                                                        self.req.getTimeStamp()),
                    self.default_config.conf.get("global", "connect_referer")))
            logging.debug("uin_to_account html:    " + str(info))
            if info['retcode'] != 0:
                raise TypeError('uin_to_account retcode error')
            info = info['result']['account']
            return info

        except:
            logging.exception("uin_to_account")
            return None

    # 获取自己的信息
    def get_self_info2(self):
        """
        获取自己的信息
        get_self_info2
        {"retcode":0,"result":{"birthday":{"month":1,"year":1989,"day":30},"face":555,"phone":"","occupation":"","allow":1,"college":"","uin":2609717081,"blood":0,"constel":1,"lnick":"","vfwebqq":"68b5ff5e862ac589de4fc69ee58f3a5a9709180367cba3122a7d5194cfd43781ada3ac814868b474","homepage":"","vip_info":0,"city":"青岛","country":"中国","personal":"","shengxiao":5,"nick":"要有光","email":"","province":"山东","account":2609717081,"gender":"male","mobile":""}}
        :return:dict
        """
        if not self.__self_info:
            url = "http://s.web2.qq.com/api/get_self_info2"
            response = self.req.Get(url)
            rsp_json = json.loads(response)
            if rsp_json["retcode"] != 0:
                return {}
            self.__self_info = rsp_json["result"]
        return self.__self_info

    # 获取好友详情信息
    def get_friend_info2(self, tuin):
        """
        获取好友详情信息
        get_friend_info2
        {"retcode":0,"result":{"face":0,"birthday":{"month":1,"year":1989,"day":30},"occupation":"","phone":"","allow":1,"college":"","uin":3964575484,"constel":1,"blood":3,"homepage":"http://blog.lovewinne.com","stat":20,"vip_info":0,"country":"中国","city":"","personal":"","nick":" 信","shengxiao":5,"email":"John123951@126.com","province":"山东","gender":"male","mobile":"158********"}}
        :return:dict
        """
        uin_str = str(tuin)
        try:
            logging.info("Requesting the account info by uin:    " + str(tuin))
            info = json.loads(self.req.Get(
                    'http://s.web2.qq.com/api/get_friend_info2?tuin={0}&vfwebqq={1}&clientid={2}&psessionid={3}&t={4}'
                        .format(
                            uin_str,
                            self.vfwebqq,
                            self.client_id,
                            self.psessionid,
                            self.req.getTimeStamp()),
            ))
            logging.debug("get_friend_info2 html:    " + str(info))
            if info['retcode'] != 0:
                raise TypeError('get_friend_info2 result error')
            info = info['result']
            return info

        except:
            logging.exception("get_friend_info2")
            return None

    # 获取好友详情信息
    def get_friend_info(self, tuin):
        uin_str = str(tuin)
        if uin_str not in self.friend_list:
            info = self.get_friend_info2(tuin) or {'nick': '群用户'}
            info['account'] = self.uin_to_account(tuin)
            self.friend_list[uin_str] = info

        try:
            return '【{0}({1})】'.format(self.friend_list[uin_str]['nick'], self.friend_list[uin_str]['account'])
        except:
            logging.warning("get_friend_info return fail.")
            logging.debug("now uin list:    " + str(self.friend_list[uin_str]))

    # 获取好友的签名信息
    def get_single_long_nick2(self, tuin):
        """
        获取好友的签名信息
        get_single_long_nick2
        {"retcode":0,"result":[{"uin":3964575484,"lnick":"幸福，知道自己在哪里，知道下一个目标在哪里，心不累~"}]}
        :return:dict
        """
        url = "http://s.web2.qq.com/api/get_single_long_nick2?tuin=%s&vfwebqq=%s&t=%s" % (
            tuin, self.vfwebqq, int(time.time() * 100))
        response = self.req.Get(url)
        rsp_json = json.loads(response)
        if rsp_json["retcode"] != 0:
            return {}
        return rsp_json["result"]

    #获取群列表信息
    '''
    def get_group_name_list(self, vfwebqq):   
        try:   
            url="http://s.web2.qq.com/api/get_group_name_list_mask2"   
            postdata="r=%7B%22vfwebqq%22%3A%22{$vfwebqq}%22%7D"   
            postdatapostdata=postdata.replace("{$vfwebqq}",vfwebqq)   
            ret=self.Post(url,postdata,QQRobot.HOST[1],QQRobot.REFERER[1],QQRobot.ORIGIN[1])   
            print 'Step5: GetGroupList'   
            retjson=json.loads(ret)   
            retjsonretjson=retjson["result"]   
            self.grouplist=retjson   
            for group in self.grouplist['gnamelist']:   
                print group["code"],group["name"]   
                   
        except Exception,e:   
            print "GetGroupNameList error"+str(e)
    '''

    # 获取群信息（对于易变的信息，请在外层做缓存处理）
    def get_group_info_ext2(self, gcode):
        """
        获取群信息
        get_group_info_ext2
        {"retcode":0,"result":{"stats":[],"minfo":[{"nick":" 信","province":"山东","gender":"male","uin":3964575484,"country":"中国","city":""},{"nick":"崔震","province":"","gender":"unknown","uin":2081397472,"country":"","city":""},{"nick":"云端的猫","province":"山东","gender":"male","uin":3123065696,"country":"中国","city":"青岛"},{"nick":"要有光","province":"山东","gender":"male","uin":2609717081,"country":"中国","city":"青岛"},{"nick":"小莎机器人","province":"广东","gender":"female","uin":495456232,"country":"中国","city":"深圳"}],"ginfo":{"face":0,"memo":"http://hujj009.ys168.com\r\n0086+区(没0)+电话\r\n0086+手机\r\nhttp://john123951.xinwen365.net/qq/index.htm","class":395,"fingermemo":"","code":3943922314,"createtime":1079268574,"flag":16778241,"level":0,"name":"ぁQQぁ","gid":3931577475,"owner":3964575484,"members":[{"muin":3964575484,"mflag":192},{"muin":2081397472,"mflag":65},{"muin":3123065696,"mflag":128},{"muin":2609717081,"mflag":0},{"muin":495456232,"mflag":0}],"option":2},"cards":[{"muin":3964575484,"card":"●s.Εx2(22222)□"},{"muin":495456232,"card":"小莎机器人"}],"vipinfo":[{"vip_level":0,"u":3964575484,"is_vip":0},{"vip_level":0,"u":2081397472,"is_vip":0},{"vip_level":0,"u":3123065696,"is_vip":0},{"vip_level":0,"u":2609717081,"is_vip":0},{"vip_level":0,"u":495456232,"is_vip":0}]}}
        :return:dict
        """
        if gcode == 0:
            return {}
        try:
            url = "http://s.web2.qq.com/api/get_group_info_ext2?gcode=%s&vfwebqq=%s&t=%s" % (
                gcode, self.vfwebqq, int(time.time() * 100))
            response = self.req.Get(url)
            rsp_json = json.loads(response)
            if rsp_json["retcode"] != 0:
                return {}
            return rsp_json["result"]
        except Exception as ex:
            logging.warning("get_group_info_ext2. Error: " + str(ex))
            return {}

    # 发送群消息
    def send_qun_msg(self, guin, reply_content, msg_id, fail_times=0):
        fix_content = str(reply_content.replace("\\", "\\\\\\\\").replace("\n", "\\\\n").replace("\t", "\\\\t"))
        rsp = ""
        try:
            req_url = "http://d1.web2.qq.com/channel/send_qun_msg2"
            data = (
                ('r',
                 '{{"group_uin":{0}, "face":564,"content":"[\\"{4}\\",[\\"font\\",{{\\"name\\":\\"Arial\\",\\"size\\":\\"10\\",\\"style\\":[0,0,0],\\"color\\":\\"000000\\"}}]]","clientid":{1},"msg_id":{2},"psessionid":"{3}"}}'.format(
                         guin, self.client_id, msg_id, self.psessionid, fix_content)),
                ('clientid', self.client_id),
                ('psessionid', self.psessionid)
            )
            rsp = self.req.Post(req_url, data, self.default_config.conf.get("global", "connect_referer"))
            rsp_json = json.loads(rsp)
            if 'retcode' in rsp_json and rsp_json['retcode'] != 0:
                raise ValueError("reply group chat error" + str(rsp_json['retcode']))
            logging.info("send_qun_msg: Reply successfully.")
            logging.debug("send_qun_msg: Reply response: " + str(rsp))
            return rsp_json
        except:
            logging.exception("send_qun_msg exception")
            if fail_times < 5:
                logging.warning("send_qun_msg: Response Error.Wait for 2s and Retrying." + str(fail_times))
                logging.debug(rsp)
                time.sleep(2)
                self.send_qun_msg(guin, reply_content, msg_id, fail_times + 1)
            else:
                logging.warning("send_qun_msg: Response Error over 5 times.Exit.reply content:" + str(reply_content))
                return False

    # 发送私密消息
    def send_buddy_msg(self, tuin, reply_content, msg_id, fail_times=0):
        fix_content = str(reply_content.replace("\\", "\\\\\\\\").replace("\n", "\\\\n").replace("\t", "\\\\t"))
        rsp = ""
        try:
            req_url = "http://d1.web2.qq.com/channel/send_buddy_msg2"
            data = (
                ('r',
                 '{{"to":{0}, "face":594, "content":"[\\"{4}\\", [\\"font\\", {{\\"name\\":\\"Arial\\", \\"size\\":\\"10\\", \\"style\\":[0, 0, 0], \\"color\\":\\"000000\\"}}]]", "clientid":{1}, "msg_id":{2}, "psessionid":"{3}"}}'.format(
                         tuin, self.client_id, msg_id, self.psessionid, fix_content)),
                ('clientid', self.client_id),
                ('psessionid', self.psessionid)
            )
            rsp = self.req.Post(req_url, data, self.default_config.conf.get("global", "connect_referer"))
            rsp_json = json.loads(rsp)
            if 'errCode' in rsp_json and rsp_json['errCode'] != 0:
                raise ValueError("reply pmchat error" + str(rsp_json['retcode']))
            logging.info("Reply successfully.")
            logging.debug("Reply response: " + str(rsp))
            return rsp_json
        except:
            if fail_times < 5:
                logging.warning("Response Error.Wait for 2s and Retrying." + str(fail_times))
                logging.debug(rsp)
                time.sleep(2)
                self.send_buddy_msg(tuin, reply_content, msg_id, fail_times + 1)
            else:
                logging.warning("Response Error over 5 times.Exit.reply content:" + str(reply_content))
                return False

    # 发送临时消息
    def send_sess_msg2(self, tuin, reply_content, msg_id, group_sig, service_type=0, fail_times=0):
        fix_content = str(reply_content.replace("\\", "\\\\\\\\").replace("\n", "\\\\n").replace("\t", "\\\\t"))
        rsp = ""
        try:
            req_url = "http://d1.web2.qq.com/channel/send_sess_msg2"
            data = (
                ('r',
                 '{{"to":{0}, "face":594, "content":"[\\"{4}\\", [\\"font\\", {{\\"name\\":\\"Arial\\", \\"size\\":\\"10\\", \\"style\\":[0, 0, 0], \\"color\\":\\"000000\\"}}]]", "clientid":{1}, "msg_id":{2}, "psessionid":"{3}", "group_sig":"{5}", "service_type":{6}}}'.format(
                         tuin,
                         self.client_id,
                         msg_id,
                         self.psessionid,
                         fix_content,
                         group_sig,
                         service_type)
                 ),
                ('clientid', self.client_id),
                ('psessionid', self.psessionid),
                ('group_sig', group_sig),
                ('service_type', service_type)
            )
            rsp = self.req.Post(req_url, data, self.default_config.conf.get("global", "connect_referer"))
            rsp_json = json.loads(rsp)
            if 'retcode' in rsp_json and rsp_json['retcode'] != 0:
                raise ValueError("reply sess chat error" + str(rsp_json['retcode']))
            logging.info("Reply successfully.")
            logging.debug("Reply response: " + str(rsp))
            return rsp_json
        except:
            if fail_times < 5:
                logging.warning("Response Error.Wait for 2s and Retrying." + str(fail_times))
                logging.debug(rsp)
                time.sleep(2)
                self.send_sess_msg2(tuin, reply_content, msg_id, group_sig, service_type, fail_times + 1)
            else:
                logging.warning("Response Error over 5 times.Exit.reply content:" + str(reply_content))
                return False

    # 主动发送临时消息
    def send_sess_msg2_fromGroup(self, guin, tuin, reply_content, msg_id, service_type=0, fail_times=0):
        group_sig = self.__getGroupSig(guin, tuin, service_type)
        fix_content = str(reply_content.replace("\\", "\\\\\\\\").replace("\n", "\\\\n").replace("\t", "\\\\t"))
        rsp = ""
        try:
            req_url = "http://d1.web2.qq.com/channel/send_sess_msg2"
            data = (
                ('r',
                 '{{"to":{0}, "face":594, "content":"[\\"{4}\\", [\\"font\\", {{\\"name\\":\\"Arial\\", \\"size\\":\\"10\\", \\"style\\":[0, 0, 0], \\"color\\":\\"000000\\"}}]]", "clientid":{1}, "msg_id":{2}, "psessionid":"{3}", "group_sig":"{5}", "service_type":{6}}}'.format(
                         tuin,
                         self.client_id,
                         msg_id,
                         self.psessionid,
                         fix_content,
                         group_sig,
                         service_type)
                 ),
                ('clientid', self.client_id),
                ('psessionid', self.psessionid),
                ('group_sig', group_sig),
                ('service_type', service_type)
            )
            rsp = self.req.Post(req_url, data, self.default_config.conf.get("global", "connect_referer"))
            rsp_json = json.loads(rsp)
            if 'retcode' in rsp_json and rsp_json['retcode'] != 0:
                raise ValueError("reply sess chat error" + str(rsp_json['retcode']))
            logging.info("send_sess_msg2_fromGroup: Reply successfully.")
            logging.debug("send_sess_msg2_fromGroup: Reply response: " + str(rsp))
            return rsp_json
        except:
            if fail_times < 5:
                logging.warning("send_sess_msg2_fromGroup: Response Error.Wait for 2s and Retrying." + str(fail_times))
                logging.debug(rsp)
                time.sleep(2)
                self.send_sess_msg2_fromGroup(guin, tuin, reply_content, msg_id, service_type, fail_times + 1)
            else:
                logging.warning(
                    "send_sess_msg2_fromGroup: Response Error over 5 times.Exit.reply content:" + str(reply_content))
                return False