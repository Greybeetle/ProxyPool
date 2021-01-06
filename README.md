# 整体思路流程
爬取IP的总体思路分为两部分：  
1. 第一部分是定时从一些网站上爬取IP，做简单的验证，将验证通过的IP保存到数据库中；  
2. 第二部分是定时对数据库中已保存的IP进行测试，通过给每个IP进行打分的形式保留打分最高的IP作为最终的IP；  
***将这两个过程写成两个脚本，制作一个定时任务部署到服务器上即可，如果需要使用ip池，以后只要每次从数据库中捞就行了***
具体实现代码可见[个人github仓库：https://github.com/Greybeetle/ProxyPool](https://github.com/Greybeetle/ProxyPool)，有需要的可以参考

# IP爬取过程
## 基础IP爬取
从比较主流的网站上抓取目标ip，常用的网站有如下：  
1. 66免费代理网：[http://www.66ip.cn/](!http://www.66ip.cn/)
2. xici代理：[http://www.xicidaili.com/nn/](!http://www.xicidaili.com/nn/)  
3. 快代理：[http://www.kuaidaili.com/free/inha/](!http://www.kuaidaili.com/free/inha/)  

以下是爬取ip过程中的一些主要函数：
```python
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
```

多网站、多页面IP爬取
```python
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
```
## 初步验证IP是否可用
通过请求百度首页，测试每一个ip是否可以使用，如果不能使用则剔除掉
```python
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
```
为了防止一次测试结果不准确，所以进行多次测试
```python
# 轮巡检测多次
def get_best_ip(_ip_set, timeout, round):
    # 循环检查次数
    for i in range(round):
        _ip_set = get_valid_ip(_ip_set, timeout)     # 检查代理是否可用
        logger.info('Round ' + str(i+1) + '/' + str(round) + '：本轮有' + str(len(_ip_set)) + '个ip通过测试')
        time.sleep(30)
    # 返回可用数据
    return _ip_set
```
## 写入数据库
经过基本的筛选之后，将结果保存到数据库中即可
```python
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
```
***以上为IP爬取的整体流程........***
# IP打分过程
IP打分过程的主要思路是对保存到数据库中的IP进行多轮巡检，通过访问百度主页的成功率、响应时间等进行打分；
1. 从数据库中读取每一条数据
```python
cursor.execute('SELECT content FROM %s' % cfg.TABLE_NAME)
result = cursor.fetchall()
```
2. 对result中的每一条数据进行测试，通过成功率，响应时间计算得分：
```python
# 计算得分
def modify_score(ip, success, response_time):
    # 连接数据库
    conn = mdb.connect(cfg.host, cfg.user, cfg.passwd, cfg.DB_NAME)
    cursor = conn.cursor()

    # ip超时
    if success == 0:
        logging.warning(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+": " + ip + " out of time")
        try:
            cursor.execute('SELECT * FROM %s WHERE content= "%s"' % (cfg.TABLE_NAME, ip))
            q_result = cursor.fetchall()
            for r in q_result:
                test_times = r[1] + 1
                failure_times = r[2]
                success_rate = r[3]
                avg_response_time = r[4]

                # 超时达到4次且成功率低于标准
                if failure_times > 4 and success_rate < cfg.SUCCESS_RATE:
                    cursor.execute('DELETE FROM %s WHERE content= "%s"' % (cfg.TABLE_NAME, ip))
                    conn.commit()
                    logging.warning(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+": " + ip + " was deleted.")
                else:
                    # not too bad
                    failure_times += 1
                    success_rate = 1 - float(failure_times) / test_times
                    avg_response_time = (avg_response_time * (test_times - 1) + cfg.TIME_OUT_PENALTY) / test_times
                    score = (success_rate + float(test_times) / 500) / avg_response_time
                    n = cursor.execute('UPDATE %s SET test_times = %d, failure_times = %d, success_rate = %.2f, avg_response_time = %.2f, score = %.2f WHERE content = "%s"' % (TABLE_NAME, test_times, failure_times, success_rate, avg_response_time, score, ip))
                    conn.commit()
                    if n:
                        logging.error(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+": " +  ip + ' has been modify successfully!')
                break
        except Exception as e:
            logging.error(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+": Error when try to delete " + ip + str(e))
        finally:
            cursor.close()
            conn.close()
    
    elif success == 1:
        # pass the test
        try:
            cursor.execute('SELECT * FROM %s WHERE content= "%s"' % (cfg.TABLE_NAME, ip))
            q_result = cursor.fetchall()
            for r in q_result:
                test_times = r[1] + 1
                failure_times = r[2]
                avg_response_time = r[4]
                success_rate = 1 - float(failure_times) / test_times
                avg_response_time = (avg_response_time * (test_times - 1) + response_time) / test_times
                score = (success_rate + float(test_times) / 500) / avg_response_time
                n = cursor.execute('UPDATE %s SET test_times = %d, success_rate = %.2f, avg_response_time = %.2f, score = %.2f WHERE content = "%s"' %(cfg.TABLE_NAME, test_times, success_rate, avg_response_time, score, ip))
                conn.commit()
                if n:
                    logging.error(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ": " + ip + 'has been modify successfully!')
                break
        except Exception as e:
            logging.error(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ": Error when try to modify " + ip + str(e))
        finally:
            cursor.close()
            conn.close()
```
3. 经过这样的打分之后将更新数据库中的数据，同时为了保证数据库中IP不太多，每次检测完之后判断一下数据库中的IP数量，如果数量超过设定的最大数量，则删除评分较低的IP，删除代码如下：
```python
# 删除分数较低的ip，只保留max_num_ip条纪录
sql = "delete from %s where content not in (select content from (select content from (select content from %s order by score desc) tt limit %i) ss);" % (cfg.TABLE_NAME, cfg.TABLE_NAME, cfg.max_ip_num)
cursor.execute(sql)
conn.commit()
```
到这里，爬虫和打分两个过程都结束了，下面说一下在服务器上的部署；
# 项目部署
## 项目定时
主要思路是使用BlockingScheduler对两个脚本设置定时任务，其中爬取ip的脚本我设置的是每天0点爬一次，关于更多的定时任务的知识请移步我的其他博客。
```python
scheduler = BlockingScheduler()
scheduler.add_job(job, 'cron', hour=0, minute=0, second=0)
scheduler.start()
```
而检测的脚本设置的是每6小时检测一次
```python
scheduler = BlockingScheduler()
scheduler.add_job(job, 'interval', hours=6)
scheduler.start()
```
## 项目配置
在`config.py`中修改自己的数据库配置信息，然后分别运行`python get_proxy.py`和`python check_proxy.py`即可。
## 自动化守护
本次使用的自动化守护工具是`supervisor`，关于supervisor的教程，网上也非常多，大家可以参考，有时间再专门写一个教程。
---
至此整个项目都结束，大家可以愉快的爬虫了，爬虫一时爽，一直爬虫一直爽！
本文中参考了比较多的[ProxyPool – 自动化代理池，爬取代理IP并进行测速筛选](https://www.uedbox.com/post/54864/)，在此特别感谢！