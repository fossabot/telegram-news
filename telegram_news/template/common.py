# -*- coding: UTF-8 -*-

"""
Base template Info Extractor and News Postman for Telegram-news.

Basic Info Extractor and News Postman for standard HTML data and extended
class for JSON and XML format data. Maybe have more subclasses for other
situations.
"""

import json
import math
import os
import threading
import traceback
from time import sleep

import requests
import sqlalchemy
from bs4 import BeautifulSoup

from ..displaypolicy import (
    default_policy,
    default_id_policy,
)
from ..ratelimit import (
    sleep_and_retry,
    RateLimitDecorator as limits
)
from ..utils import (
    keep_link,
    str_url_encode,
    is_single_media,
    get_full_link,
    xml_to_json,
    add_parameters_into_url,
)
from ..constant import (
    AVAILABLE_METHOD,
)


class InfoExtractor(object):
    """
    Information Extractor class.

    Information Extractor class is a class that process raw request data
    and convert to a formatted data.

    Attributes:
        _listURLs
        _lang
        _id_policy
        _list_pre_process_policy
        _full_pre_process_policy
        max_post_length
        _cached_list_items
        _list_selector
        _time_selector
        _title_selector
        _source_selector
        _paragraph_selector
        _outer_link_selector
        _outer_title_selector
        _outer_paragraph_selector
        _outer_time_selector
        _outer_source_selector
    """

    _listURLs = []
    _lang = ""
    _id_policy = default_id_policy

    # Functions that get preprocessed text from raw request response text.
    _list_pre_process_policy = None
    _full_pre_process_policy = None

    max_post_length = 1000

    # Maybe cache feature should be implemented at here
    # Cache the list webpage and check if modified
    _cached_list_items = os.urandom(10)

    _list_selector = None
    _title_selector = None
    _time_selector = None
    _source_selector = None
    _image_selector = None
    _paragraph_selector = 'p'  # Default selector
    _outer_link_selector = 'a'  # Default selector
    _outer_title_selector = None
    _outer_paragraph_selector = None
    _outer_time_selector = None
    _outer_source_selector = None
    _outer_image_selector = None

    def __init__(self, lang=''):
        """Construct the class."""
        self._DEBUG = True
        self._lang = lang

    def set_list_selector(self, selector):
        self._list_selector = selector

    def set_title_selector(self, selector):
        self._title_selector = selector

    def set_paragraph_selector(self, selector):
        self._paragraph_selector = selector

    def set_time_selector(self, selector):
        self._time_selector = selector

    def set_source_selector(self, selector):
        self._source_selector = selector

    def set_image_selector(self, selector):
        self._image_selector = selector

    def set_outer_link_selector(self, selector):
        self._outer_link_selector = selector

    def set_outer_title_selector(self, selector):
        self._outer_title_selector = selector

    def set_outer_paragraph_selector(self, selector):
        self._outer_paragraph_selector = selector

    def set_outer_time_selector(self, selector):
        self._outer_time_selector = selector

    def set_outer_source_selector(self, selector):
        self._outer_source_selector = selector

    def set_outer_image_selector(self, selector):
        print('Set outer selector successfully', selector)
        self._outer_image_selector = selector

    def set_id_policy(self, id_policy):
        self._id_policy = id_policy

    def set_list_pre_process_policy(self, pre_process_policy):
        self._list_pre_process_policy = pre_process_policy

    def set_full_pre_process_policy(self, pre_process_policy):
        self._full_pre_process_policy = pre_process_policy

    def list_pre_process(self, text, list_url):
        if self._list_pre_process_policy:
            try:
                return self._list_pre_process_policy(text, list_url)
            except TypeError:
                # _list_pre_process_policy not need url
                return self._list_pre_process_policy(text)
        else:
            return text

    def full_pre_process(self, text, full_url):
        if self._full_pre_process_policy:
            try:
                return self._full_pre_process_policy(text, full_url)
            except TypeError:
                # _full_pre_process_policy not need url
                return self._full_pre_process_policy(text)
        else:
            return text

    def get_items_policy(self, text, listURL):
        """
        Get all items in the list webpage.

        :param text:
        :param listURL:
        :return: item dict list.
        """
        soup = BeautifulSoup(text, 'lxml')
        data = soup.select(self._list_selector)
        # print(data)

        news_list = []
        for i in data:
            soup2 = BeautifulSoup(str(i), 'lxml')
            link_select = soup2.select(self._outer_link_selector)
            link = get_full_link(link_select[0].get('href'), listURL)
            item = {
                "title": link_select[0].get_text().strip(),
                'link': link,
                'id': self._id_policy(link)
            }

            if self._outer_title_selector:
                try:
                    item['title'] = soup2.select(self._outer_title_selector)[0].get_text().strip()
                except IndexError:
                    item['title'] = ''
            else:
                item['title'] = item['title']

            if self._outer_paragraph_selector:
                try:
                    paragraphs = [x.get_text().strip() for x in soup2.select(self._outer_paragraph_selector)]
                    item['paragraphs'] = '\n\n'.join(paragraphs) + '\n\n'
                except IndexError:
                    item['paragraphs'] = ''
            else:
                item['paragraphs'] = ''

            if self._outer_time_selector:
                try:
                    item['time'] = soup2.select(self._outer_time_selector)[0].get_text().strip()
                except IndexError:
                    item['time'] = ''
            else:
                item['time'] = ''

            if self._outer_source_selector:
                try:
                    item['source'] = soup2.select(self._outer_source_selector)[0].get_text().strip()
                except IndexError:
                    item['source'] = ''
            else:
                item['source'] = ''

            if self._outer_image_selector:
                try:
                    tags = soup2.select(self._outer_image_selector)
                    item['image'] = [get_full_link(img.get('src'),listURL) for img in tags]
                except IndexError:
                    item['image'] = []
            else:
                item['image'] = []
            news_list.append(item)

        # Hit cache test here
        # If the list is new, return it.
        if news_list != self._cached_list_items:
            self._cached_list_items = news_list
            return news_list, len(news_list)
        else:
            # print('List is not modified!', end=' ')
            return None, len(news_list)

    def get_title_policy(self, text, item):
        """
        Get news title.

        :param text: raw request data from webpage.
        :param item: item dict.
        :return: title string.
        """
        if item['title'] or self._outer_title_selector:
            return keep_link(item['title'].replace('&nbsp;', ' '), item['link'])
        if not self._title_selector:
            return ''
        soup = BeautifulSoup(text, 'lxml')
        title_select = soup.select(self._title_selector)
        try:
            return title_select[0].getText().strip()
        except IndexError:  # Do not have this element because of missing/403/others
            # But the list have a title
            return item['title']

    def get_paragraphs_policy(self, text, item):
        """
        Get news body.

        :param text: raw request data from webpage.
        :param item: item dict.
        :return: concatenated paragraphs string.
        """
        if item['paragraphs'] or self._outer_paragraph_selector:
            return item['paragraphs']
        if not self._paragraph_selector:
            return None
        soup = BeautifulSoup(text, 'lxml')
        paragraph_select = soup.select(self._paragraph_selector)
        # print(paragraph_select)

        url = item['link']
        paragraphs = ""
        blank_flag = False
        for p in paragraph_select:
            link_str = keep_link(str(p), url).strip('\u3000').strip('\n').strip()

            # If there is only ONE [Media] link, it should be concerned as a word.
            # This is the
            if link_str != "" and not is_single_media(link_str):
                if blank_flag:
                    link_str = '\n\n' + link_str
                    blank_flag = False
                paragraphs += link_str + '\n\n'
            elif link_str != "":
                paragraphs += link_str + ' '
                blank_flag = True
        if paragraphs and paragraphs[-1] == ' ':
            paragraphs += '\n\n'
        # print(paragraphs)

        return paragraphs

    def get_time_policy(self, text, item):
        """
        Get news release time.

        :param text: raw request data from webpage.
        :param item: item dict.
        :return: time string.
        """
        if item['time'] or self._outer_time_selector:
            return item['time']
        if not self._time_selector:
            return ''
        soup = BeautifulSoup(text, 'lxml')
        time_select = soup.select(self._time_selector)
        if not time_select:
            return ""
        publish_time = time_select[0].getText().strip().replace('\n', ' ')
        return publish_time

    def get_source_policy(self, text, item):
        """
        Get news source.

        :param text: raw request data from webpage.
        :param item: item dict.
        :return: source string.
        """
        if item['source'] or self._outer_source_selector:
            return item['source']
        if not self._source_selector:
            return ''
        soup = BeautifulSoup(text, 'lxml')
        source_select = soup.select(self._source_selector)
        url = item['link']
        try:
            # Maybe source is a link
            source = keep_link(str(source_select[0]), url).strip().replace('\n', '').replace(' ' * 60, ' / ')
        except IndexError:  # Do not have this element because of missing/403/others
            source = ""
        return source

    def get_image_policy(self, text, item):
        """
        Get selected image.

        :param text: raw request data from webpage.
        :param item: item dict.
        :return: image url list.
        """
        if item['image'] or self._outer_image_selector:
            return item['image']
        if not self._image_selector:
            return []
        soup = BeautifulSoup(text, 'lxml')
        tags_select = soup.select(self._image_selector)
        images = [get_full_link(img.get('src'), item['link']) for img in tags_select]
        return images

