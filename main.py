# -*- coding: UTF-8 -*-
import requests
from bs4 import BeautifulSoup
import re
from time import sleep
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80 Safari/537.36'}
proxies = {  }
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
channel = os.getenv("CHANNEL")

jsxwURL = "http://www.xinhuanet.com/jsxw.htm"
whxwURL = "http://www.news.cn/whxw.htm"

# 参数 _pageNid：栏目id _pageNum：当前json页数 _pageCnt：json取的条数 _pageTp：默认为1
_pageNid = '11142121'
_pageNum = '1'
_pageCnt = '50'
latestnewsURL = "http://qc.wa.news.cn/nodeart/list?nid=" + _pageNid + "&pgnum=" + _pageNum + "&cnt=" + _pageCnt + "&tp=1&orderby=1"   #http://www.xinhuanet.com/english/list/latestnews.htm"
maxLen = 1000       # The maximum length of one message.
                    # Bad view if too long
                    # Accounding to API doc, max is 4096

engine = create_engine(DATABASE_URL)
db = scoped_session(sessionmaker(bind=engine))

def getList(listURL, actionFlag):
    res = requests.get(listURL, headers = headers)
    res.encoding='utf-8'
    #print(res.text)

    newsList = []
    
    if actionFlag == 0:
        soup = BeautifulSoup(res.text,'lxml')
        data = soup.select('.dataList > .clearfix > h3 > a')
        #print(data)

        for item in data:
            result = {
                "title": item.get_text(),
                "link": item.get('href'),
                'ID': re.findall('\d+',item.get('href'))[-1]
            }
            newsList.append(result)
            
    elif actionFlag == 1:
        listJSON = json.loads(res.text[1:-2])   # Remove brackets and load as json

        for item in listJSON['data']['list']:
            i = {'ID': 0}
            i['ID'] = item['DocID']
            i['link'] = item['LinkUrl']
            i['title'] = item['Title']
            i["PubTime"] = item["PubTime"]
            i["SourceName"] = item["SourceName"]
            i["Author"] = item["Author"]
            newsList.append(i)
         
    return newsList

def getFull(url, item=None):
    res = requests.get(url, headers = headers)
    res.encoding='utf-8'
    #print(res.text)
    time = ''
    source = ''
    title = ''
    
    soup = BeautifulSoup(res.text,'lxml')
    if not item:

        # Get release time and source
        infoSelect = soup.select('.h-info > span')
        try:
            time = infoSelect[0].getText().strip()
        except IndexError:                              # Do not have this element because of missing/403/others
            time = ""
        try:
            source = infoSelect[1].getText().strip().replace('\n','')
        except IndexError:                              # Do not have this element because of missing/403/others
            source = ""
        
        # Get news title
        titleSelect = soup.select('body > .h-title, title, Btitle')
        try:
            title = titleSelect[0].getText().strip()
        except IndexError:                              # Do not have this element because of missing/403/others
            title = ""
    else:
        time = item["PubTime"]
        source = item["SourceName"]
        title = item['title']
        
    # Get news body
    # Two select ways:
    # Mobile news page: '.main-article > p'
    # Insatnce news page: '#p-detail > p'
    paragraphSelect = soup.select('p')
    #return paragraphSelect
    #print(paragraphSelect)

    def findLink(p):
        '''Remove tags except <a></a>. Otherwise, telegram api will not parse'''
        if p.select('a') == []:
            return p.getText()
        else:
            cp = str(p)
            result = ""
            for link in p.select('a'):
                other = str(cp).split(str(link))
                
                content = link.get_text()
                url = link.get('href')

                result += BeautifulSoup(other[0],'lxml').getText() + '<a href=\"'+url+'\" >'+content+'</a>'
                cp = str(p).replace(str(other[0])+str(link),"")
            return result + BeautifulSoup(cp, 'lxml').getText()
        
    paragraphs = ""
    for p in paragraphSelect:
        linkStr = findLink(p).strip('\u3000').strip('\n').strip()
        if linkStr != "": 
            paragraphs += linkStr + '\n\n'
    #print(paragraphs)

    return {'title': title, 'time': time, 'source': source, 'paragraphs': paragraphs, 'link': url}

def post(item, channel, news_id):
    po = ""
    po = '<b>' + item['title'] + '</b>'   # '%23' is '#'
    po += '\n\n'
    
    disable_web_page_preview = 'True'
    #disable_notification = 'Ture'
    
    if len(item['paragraphs']) > maxLen:
        # Post the link only.
        po += '<a href=\"' + item['link'] + '\">Link</a>\n\n'
        # If there is exceed the limit, enable web page preview.
        disable_web_page_preview = 'False'
    else:
        po += item['paragraphs']
    po += item['time']
    po += '\n'
    po += item['source']

    # https://core.telegram.org/bots/api#sendmessage    
    postURL = 'https://api.telegram.org/bot' + TOKEN + '/sendMessage?chat_id=' + channel + '&text=' + po + '&parse_mode=html&disable_web_page_preview=' + disable_web_page_preview
    res = requests.get(postURL, proxies=proxies)
    if res.status_code == 200:
        db.execute("INSERT INTO news (news_id, time) VALUES (:news_id, NOW())",
                            {"news_id":news_id})

        # Commit changes to database
        db.commit()
    return json.dumps(res.text)
    
def isPosted(news_id):
    rows = db.execute("SELECT * FROM news WHERE news_id = :news_id",
                            {"news_id": news_id})
    if rows.rowcount == 0:
        return False
    else:
        return True

def action(url, actionFlag):
    nlist = getList(url, actionFlag=actionFlag)
    nlist.reverse()
    #print(nlist)

    total = 0
    posted = 0
    for item in nlist:
        if not isPosted(item['ID']):
            message = None
            if actionFlag == 1:
                message = getFull(item['link'], item=item)
            elif actionFlag == 0:
                message = getFull(item['link'])
            res = post(message, channel, item['ID'])
            print(str(item['ID']) + " success!")
            total +=1
        else:
            posted += 1
            #print(item['ID'] + 'Posted!')
    return total, posted

def poll(time=30):
    while(True):
        total, posted = action(latestnewsURL, 1)
        print('1:' + str(total) + ' succeeded,' + str(posted) + ' posted.')
        total, posted = action(jsxwURL, 0)
        print('2:' + str(total) + ' succeeded,' + str(posted) + ' posted.')
        total, posted = action(whxwURL, 0)
        print('3:' + str(total) + ' succeeded,' + str(posted) + ' posted.')

        print('Wait ' + str(time) + 's to restart!')
        sleep(time)

poll()
