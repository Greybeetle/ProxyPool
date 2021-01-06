#!/user/bin/env python
# -*- coding:utf-8 -*-
#
import requests
import logging
import time
import config as cfg
from lxml import etree
import pymysql as mdb
import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
logging.basicConfig(level=logging.INFO, format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 解析网页内容，返回ip列表
def get_content(url, url_xpath, port_xpath):
    ip_list = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Trident/7.0; rv:11.0) like Gecko'}    # 设置请求头信息
        
        # 获取页面数据
        results = requests.get(url, headers=headers, timeout=4)
        tree = etree.HTML(results.text)
        
        # 提取ip:port
        url_results = tree.xpath(url_xpath)
        port_results = tree.xpath(port_xpath)
        urls = [line.strip() for line in url_results]
        ports = [line.strip() for line in port_results]

        if len(urls) == len(ports):
            for i in range(len(urls)):
                full_ip = urls[i]+":"+ports[i]  # 匹配ip:port对
                ip_list.append(full_ip)
    except Exception as e:
        logger.info('get proxies error: ' + str(e))
    return ip_list


# 根据设定页数爬取ip数
def get_all_ip(max_page_num, max_nums):
    ip_set = set()  # 利用set的自动排序和剔重功能
    url_xpath_xici = '//table[@id="ip_list"]//tr[position()>1]/td[position()=2]/text()'
    port_xpath_xici = '//table[@id="ip_list"]//tr[position()>1]/td[position()=3]/text()'
    url_xpath_66 = '/html/body/div[last()]//table//tr[position()>1]/td[1]/text()'
    port_xpath_66 = '/html/body/div[last()]//table//tr[position()>1]/td[2]/text()'
    url_xpath_kuaidaili = '//td[@data-title="IP"]/text()'
    port_xpath_kuaidaili = '//td[@data-title="PORT"]/text()'
    page = 0
    while len(ip_set) < max_nums:
        url_xici = 'http://www.xicidaili.com/nn/' + str(page+1)
        url_66 = 'http://www.66ip.cn/' + str(page+1) + '.html'
        url_kuaidaili = 'http://www.kuaidaili.com/free/inha/' + str(page+1) + '/'
        ip_set.update(get_content(url_xici, url_xpath_xici, port_xpath_xici))
        ip_set.update(get_content(url_66, url_xpath_66, port_xpath_66))
        ip_set.update(get_content(url_kuaidaili, url_xpath_kuaidaili, port_xpath_kuaidaili))
        page+=1
        if page > max_page_num:
            break
        time.sleep(1)
    return ip_set

# 测试爬取ip的可用性
def get_valid_ip(ip_set, timeout):
    
    # 设置请求地址
    url = 'https://www.baidu.com'

    # 可用代理结果
    results = set()

    # 检查代理是否可用
    for p in ip_set:
        proxy = {'http': 'http://'+p}
        try:
            # 请求开始时间
            start = time.time()
            r = requests.get(url, proxies=proxy, timeout=timeout)
            # 请求结束时间
            end = time.time()
            # 判断是否可用
            if r.text is not None:
                # logger.info('succeed: ' + p + ' ' + " in " + format(end-start, '0.2f') + 's')
                # 追加代理ip到返回的set中
                results.add(p)
        except OSError:
            logger.info('timeout:' + str(p))
    
    return results

# 轮巡检测多次
def get_best_ip(_ip_set, timeout, round):
    # 循环检查次数
    for i in range(round):
        _ip_set = get_valid_ip(_ip_set, timeout)     # 检查代理是否可用
        logger.info('Round ' + str(i+1) + '/' + str(round) + '：本轮有' + str(len(_ip_set)) + '个ip通过测试')
        time.sleep(30)
    # 返回可用数据
    return _ip_set

# 将可用的ip存储进mysql数据库
def save_to_db(_ip_set):
    if len(_ip_set) == 0:
        logger.info("本次没有抓到可用ip")
        return
    # 连接数据库
    logger.info("---------- 开始写入数据库  ----------")
    conn = mdb.connect(cfg.host, cfg.user, cfg.passwd, cfg.DB_NAME)
    cursor = conn.cursor()
    try:
        for item in _ip_set:
            # 检查表中是否存在数据
            item_exist = cursor.execute('SELECT * FROM %s WHERE content="%s"' %(cfg.TABLE_NAME, item))

            # 新增代理数据入库
            if item_exist == 0:
                # 插入数据
                n = cursor.execute('INSERT INTO %s VALUES("%s", 1, 0, 0, 1.0, 2.5)' %(cfg.TABLE_NAME, item))
                conn.commit()

                # 输出入库状态
                if n:
                    logger.info(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+" "+item+" 插入成功")
                else:
                    logger.info(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+" "+item+" 插入失败")
            else:
                logger.info(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+" "+ item +" 已存在")
    except Exception as e:
        logger.info("入库失败：" + str(e))
    finally:
        cursor.close()
        conn.close()
    logger.info("---------- 写入数据库结束  ----------")

def job():
    ip_set = get_all_ip(cfg.page_num, cfg.max_ip_num)  # 获取50个左右的ip，但是最大爬取网页数要低于10个
    logger.info('爬取' + str(len(ip_set)) + '个ip，开始准备轮巡验证')
    available_ip_set = get_best_ip(ip_set, cfg.timeout, cfg.examine_round)
    logger.info(str(len(ip_set)) + '个ip通过验证，开始写入数据库中')
    save_to_db(available_ip_set)



if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(job, 'cron', hour=0, minute=0, second=0)
    scheduler.start()