class InfoExtractorJSON(InfoExtractor):
    """
    Information Extractor class for JSON.

    Information Extractor class for JSON is a class that process raw request data
    and convert to a formatted data, especially for a format of JSON.

    Attributes:
        All the attributes of InfoExtractor and
        _list_router
        _id_router
        _link_router
        _title_router
        _paragraphs_router
        _time_router
        _source_router
    """

    _list_router = None
    _id_router = None
    _link_router = None
    _title_router = None
    _paragraphs_router = None
    _time_router = None
    _source_router = None

    def __init__(self):
        """As same as InfoExtractor."""
        super(InfoExtractorJSON, self).__init__()

    @staticmethod
    def _get_item_by_route(item, router):
        if router is None:
            return None
        try:
            for key in router:
                if key is not None:
                    item = item[key]
        except KeyError:
            return None
        except IndexError:
            return None
        return item

    def set_list_router(self, router):
        self._list_router = router

    def set_id_router(self, router):
        self._id_router = router

    def set_link_router(self, router):
        self._link_router = router

    def set_title_router(self, router):
        self._title_router = router

    def set_paragraphs_router(self, router):
        self._paragraphs_router = router

    def set_time_router(self, router):
        self._time_router = router

    def set_source_router(self, router):
        self._source_router = router

    def get_items_policy(self, text, listURL):  # -> (list, int)
        try:
            list_json = json.loads(text)
        except json.decoder.JSONDecodeError:
            try:
                list_json = json.loads(text[1:-2])  # Remove brackets and load as json
            except Exception as e:
                print('List json decode filed. ', e)
                return None, 0

        list_json = self._get_item_by_route(list_json, self._list_router)

        news_list = []
        for i in list_json:
            item = dict()
            item['link'] = get_full_link(self._get_item_by_route(i, self._link_router), listURL)
            # Router has a higher priority
            if self._id_router:
                item['id'] = self._get_item_by_route(i, self._id_router)
            else:
                item['id'] = self._id_policy(item['link'])
            item['title'] = self._get_item_by_route(i, self._title_router)
            item['paragraphs'] = keep_link(self._get_item_by_route(i, self._paragraphs_router), item['link'])
            item["time"] = self._get_item_by_route(i, self._time_router)
            item["source"] = self._get_item_by_route(i, self._source_router)
            news_list.append(item)

        # Hit cache test here
        # If the list is new, return it.
        if news_list != self._cached_list_items:
            self._cached_list_items = news_list
            return news_list, len(news_list)
        else:
            # print('List is not modified!', end=' ')
            return None, len(news_list)

    def get_title_policy(self, text, item):
        if item['title'] and self._title_router:
            return keep_link(item['title'].replace('&nbsp;', ' '), item['link'])
        return super(InfoExtractorJSON, self).get_title_policy(text, item)

    def get_paragraphs_policy(self, text, item):
        if item['paragraphs'] and self._paragraphs_router:
            return item['paragraphs']
        return super(InfoExtractorJSON, self).get_paragraphs_policy(text, item)

    def get_time_policy(self, text, item):
        if item['time'] and self._time_router:
            return item['time']
        return super(InfoExtractorJSON, self).get_time_policy(text, item)

    def get_source_policy(self, text, item):
        if item['source'] and self._source_router:
            return item['source']
        return super(InfoExtractorJSON, self).get_source_policy(text, item)


