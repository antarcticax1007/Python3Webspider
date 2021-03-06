import requests
import json
import time
import pymysql

class Fund_Spider():

    def __init__(self):
        self.headers = \
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"
            }
        self.getid_url = 'http://fund.ijijin.cn/data/Net/info/gpx_F009_desc_0_0_1_9999_0_0_0_jsonp_g.html'
        self.baseinfo_url = 'http://fund.10jqka.com.cn/data/client/myfund/{}'
        self.stocks_info = 'http://fund.10jqka.com.cn/web/fund/stockAndBond/{}'
        self.db = pymysql.connect(host='localhost', user='root', password='zsw123456', port=3306, db='test_db')

    # 从字典列表相互嵌套的数据中获取想要的值的方法
    def get_json_value_by_key(self, in_json, target_key, results=[]):
        if isinstance(in_json, dict):  # 如果输入数据的格式为dic
            for key in in_json.keys():  # 循环获取key
                data = in_json[key]
                self.get_json_value_by_key(data, target_key, results=results)  # 回归当前key对于的value

                if key == target_key:  # 如果当前key与目标key相同就将当前key的value添加到输出列表
                    results.append(data)

        elif isinstance(in_json, list) or isinstance(in_json, tuple):  # 如果输入数据格式为list或者tuple
            for data in in_json:  # 循环当前列表
                self.get_json_value_by_key(data, target_key, results=results)  # 回归列表的当前的元素

        return results

    def get_fund_id(self):
        response = requests.get(self.getid_url, self.headers).text
        # 发现返回的并不是标准json格式数据
        jsondata = response[2:-1]  # 字符串处理
        data = json.loads(jsondata)  # 转化为json数据为字典
        idnum = self.get_json_value_by_key(data, "code")
        return idnum  # 以列表形式返回所有基金id

    # 获取基金基本信息，以及前十重仓信息
    def get_fundinfo(self, fund_num):
        baseinfo_url = self.baseinfo_url.format(fund_num)
        stocks_infourl = self.stocks_info.format(fund_num)
        fund_baseinfo_response = requests.get(baseinfo_url, self.headers)
        fund_stocksinfo_response = requests.get(stocks_infourl, self.headers)
        # print(fund_baseinfo_response.status_code)
        if fund_baseinfo_response.status_code == 200 and fund_stocksinfo_response.status_code == 200:
            stocksinfo_data = json.loads(fund_stocksinfo_response.text)
            baseinfo_data = json.loads(fund_baseinfo_response.text)
            return stocksinfo_data, baseinfo_data
        else:
            return None, None

    def create_table(self):
        cur = self.db.cursor()
        # 创建一个表
        sql = 'create table if not exists fund_spider (id INT, 基金名称 VARCHAR(255),基金代码 INT , 日期 DATE , ' \
              '规模亿 FLOAT , 净值 FLOAT , 成立时间 DATE , 经理 VARCHAR(255), 管理人 VARCHAR(255), ' \
              '近1个月收益 FLOAT )'
        cur.execute(sql)
        for i in range(10):
            sql = 'alter table fund_spider add column 重仓持股_{a} varchar(255), ' \
                  'add column 占净资产比_{b} FLOAT, add column 市值万元_{c} FLOAT '.format(a=i + 1, b=i + 1, c=i + 1)
            cur.execute(sql)
        print('创建表成功')
        self.db.close()

    # 将数据插入到mysql中
    def insert_data(self):
        cur = self.db.cursor()  # 获取游标
        count = 0
        idnum_pool = self.get_fund_id()
        print(len(idnum_pool))

        # 获取数据
        while len(idnum_pool) > 0:
            fund_num = idnum_pool.pop()
            stocksinfo_data, baseinfo_data = self.get_fundinfo(fund_num=fund_num)
            time.sleep(0.5)   # 间歇爬取不会导致封锁ip
            # 获取数据插入mysql
            if stocksinfo_data != None and baseinfo_data != None:
                count = count + 1
                # 获取基本信息
                name = baseinfo_data["data"][0]["name"]  # 基金名称
                id = fund_num  # 基金代码
                value = baseinfo_data["data"][0]["asset"]  # 规模
                established = baseinfo_data["data"][0]["clrq"]  # 成立时间
                manager = baseinfo_data["data"][0]["manager"]  # 经理
                administrator = baseinfo_data["data"][0]["orgname"]  # 管理人
                monthincome = baseinfo_data["data"][0]["month"]  # 近一个月收益
                enddate = baseinfo_data["data"][0]["enddate"]  # 更新时间
                totalnet = baseinfo_data["data"][0]["totalnet1"]  # 净值
                print(totalnet)
                baseinfo_sql = 'INSERT INTO fund_spider(ID, 基金名称, 基金代码, 日期, 规模亿, 净值, 成立时间, 经理, 管理人, ' \
                               '近1个月收益) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'
                try:
                    cur.execute(baseinfo_sql,
                                (count, name, id, enddate, value, totalnet, established, manager, administrator, monthincome))
                    self.db.commit()
                    print('基本信息获取成功')
                except:
                    self.db.rollback()
                # 将获取到的仓位信息处理并插入到mysql中
                stocks = stocksinfo_data["data"]['stock']
                print(stocks)
                for i in range(len(stocks)):
                    stock = stocks[i]
                    name = stock['zcName']
                    proportion = stock['ccRate']
                    totalvalue = stock['totalPrice']
                    print(totalvalue)
                    stocks_sql = 'UPDATE fund_spider SET 重仓持股_{a}="{A}", 占净资产比_{b}={B}, ' \
                                              '市值万元_{c}={C} WHERE ID={count}'.format(a=i + 1, b=i + 1, c=i + 1, A=name, B=proportion, C=totalvalue, count=count )  # sql语句
                    try:
                        cur.execute(stocks_sql)  # 插入数据
                        self.db.commit()
                        print('持仓信息插入成功')
                    except:
                        self.db.rollback()
            else:
                idnum_pool.insert(0, fund_num)
                print("请求失败,idnum返回请求池")
        self.db.close()


    def crawler_starting(self):
        self.create_table()
        self.insert_data()


if __name__ == '__main__':
    spider = Fund_Spider()
    spider.crawler_starting()