class InfoExtractorXML(InfoExtractorJSON):
    """
    Information Extractor class for JSON.

    Information Extractor class for JSON is a class that process raw request data
    and convert to a formatted data, especially for a format of JSON.

    Attributes:
        As same as InfoExtractorJSON.
    """

    def __init__(self):
        """As same as InfoExtractor."""
        super(InfoExtractorXML, self).__init__()

    def list_pre_process(self, text, list_url):
        text = super(InfoExtractorXML, self).list_pre_process(text, list_url=list_url)
        return xml_to_json(text)


class NewsPostman(object):
    """
    News Postman class.

    News Postman class is a class that deals with network and database.

    Attributes:
        _listURLs
        _tag
        _sendList
        _headers
        _proxies
        _display_policy
        _parameter_policy
        _TOKENS
        _db
        _table_name
        _max_table_rows
        _list_request_response_encode
        _list_request_timeout
        _full_request_response_encode
        _full_request_timeout
        _max_list_length
        _extractor
        _cache_list
    """

    _listURLs = []
    _tag = ""
    _sendList = []
    _headers = None
    _proxies = None
    _display_policy = default_policy
    _parameter_policy = None
    _TOKENS = [os.getenv("TOKEN"), ]
    _db = None
    _table_name = None
    _max_table_rows = math.inf
    _list_request_response_encode = 'utf-8'
    _list_request_timeout = 10
    _full_request_response_encode = 'utf-8'
    _full_request_timeout = 10
    _max_list_length = math.inf
    _send_method = "sendMessage"
    _extractor = InfoExtractor()

    # Cache the list webpage and check if modified
    _cache_list = os.urandom(10)

    def __init__(self, listURLs, sendList, db, tag='', headers=None, proxies=None, display_policy=default_policy):
        """Construct the class by setting key attributes."""
        self._DEBUG = False
        self._listURLs = listURLs
        self._sendList = sendList
        self._tag = tag
        self._display_policy = display_policy
        self._db = db
        if headers:
            self._headers = headers
        else:
            self._headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/80 Safari/537.36'
            }
        self._proxies = proxies

    @staticmethod
    def set_bot_token(new_token):
        """Set one token only."""
        NewsPostman._TOKENS = [new_token, ]

    @staticmethod
    def add_bot_token(new_token):
        NewsPostman._TOKENS.append(new_token)

    def set_database(self, db):
        self._db = db

    def set_table_name(self, new_table_name):
        self._table_name = new_table_name
        rows = self._db.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :new_table_name ;",
                                {"new_table_name": new_table_name})
        if rows.fetchone()[0] == 1:
            print('Set table name \"' + new_table_name + '\" successfully, table already exists!')
            return False
        else:
            # Change dir to here and change back
            work_path = os.getcwd()
            file_path = os.path.abspath(__file__).replace('common.py', '')
            os.chdir(file_path)
            f = open("../table.sql")
            os.chdir(work_path)

            # Get SQL statement
            lines = f.read()
            f.close()

            lines = lines.replace(' ' + 'news' + '\n', ' ' + new_table_name + '\n')
            print('New table name \"' + new_table_name + '\" is settable, setting...')
            self._db.execute(lines)
            self._db.commit()
            print('Create table finished!')
            return True

    def set_max_table_rows(self, num, verbose=True):
        if verbose:
            print('Warning, the max_table_rows must at least 3 TIMES than the real list length!')
            print('And to avoid problems caused by unstable list, the number may be higher!')
        self._max_table_rows = num

    def _clean_database(self):
        query = "SELECT COUNT(*) FROM {}".format(self._table_name)
        rows = self._db.execute(query)
        # If the items in database exceed 2 of 3 of max rows, begin to delete old 1 of 3 of max rows
        rows_num = rows.fetchone()[0]
        # print("rows: ", rows_num)

        if rows_num > 2 * ((self._max_table_rows - 3) / 3):
            delete_number = int(self._max_table_rows / 3)
            print('delete ', delete_number)
            query = "DELETE FROM {} WHERE id IN ( SELECT id FROM {} ORDER BY id ASC LIMIT :delete_number )" \
                .format(self._table_name, self._table_name)
            self._db.execute(query, {"delete_number": str(delete_number)})
            self._db.commit()
            print('\033[33mClean database finished!\033[0m')

    def _insert_one_item(self, news_id):
        query = "INSERT INTO {} (news_id, time) VALUES (:news_id, NOW())".format(self._table_name)
        self._db.execute(query, {"news_id": news_id})
        # Commit changes to database
        self._db.commit()

    def not_post_old(self):
        """Use the same work logic to set old news item as POSTED."""
        self._action(no_post=True)

    def set_list_encoding(self, encode):
        self._list_request_response_encode = encode

    def set_full_encoding(self, encode):
        self._full_request_response_encode = encode

    def set_full_request_timeout(self, timeout=10):
        self._full_request_timeout = timeout

    def set_list_request_timeout(self, timeout=10):
        self._list_request_timeout = timeout

    def set_max_list_length(self, max_list_length):
        self._max_list_length = max_list_length

    def set_extractor(self, extractor):
        self._extractor = extractor

    def set_parameter_policy(self, parameter_policy):
        self._parameter_policy = parameter_policy

    def _get_request_url(self, pure_url):
        if self._parameter_policy:
            return self._parameter_policy(url=pure_url)
        else:
            return pure_url

    def _get_list(self, list_request_url):  # -> (list, int)
        timeout = self._list_request_timeout
        res = requests.get(list_request_url, headers=self._headers, timeout=timeout)
        # print(res.text)
        if res.status_code == 200:
            res.encoding = self._list_request_response_encode
            text = self._extractor.list_pre_process(res.text, list_request_url)
            return self._extractor.get_items_policy(text, list_request_url)
        else:
            print('\033[31mList URL error exception! ' + str(res.status_code) + '\033[0m')
            if res.status_code == 403:
                print('Maybe something not work.')
            return [], 0

    def _get_full(self, url, item):
        text = ""
        if url:
            timeout = self._full_request_timeout
            res = requests.get(url, headers=self._headers, timeout=timeout)
            res.encoding = self._full_request_response_encode
            text = res.text
        text = self._extractor.full_pre_process(text, item['link'])
        # print(text)

        title = self._extractor.get_title_policy(text, item)
        paragraphs = self._extractor.get_paragraphs_policy(text, item)
        publish_time = self._extractor.get_time_policy(text, item)
        source = self._extractor.get_source_policy(text, item)
        images = self._extractor.get_image_policy(text, item)

        return {
            'title': title,
            'time': publish_time,
            'source': source,
            'paragraphs': paragraphs,
            'link': url,
            'images': images
        }

    @sleep_and_retry
    @limits(calls=1, period=1)
    def _post(self, item, news_id):

        # Get display policy by item info
        po, parse_mode, disable_web_page_preview = self._display_policy(item, max_len=self._extractor.max_post_length)

        # Do not post if the message is empty
        if not po:
            return None

        # Must url encode the text
        if self._DEBUG:
            po += '\nDEBUG #D' + str(news_id)
        po = str_url_encode(po)

        res = None

        isposted_flags = [0] * len(self._sendList)
        candidate_list = self._sendList

        for i, chat_id in enumerate(candidate_list):
            if not chat_id:
                continue

            for token in self._TOKENS:
                if not token:
                    continue

                # https://core.telegram.org/bots/api#sendmessage
                post_url = 'https://api.telegram.org/bot' + token + '/sendMessage?chat_id=' + chat_id + '&text=' + \
                           po + '&parse_mode=' + parse_mode + '&disable_web_page_preview=' + disable_web_page_preview
                res = requests.get(post_url, proxies=self._proxies)

                # If post successfully, record and post to next channel.
                if res.status_code == 200:
                    isposted_flags[i] = 1

                    # Only record once when successfully posted.
                    if isposted_flags.count(1) == 1:
                        self._insert_one_item(news_id)

                    break

                # If not success because of 429 error, retry by other bots.
                elif res.status_code == 429:

                    # If no more bot tokens for retrying.
                    if token is self._TOKENS[-1]:
                        print('\033[31mWarning! 429 happened in ' + self._tag + '!\033[0m')

                        # Sleep time is determined by the last bot!
                        sleep_time = json.loads(res.text)['parameters']['retry_after']
                        sleep(sleep_time)

                        # Clear cache if not post.
                        self._cache_list = os.urandom(10)

                        # The last post succeed but this one failed, do it again!
                        if isposted_flags[i] == 0 and i != 0 and isposted_flags[:i].count(1) >= 1:
                            candidate_list.append(chat_id)
                            isposted_flags.append(0)
                            continue

                        # Non-first channel has the risk of lost message
                        return res
                    else:
                        print("Retry " + str(self._TOKENS.index(token) + 1) + " time(s) for " + self._tag)
                        continue

                # Other unknown error.
                else:
                    # Clear cache if not post
                    self._cache_list = os.urandom(10)
                    print('\033[31mFATAL ERROR! NOT POSTED BECAUSE OF ' + str(res.status_code))
                    print(res.text)
                    print('Telegram API error in ' + self._tag + '!\033[0m')
        return res

    def _is_posted(self, news_id):
        query = "SELECT * FROM {} WHERE news_id = :news_id".format(self._table_name)
        rows = self._db.execute(query, {"news_id": str(news_id)})
        if rows.rowcount == 0:
            return False
        else:
            return True

    def _action(self, no_post=False):  # -> (list, int)
        duplicate_list = []
        total = 0
        for link in self._listURLs:
            list_request_url = self._get_request_url(link)
            # print(list_request_url)
            l, num = self._get_list(list_request_url)
            total += num
            if l:
                duplicate_list += l

        if not duplicate_list:
            return None, total
        # Remain the UNIQUE one from oldest to newest
        unique_list = []
        duplicate_list.reverse()
        for item in duplicate_list:
            if item not in unique_list:
                unique_list.append(item)
        # Hit cache test here
        list_set = {str(i) for i in unique_list}
        if list_set != self._cache_list:
            self._cache_list = list_set
        else:
            # print('List set is cached!')
            return None, len(unique_list)

        total = 0
        posted = 0

        # Select top item_mun items
        item_mun = min(self._max_list_length, len(unique_list))

        unique_list = unique_list[-item_mun:]
        for item in unique_list:
            if not self._is_posted(item['id']):
                if not no_post:
                    message = self._get_full(item['link'], item=item)
                    # print(message)

                    # Post the message by api
                    res = self._post(message, item['id'])
                    if res is None:
                        print('\033[32m' + str(item['id']) + ' empty message!\033[0m')
                        continue
                    print('\033[32m' + str(item['id']) + ' ' + str(res.status_code) + '\033[0m')
                else:  # to set old news item as POSTED
                    self._insert_one_item(item['id'])
                    print('Get ' + item['id'] + ', but no action!')
                total += 1
            else:
                posted += 1
                # print(item['id'] + 'Posted!')
        return total, posted

    def poll(self, sleep_time=30):
        # Thread work function
        def work():
            while True:
                try:
                    total, posted = self._action()
                    if total is None:
                        print(self._tag + ':' + ' ' * (6 - len(self._tag)) + '\tList not modified! ' +
                              str(min(posted, self._max_list_length)) + ' posted. Wait ' +
                              str(sleep_time) + 's to restart!')
                        # If the list is not modified, we don't need to clean database
                        # self._clean_database()
                    else:
                        print(self._tag + ':' + ' ' * (6 - len(self._tag)) + '\t' + str(total) + ' succeeded, '
                              + str(posted) + ' posted. Wait ' + str(sleep_time) + 's to restart!')
                        self._clean_database()
                except requests.exceptions.ReadTimeout as e:
                    print('\033[31mwarning in', self._tag)
                    print(e)
                    print('\033[0m')
                except requests.exceptions.ConnectTimeout as e:
                    print('\033[31mwarning in', self._tag)
                    print(e)
                    print('\033[0m')
                except requests.exceptions.ConnectionError as e:
                    print('\033[31mwarning in', self._tag)
                    print(e)
                    print('\033[0m')
                except sqlalchemy.exc.InvalidRequestError as e:
                    # Clear cache when any error
                    self._cache_list = os.urandom(10)
                    print('\033[31merror in', self._tag)
                    print('Unknown error!!', e)
                    traceback.print_exc()
                    print('\033[0m')
                except Exception:
                    # Clear cache when any error
                    self._cache_list = os.urandom(10)
                    print('\033[31merror in', self._tag)
                    traceback.print_exc()
                    print('\033[0m')
                # Sleep when each loop ended
                sleep(sleep_time)

        # Boot check
        if not self._table_name or self._TOKENS.count(None) == len(self._TOKENS) or not self._db:
            print('\033[31m' + self._tag + " boot failed! Nothing happened!\033[0m")
            return
        t = threading.Thread(target=work)
        t.start()


class NewsPostmanJSON(NewsPostman):
    """
    News Postman class for JSON.

    News Postman class for JSON is as same as News Postman class, but only be used
    when process JSON formatted data.

    Attributes:
        As same as NewsPostman.
    """

    def __init__(self, listURLs, sendList, db, tag='', display_policy=default_policy):
        """As same as NewsPostman."""
        super(NewsPostmanJSON, self).__init__(listURLs, sendList=sendList, tag=tag,
                                              display_policy=display_policy, db=db)
        self._extractor = InfoExtractorJSON()


class NewsPostmanXML(NewsPostman):
    """
    News Postman class for XML.

    News Postman class for XML is as same as News Postman class, but only be used
    when process XML formatted data.

    Attributes:
            As same as NewsPostman.
    """

    def __init__(self, listURLs, sendList, db, tag='', display_policy=default_policy):
        """As same as NewsPostman."""
        super(NewsPostmanXML, self).__init__(listURLs, sendList=sendList, tag=tag,
                                             display_policy=display_policy, db=db)
        self._extractor = InfoExtractorXML()
